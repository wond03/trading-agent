# 主循环 —— 串起全链路: 行情 → 结构 → 流动性 → 入场 → 风控 → (模拟盘下单) → 企微推送
# 运行模式: DRY_RUN=1 只告警不下单(默认); AUTO_TRADE=1 启用模拟盘自动下单
import os, sys, json, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
from structure import StructureEngine, Candle
from liquidity import LiquidityEngine
from entry import EntryEngine
from exits import ExitEngine, Position
from risk import RiskManager, size_fixed_margin, liquidation_sl
from okx_client import OkxClient

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "state.json")
WECOM = os.environ.get(C.WECOM_WEBHOOK_ENV, "")
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"
CAPITAL_USD = float(os.environ.get("CAPITAL_USD", "10000"))   # 账户资金(可用 GitHub Secrets 覆盖)

def push(text):
    print("=== 推送内容 ===\n" + text + "\n=== 结束 ===")   # 同时打印到日志(便于云端诊断)
    if not WECOM:
        print("[企微未配置]"); return
    try:
        import requests
        r = requests.post(WECOM, json={"msgtype": "markdown", "markdown": {"content": text}}, timeout=8)
        print(f"[已推送企微] code={r.status_code}")
    except Exception as e:
        print(f"[推送失败] {e}")

def load_state():
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {"positions": [], "daily": {"date": "", "trades": 0}, "last_signal_bar": {}}

def fmt_price(x):
    return f"{x:,.0f}" if x >= 100 else f"{x:,.2f}"

def simplify_reason(reason):
    """技术证据链 → 人话"""
    import re
    r = reason.split("|")[0] if "|" in reason else reason      # 去掉尾部重复的RR
    r = re.sub(r"上截取@([\d.]+)\((\d)\)", r"扫上方流动性\1(双点)", r)
    r = re.sub(r"下截取@([\d.]+)\((\d)\)", r"扫下方流动性\1(双点)", r)
    r = re.sub(r"转多@[\d.]+", "结构转多", r)
    r = re.sub(r"转空@[\d.]+", "结构转空", r)
    r = r.replace("回踩收阳", "回踩企稳").replace("回踩收阴", "回踩走弱").replace("放量触发", "放量确认")
    r = r.replace("回踩 → 回踩走弱", "回踩走弱").replace("回踩 → 回踩企稳", "回踩企稳").replace("回踩 → 放量确认", "回踩放量确认")
    return r.strip().strip("→ ").replace(" → ", " → ")

def format_signal(inst_id, sig, size, sl_use=None, liq=None):
    """信号消息模板 (固定保证金模式: 显示爆仓价与强平止损)"""
    name = "BTC" if "BTC" in inst_id else "黄金"
    side = "做多" if sig.direction == "long" else "做空"
    sl = sl_use if sl_use else sig.sl
    sl_pct = abs(sl - sig.entry) / sig.entry * 100
    tp_pct = abs(sig.tp - sig.entry) / sig.entry * 100
    rr = abs(sig.tp - sig.entry) / max(abs(sig.entry - sl), 1e-9)
    if sig.direction == "long":
        sl_txt, tp_txt = f"跌{sl_pct:.1f}%即离场", f"涨{tp_pct:.1f}%止盈"
    else:
        sl_txt, tp_txt = f"涨{sl_pct:.1f}%即离场", f"跌{tp_pct:.1f}%止盈"
    unit = "BTC" if "BTC" in inst_id else "XAU"
    msg = (f"🚨 **新信号 · {name} {side}**\n\n"
           f"**进场** {fmt_price(sig.entry)}\n"
           f"**止损** {fmt_price(sl)}  ({sl_txt})")
    if liq:
        msg += f"\n**爆仓价** {fmt_price(liq)}  (止损在其前0.3%强平)"
    msg += (f"\n**目标** {fmt_price(sig.tp)}  ({tp_txt})\n"
            f"**盈亏比** 1 : {rr:.1f}\n\n"
            f"**依据** {simplify_reason(sig.reason)}\n"
            f"**下单** {size['lots']} 张 ≈ {size['notional']:.0f}U 名义  保证金{size['margin']:.1f}U · {size['leverage']}倍")
    if DRY_RUN:
        msg += "\n\n> 模拟观察模式，未实际下单"
    return msg

