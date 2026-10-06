# -*- coding: utf-8 -*-
"""短线回测: 用【引擎自己的代码】逐根 15m 回放 SIGNAL_MODE=fvg_touch, 并对每个信号
向前追踪 TP(±1%) / 结构止损 的先后, 统计信号数/胜率/净U。
用法: python tools/bt1d.py [品种] [最近N根] [K=V ...]
例:   python tools/bt1d.py XAU-USDT-SWAP 96 FVGT_REQUIRE_STRUCT=False
说明: 每个信号独立评估(允许重叠持仓), 只为看"信号本身的质量"; 不是组合净值。
"""
import sys, os, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))

import config as C
from structure import StructureEngine, Candle
from liquidity import LiquidityEngine
from entry import EntryEngine
from risk import size_fixed_margin

args = sys.argv[1:]
INST = args[0] if len(args) > 0 else "XAU-USDT-SWAP"
N = int(args[1]) if len(args) > 1 else 96
for kv in args[2:]:
    if "=" in kv:
        k, v = kv.split("=", 1)
        for f in (int, float):
            try:
                v = f(v); break
            except ValueError:
                pass
        else:
            v = {"True": True, "False": False}.get(v, v.strip('"'))
        setattr(C, k, v)

CST = datetime.timezone(datetime.timedelta(hours=8))
d = json.load(open(os.path.join(HERE, "_cache_weex", f"{INST}_15m.json")))
keys = sorted(int(k) for k in d)
CAND = {k: Candle(k, d[str(k)][0], d[str(k)][1], d[str(k)][2], d[str(k)][3], d[str(k)][4]) for k in keys}


def cd(i, n):
    return [CAND[k] for k in keys[max(0, i - n + 1): i + 1]]


def T(ts):
    return datetime.datetime.fromtimestamp(ts, CST).strftime("%m-%d %H:%M")


LEV = C.WEEX_LEVERAGE.get(INST, C.LEVERAGE_FIXED)
TP_PCT = getattr(C, "TP_PCT", 1.0) / 100.0
trades = []
for i in range(max(0, len(keys) - N), len(keys)):
    c300 = cd(i, 300)
    if len(c300) < 120:
        continue
    se = StructureEngine(C.SWING_LEN_HTF); se.process(c300)
    le = LiquidityEngine(); le.process(c300)
    c200 = cd(i, 200)
    lse = StructureEngine(C.SWING_LEN_LTF); lse.process(c200); lse.last_idx = len(c200) - 1
    lle = LiquidityEngine(); lle.process(c200)
    hse = StructureEngine(C.SWING_LEN_HTF); hse.process(c200); htf = hse.trend
    ee = EntryEngine()
    sig = ee.evaluate(c300, se, le, htf, bar_i=len(c300) - 1, ltf_se=lse, ltf_le=lle, ltf_candles=c200)
    if not sig:
        continue
    # 向前追踪 (最多 96 根 15m = 24h), 同根内先判止损(保守)
    d_ = sig.direction
    out, reason, nb = CAND[keys[-1]].close, "未平", len(keys) - 1 - i
    for k in range(i + 1, min(i + 97, len(keys))):
        b = CAND[keys[k]]
        if d_ == "long":                      # 止损在下方, 止盈在上方
            if b.low <= sig.sl:
                out, reason, nb = sig.sl, "止损", k - i; break
            if b.high >= sig.tp:
                out, reason, nb = sig.tp, "止盈", k - i; break
        else:                                 # 空: 止损在上方, 止盈在下方
            if b.high >= sig.sl:
                out, reason, nb = sig.sl, "止损", k - i; break
            if b.low <= sig.tp:
                out, reason, nb = sig.tp, "止盈", k - i; break
    sz = size_fixed_margin(sig.entry, INST, LEV)
    sign = 1.0 if d_ == "long" else -1.0
    gross = (out - sig.entry) * sign * sz["lots"] * C.INST_SPECS[INST]["ctVal"]
    gross = max(gross, -sz["margin"])          # 亏损封顶=保证金(强平)
    fee = 2.0 * 0.0005 * sz["notional"]
    trades.append(dict(t=T(keys[i]), dir=d_, entry=sig.entry, sl=sig.sl, tp=sig.tp,
                       out=out, reason=reason, nb=nb, net=gross - fee, notional=sz["notional"]))

wins = [x for x in trades if x["reason"] == "止盈"]
loss = [x for x in trades if x["reason"] == "止损"]
opn = [x for x in trades if x["reason"] == "未平"]
net = sum(x["net"] for x in trades)
print(f"\n[{INST}] 最近 {min(N, len(keys))} 根15m ({T(keys[-min(N,len(keys))])} → {T(keys[-1])}) | "
      f"SIGNAL_MODE={C.SIGNAL_MODE} FVGT_REQUIRE_STRUCT={C.FVGT_REQUIRE_STRUCT} | 50x 名义≈{trades[0]['notional']:.0f}U" if trades else "无信号")
for x in trades:
    print(f"   {x['t']}  {x['dir'].upper():<5} @{x['entry']:.1f} → {x['out']:.1f} {x['reason']}({x['nb']}根)  {x['net']:+.2f}U")
print(f"   ---- 信号 {len(trades)} 笔 | 止盈 {len(wins)} / 止损 {len(loss)} / 未平 {len(opn)} "
      f"| 胜率 {100*len(wins)/max(1,len(wins)+len(loss)):.0f}% | 净 {net:+.2f}U")
