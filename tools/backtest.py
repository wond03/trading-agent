#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
暗夜猎手 4-1-15 · 历史回测器 (用 engine/ 现有真实引擎逐根回放, 无未来函数)
- 数据源: Gate.io 现货 K 线 (engine/main.py 的 _fetch_gate 同源, 相同 Candle 构造)
- XAU-USDT-SWAP 用 PAXG_USDT 代理
- 周期链: 1H(主) / 4H(趋势) / 15m(转势+FVG)
- 用法: python tools/backtest.py [--ranges 1w,1m,3m]
产出: deploy/backtest_results.json, deploy/回测报告.md
"""
import sys, os, json, time, bisect, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATA_SOURCE", "gate")

import config as C
from structure import StructureEngine, Candle
from liquidity import LiquidityEngine
from entry import EntryEngine
from exits import ExitEngine, Position
from risk import size_fixed_margin
from main import adaptive_sl
from _fetch_cache import fetch_range

INSTS = ["BTC-USDT-SWAP", "XAU-USDT-SWAP"]
FEE_RATE = 0.0005          # 单边 taker 手续费 0.05% (名义价值)
SLIP_BPS = 0.0002          # 说明用: 有滑点口径 = 单边 2bp 额外成本 (敏感性)
RANGE_DEF = {"1w": 7, "1m": 30, "3m": 90}
WARMUP_BARS = 320          # 回放起点前的 1H 预热根数(>=200)


def load_candles(inst, tf, start_ts, end_ts):
    keys, store = fetch_range(inst, tf, start_ts, end_ts)
    return [Candle(k, store[k][0], store[k][1], store[k][2], store[k][3], store[k][4]) for k in keys]


def replay(inst, bars1h, bars4h, bars15, i0):
    """逐根回放 [i0, len) 的 1H 序列; 返回 (trades, sig_count, samples)"""
    ts4 = [c.ts for c in bars4h]
    ts15 = [c.ts for c in bars15]
    se = StructureEngine(getattr(C, "SWING_LEN_HTF", None))   # 1H(Swing层): 增量复用
    ee = EntryEngine()
    ee.inst = inst                                          # ★2026-10-06: 分品种参数(扫荡刺破幅度)
    xe = ExitEngine()
    positions = []                    # {pos, inst, lots, ctVal, entry, notional, open_i, open_ts}
    trades = []
    sig_count = 0

    def close(pp, exit_px, reason, exit_ts, exit_i):
        d = pp["pos"].direction
        sign = 1.0 if d == "long" else -1.0
        gross = (exit_px - pp["entry"]) * sign * pp["lots"] * pp["ctVal"]
        gross = max(gross, -pp.get("margin", 1e9))   # ★亏损封顶=保证金(模拟交易所强平)
        fee = 2.0 * FEE_RATE * pp["notional"]
        slip = 2.0 * SLIP_BPS * pp["notional"]
        trades.append({
            "inst": inst, "direction": d,
            "open_ts": pp["open_ts"], "exit_ts": exit_ts,
            "entry": pp["entry"], "sl": pp["sl0"], "tp": pp["tp"],
            "exit": round(exit_px, 4), "reason": reason,
            "lots": pp["lots"], "ctVal": pp["ctVal"], "notional": round(pp["notional"], 2),
            "gross": round(gross, 4), "fee": round(fee, 4), "slip": round(slip, 4),
            "net": round(gross - fee, 4), "net_slip": round(gross - fee - slip, 4),
            "bars_held": exit_i - pp["open_i"], "dur_s": exit_ts - pp["open_ts"],
        })

    for i in range(i0, len(bars1h)):
        candles = bars1h[:i + 1]
        se.process(candles)
        le = LiquidityEngine(); le.process(candles)

        # ★2026-10-03 未来函数修复: 决策时刻 D = 1H bar i 的收盘时刻 = ts + 3600
        #   一根K线(时间戳=窗口开始 ts, 时长 d)可用 ⟺ ts + d <= D
        #   旧写法 bisect_right(ts4, T) 会把【覆盖当前时刻却尚未收盘的 4H bar】算进来
        #   (其 OHLC 含 T 之后 1~4h 的数据) → HTF 趋势判断偷看未来;
        #   15m 旧写法则少算了当前 1H 内最后 45 分钟的 15m 数据(回测滞后于实盘)。
        _D = bars1h[i].ts + 3600
        # ★2026-10-04: 周期链改为两个级别(1H+15m) → 背景级别=主周期, 直接用主周期结构方向
        _HTF_TF = list(C.STRATEGY_PROFILES.values())[0].get("htf", "4H")
        if _HTF_TF == "1H":
            htf = se.trend
        else:
            jh = bisect.bisect_right(ts4, _D - 14400)
            sub4 = bars4h[max(0, jh - 200):jh]
            if len(sub4) < 60:
                continue
            s4 = StructureEngine(getattr(C, "SWING_LEN_HTF", None)); s4.process(sub4)
            htf = s4.trend
        if htf not in ("up", "down"):
            continue
        # 小级别(15m)
        j = bisect.bisect_right(ts15, _D - 900)
        sub15 = bars15[max(0, j - 200):j]
        if len(sub15) < 60:
            continue
        lse = StructureEngine(getattr(C, "SWING_LEN_LTF", None)); lse.process(sub15); lse.last_idx = len(sub15) - 1
        lle = LiquidityEngine(); lle.process(sub15)

        # ② 入场
        sig = ee.evaluate(candles, se, le, htf, bar_i=i, ltf_se=lse, ltf_le=lle, ltf_candles=sub15)
        if sig:
            sig_count += 1
            busy = any(pp["inst"] == inst for pp in positions)     # ★2026-10-06 同品种只留一个方向(禁止多空都开仓)
            if not busy:
                _lev = C.WEEX_LEVERAGE.get(inst, C.LEVERAGE_FIXED)   # ★2026-10-05: 与线上一致(WEEX 口径, BTC/XAU 均 100x → 名义≈500U)
                sz = size_fixed_margin(sig.entry, inst, _lev)
                # ★与生产一致: 止损经 adaptive_sl 收进爆仓线内(100x 下结构止损会被爆仓线覆盖)
                sl_use, _liq = adaptive_sl(sig.entry, sig.direction, sig.sl, sig.entry, _lev)
                pos = Position(sig.direction, sig.entry, sl_use, sig.tp, size=1.0, opened_bar=i,
                               inst=inst, lots=sz["lots"])
                positions.append({"pos": pos, "inst": inst, "lots": sz["lots"],
                                  "ctVal": C.INST_SPECS[inst]["ctVal"], "entry": sig.entry,
                                  "notional": sz["notional"], "margin": sz["margin"], "sl0": sl_use, "tp": sig.tp,
                                  "open_i": i, "open_ts": bars1h[i].ts})

        # ③ 出场 (开仓当根不判)
        for pp in list(positions):
            if pp["open_i"] == i:
                continue
            acts = xe.manage(pp["pos"], candles, se, le, i=i)
            for act in acts:
                if act[0] == "EXIT":
                    close(pp, act[2], act[1], bars1h[i].ts, i)
                    positions.remove(pp)
                    break

    # 样本结束仍未平仓 → 以最后一根收盘价强平(透明标注)
    if positions and len(bars1h) > 0:
        last = bars1h[-1]
        for pp in list(positions):
            close(pp, last.close, "样本结束未平仓(按末根收盘强平)", last.ts, len(bars1h) - 1)
            positions.remove(pp)

    return trades, sig_count, len(bars1h) - i0


def stats(trades):
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "gross": 0.0, "net": 0.0, "net_slip": 0.0,
                "avg": 0.0, "best": 0.0, "worst": 0.0, "max_dd": 0.0, "avg_dur_h": 0.0}
    wins = [t for t in trades if t["net"] > 0]
    gross = sum(t["gross"] for t in trades)
    net = sum(t["net"] for t in trades)
    net_slip = sum(t["net_slip"] for t in trades)
    best = max(t["net"] for t in trades)
    worst = min(t["net"] for t in trades)
    # 最大回撤(按逐笔累计净盈亏曲线)
    cum = 0.0; peak = 0.0; mdd = 0.0
    for t in sorted(trades, key=lambda x: x["exit_ts"]):
        cum += t["net"]; peak = max(peak, cum); mdd = max(mdd, peak - cum)
    avg_dur_h = sum(t["dur_s"] for t in trades) / n / 3600.0
    return {"n": n, "win_rate": round(100.0 * len(wins) / n, 1),
            "gross": round(gross, 2), "net": round(net, 2), "net_slip": round(net_slip, 2),
            "avg": round(net / n, 3), "best": round(best, 2), "worst": round(worst, 2),
            "max_dd": round(mdd, 2), "avg_dur_h": round(avg_dur_h, 1)}


def run_range(days, now):
    start = now - days * 86400
    out = {"days": days, "per_inst": {}, "all_trades": []}
    samples_total = 0; sig_total = 0; trades_total = []
    for inst in INSTS:
        b1 = load_candles(inst, "1H", start - WARMUP_BARS * 3600, now)
        b4 = load_candles(inst, "4H", start - 42 * 86400, now)
        b15 = load_candles(inst, "15m", start - 3 * 86400, now)
        ts1 = [c.ts for c in b1]
        i0 = bisect.bisect_left(ts1, start)
        if i0 < 200:
            print(f"  [警告] {inst} 预热不足 i0={i0}, 跳过")
            continue
        tr, sig, samples = replay(inst, b1, b4, b15, i0)
        samples_total += samples; sig_total += sig; trades_total += tr
        out["per_inst"][inst] = {"samples": samples, "signals": sig, "stats": stats(tr),
                                 "window": [ts1[i0], ts1[-1]], "n_bars_1h": len(b1)}
        print(f"  [{inst}] 1H样本{samples} 信号{sig} 交易{len(tr)} 净{stats(tr)['net']}U", flush=True)
    out["samples"] = samples_total; out["signals"] = sig_total
    out["stats"] = stats(trades_total); out["trades"] = trades_total
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ranges", default="1w,1m,3m")
    args = ap.parse_args()
    now = int(time.time())
    ranges = [r.strip() for r in args.ranges.split(",") if r.strip()]
    results = {"now": now, "ranges": {}}
    for r in ranges:
        if r not in RANGE_DEF:
            print("未知区间", r); continue
        print(f"=== 回测区间 {r} ({RANGE_DEF[r]}天) ===", flush=True)
        results["ranges"][r] = run_range(RANGE_DEF[r], now)
    outdir = os.path.join(ROOT, "deploy")
    os.makedirs(outdir, exist_ok=True)
    json.dump(results, open(os.path.join(outdir, "backtest_results.json"), "w"),
              ensure_ascii=False, indent=1)
    print("结果已保存: deploy/backtest_results.json")


if __name__ == "__main__":
    main()