def build_daily_report(state, now_bj):
    """每日日报 (北京时间早8点推送)"""
    day = now_bj.strftime("%m-%d")
    lines = [f"**📊 每日日报 {day} (北京时间)**", ""]
    lines.append(f"**系统**: ✅ 正常 | 今日已运行 {state.get('run_count_today', 0)} 次")
    hist = [h for h in state.get("history", []) if time.time() - h.get("ts", 0) < 86400]
    sigs = [h for h in hist if h["type"] == "signal"]
    exs = [h for h in hist if h["type"] == "exit"]
    lines.append(f"**过去24h**: 信号 {len(sigs)} 个 | 出场 {len(exs)} 笔")
    for h in sigs[-4:]:
        lines.append(f"  🚨 {h['detail']}")
    for h in exs[-4:]:
        lines.append(f"  🏁 {h['detail']}")
    pos = state.get("positions", [])
    if pos:
        lines.append(f"**当前持仓** {len(pos)} 个:")
        for p in pos:
            lines.append(f"  · {p['inst']} {p['direction'].upper()} 进{p['entry']:.0f} 损{p['sl']:.0f} 标{p['tp']:.0f}")
    else:
        lines.append("**当前持仓**: 无")
    lines.append("")
    lines.append(f"_模式: {'DRY_RUN(只告警)' if DRY_RUN else '模拟盘自动交易'} · 资金 {CAPITAL_USD:.0f}U_")
    return "\n".join(lines)

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"), ensure_ascii=False, indent=1)

def fetch_candles(client, inst_id, limit=300):
    """数据源路由: 正式=OKX; 本地测试=Gate.io(沙盒可达)"""
    if os.environ.get("DATA_SOURCE") == "gate":
        import requests
        pair = {"BTC-USDT-SWAP": "BTC_USDT", "XAU-USDT-SWAP": "PAXG_USDT"}.get(inst_id, "BTC_USDT")  # 本地测试:XAU用PAXG代理
        r = requests.get("https://api.gateio.ws/api/v4/spot/candlesticks",
                         params={"currency_pair": pair, "interval": "1h", "limit": limit}, timeout=15)
        return [Candle(int(d[0]), float(d[5]), float(d[3]), float(d[4]), float(d[2]), float(d[1])) for d in r.json()]
    return client.get_candles(inst_id, C.BASE_TF, limit)

def run_once():
    state = load_state()
    now_bj = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    # 节流: 距上次运行<50分钟则跳过 (应对高频调度; GitHub调度实际执行率低)
    last = state.get("last_run_ts", 0)
    if time.time() - last < 50 * 60:
        print(f"[节流跳过] 距上次运行{int((time.time()-last)/60)}分钟 <50分钟")
        return
    state["last_run_ts"] = time.time()
    today = now_bj.date().isoformat()
    if state["daily"]["date"] != today:
        state["daily"] = {"date": today, "trades": 0}
        state["run_count_today"] = 0
    state["run_count_today"] = state.get("run_count_today", 0) + 1

    client = OkxClient(simulated=True)
    risk = RiskManager(capital_usd=CAPITAL_USD, risk_score=3)
    risk.daily_trades = state["daily"]["trades"]
    reports = []

    for inst_id, sym_cfg in C.SYMBOLS.items():
        if not sym_cfg.get("enabled"):
            continue
        try:
            candles = fetch_candles(client, inst_id)
        except Exception as e:
            reports.append(f"❌ {inst_id} 行情失败: {e}"); continue
        if len(candles) < 120:
            continue
        se, le = StructureEngine(), LiquidityEngine()
        se.process(candles); le.process(candles)
        htf = "up" if candles[-1].close > candles[-50].close else "down"
        px = candles[-1].close

        # ---- 新信号检测 (含指纹去重: 同一信号只推一次) ----
        ee = EntryEngine()
        sig = ee.evaluate(candles, se, le, htf, bar_i=len(candles)-1)
        if sig:
            # 指纹用稳定特征: 品种+方向+止损结构位(取整到10美元, 抗ATR微漂移)
            fp = f"{inst_id}|{sig.direction}|{round(sig.sl / 10) * 10}"
            if fp in state.get("pushed_signals", []):
                print(f"[跳过重复信号] {fp}")
                sig = None
        if sig:
            ok, detail = risk.check_gates(sig)
            if ok:
                size = size_fixed_margin(px, inst_id)
                sl_use, liq_px = liquidation_sl(sig.entry, sig.direction)
                line = format_signal(inst_id, sig, size, sl_use, liq_px)
                if not DRY_RUN:
                    client.set_leverage(inst_id, size["leverage"], sym_cfg.get("td_mode", "isolated"))
                    side = "buy" if sig.direction == "long" else "sell"
                    resp = client.place_order(inst_id, side, size["lots"], td_mode=sym_cfg.get("td_mode", "isolated"))
                    ok_txt = "✅ 已自动下单" if resp.get("code") == "0" else f"❌ 下单失败: {str(resp)[:80]}"
                    line = line.replace("> 模拟观察模式，未实际下单", f"> {ok_txt}")
                    if resp.get("code") == "0":
                        state["positions"].append({"inst": inst_id, "direction": sig.direction,
                                                   "entry": sig.entry, "sl": sl_use, "tp": sig.tp,
                                                   "size": size["lots"], "ratio": 1.0,
                                                   "risk_free": False, "tp1_hit": False,
                                                   "leverage": size["leverage"],
                                                   "opened": int(time.time())})
                        state["daily"]["trades"] += 1
                else:
                    pass  # DRY_RUN 提示已由 format_signal 生成
                reports.append(line)
                state.setdefault("history", []).append({"type": "signal", "ts": time.time(),
                    "detail": f"{inst_id} {sig.direction.upper()} 进{sig.entry:.0f} 损{sig.sl:.0f} 标{sig.tp:.0f} RR1:{(abs(sig.tp-sig.entry)/max(abs(sig.entry-sig.sl),1e-9)):.1f}"})
            else:
                reports.append(f"⚠️ **{inst_id} 信号被风控拦截**\n" + "\n".join(f"· {d}" for d in detail if "❌" in d))
            # 记录指纹(去重), 保留最近60条
            state.setdefault("pushed_signals", []).append(fp)
            state["pushed_signals"] = state["pushed_signals"][-60:]

        # ---- 持仓管理 (出场引擎; 完整恢复状态, 修复Bug2) ----
        for p in list(state["positions"]):
            if p["inst"] != inst_id:
                continue
            pos = Position(p["direction"], p["entry"], p["sl"], p["tp"],
                           size=p.get("ratio", 1.0), opened_bar=0)
            pos.risk_free = p.get("risk_free", False)
            pos.tp1_hit = p.get("tp1_hit", False)
            xe = ExitEngine()
            acts = xe.manage(pos, candles, se, le)
            exited = False
            for act in acts:
                if act[0] == "EXIT":
                    _nm = "BTC" if "BTC" in inst_id else "黄金"
                    _sd = "多单" if p["direction"] == "long" else "空单"
                    reports.append(f"🏁 **出场 · {_nm} {_sd}**\n**原因** {act[1]}\n**进场** {fmt_price(p['entry'])}")
                    state.setdefault("history", []).append({"type": "exit", "ts": time.time(),
                        "detail": f"{inst_id} {p['direction'].upper()} 进{p['entry']:.0f} {act[1]}"})
                    if not DRY_RUN:
                        side = "sell" if p["direction"] == "long" else "buy"
                        client.close_position(inst_id, side, p["size"], td_mode=sym_cfg.get("td_mode", "cross"))
                    state["positions"].remove(p)
                    exited = True
                    break
                elif act[0] == "PARTIAL_TP":
                    cut = round(p["size"] * 0.5, 6)
                    if not DRY_RUN:
                        side = "sell" if p["direction"] == "long" else "buy"
                        client.close_position(inst_id, side, cut, td_mode=sym_cfg.get("td_mode", "cross"))
                    p["size"] = round(p["size"] - cut, 6)
                    p["ratio"] = pos.size
                    p["tp1_hit"] = True
                    reports.append(f"{inst_id} {act[1]} 已平{cut}")
                elif act[0] == "MOVE_SL":
                    p["sl"] = pos.sl
                    p["risk_free"] = pos.risk_free
                    reports.append(f"{inst_id} {act[1]}")
            if not exited:
                # 状态写回(修复Bug2: 保本/部分止盈持久化)
                p["sl"] = pos.sl
                p["risk_free"] = pos.risk_free
                p["tp1_hit"] = pos.tp1_hit
                p["ratio"] = pos.size

    # ---- 每日日报: 北京时间8-10点间当天首次运行触发 ----
    if 8 <= now_bj.hour < 10 and state.get("daily_report_date") != today:
        push(build_daily_report(state, now_bj))
        state["daily_report_date"] = today

    # ---- 推送策略: 有实质内容才推; 无内容静默 ----
    if reports:
        header = f"📡 **盯盘巡检** · {now_bj.strftime('%m-%d %H:%M')}"
        push(f"{header}\n\n" + "\n\n".join(reports))
    else:
        print(f"=== 静默(无新信号) {now_bj.strftime('%m-%d %H:%M')} ===")

    state["history"] = state.get("history", [])[-100:]   # 历史保留最近100条
    save_state(state)

if __name__ == "__main__":
    run_once()
