# 主循环 —— 串起全链路: 行情 → 结构 → 流动性 → 入场 → 风控 → (模拟盘下单) → 企微推送
# 运行模式: DRY_RUN=1 只告警不下单(默认); AUTO_TRADE=1 启用模拟盘自动下单
import os, sys, json, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
from structure import StructureEngine, Candle
from liquidity import LiquidityEngine
from entry import EntryEngine
from exits import ExitEngine, Position
from risk import RiskManager
from okx_client import OkxClient

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "state.json")
WECOM = os.environ.get(C.WECOM_WEBHOOK_ENV, "")
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"

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

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"), ensure_ascii=False, indent=1)

def fetch_candles(client, inst_id, limit=300):
    """数据源路由: 正式=OKX; 本地测试=Gate.io(沙盒可达)"""
    if os.environ.get("DATA_SOURCE") == "gate":
        import requests
        pair = {"BTC-USDT-SWAP": "BTC_USDT", "PAXG-USDT": "PAXG_USDT"}.get(inst_id, "BTC_USDT")
        r = requests.get("https://api.gateio.ws/api/v4/spot/candlesticks",
                         params={"currency_pair": pair, "interval": "1h", "limit": limit}, timeout=15)
        return [Candle(int(d[0]), float(d[5]), float(d[3]), float(d[4]), float(d[2]), float(d[1])) for d in r.json()]
    return client.get_candles(inst_id, C.BASE_TF, limit)

def run_once():
    state = load_state()
    now_bj = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    # 节流: 距上次运行<50分钟则跳过 (应对高频调度; GitHub调度实际执行率低)
    last = state.get("last_run_ts", 0)
    if time.time() - last < 50 * 60:
        print(f"[节流跳过] 距上次运行{int((time.time()-last)/60)}分钟 <50分钟")
        return
    state["last_run_ts"] = time.time()
    today = now_bj.date().isoformat()
    if state["daily"]["date"] != today:
        state["daily"] = {"date": today, "trades": 0}

    client = OkxClient(simulated=True)
    risk = RiskManager(capital_usd=10000, risk_score=3)
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

        # ---- 新信号检测 ----
        ee = EntryEngine()
        sig = ee.evaluate(candles, se, le, htf, bar_i=len(candles)-1)
        if sig:
            ok, detail = risk.check_gates(sig)
            if ok:
                size = risk.position_size(sig.entry, sig.sl, sig.direction)
                line = (f"**🚨 新信号 {inst_id}**\n{sig}\n"
                        f"仓位: {size['qty']} (名义{size['notional']}U 保证金{size['margin']}U {size['leverage']}x)\n"
                        f"风控: 单笔风险{size['risk_amount']}U")
                if not DRY_RUN:
                    side = "buy" if sig.direction == "long" else "sell"
                    resp = client.place_order(inst_id, side, size["qty"], td_mode=sym_cfg.get("td_mode", "cross"))
                    line += f"\n下单: {'✅' if resp.get('code')=='0' else '❌ ' + str(resp)[:100]}"
                    if resp.get("code") == "0":
                        state["positions"].append({"inst": inst_id, "direction": sig.direction,
                                                   "entry": sig.entry, "sl": sig.sl, "tp": sig.tp,
                                                   "size": size["qty"], "opened": int(time.time())})
                        state["daily"]["trades"] += 1
                else:
                    line += "\n(DRY_RUN 未实际下单)"
                reports.append(line)
            else:
                reports.append(f"**{inst_id} 信号被风控拦截**\n" + "\n".join(f"  {d}" for d in detail))

        # ---- 持仓管理 (出场引擎) ----
        for p in list(state["positions"]):
            if p["inst"] != inst_id:
                continue
            pos = Position(p["direction"], p["entry"], p["sl"], p["tp"], opened_bar=0)
            xe = ExitEngine()
            acts = xe.manage(pos, candles, se, le)
            for act in acts:
                if act[0] == "EXIT":
                    reports.append(f"**{inst_id} 出场** {act[1]} (entry={p['entry']:.1f})")
                    if not DRY_RUN:
                        side = "sell" if p["direction"] == "long" else "buy"
                        client.close_position(inst_id, side, p["size"], td_mode=sym_cfg.get("td_mode", "cross"))
                    state["positions"].remove(p)
                elif act[0] == "MOVE_SL":
                    p["sl"] = pos.sl
                    reports.append(f"{inst_id} {act[1]}")

    save_state(state)

    # ---- 推送策略: 有实质内容才推; 否则每天北京时间9点推一次心跳 ----
    if reports:
        header = f"**📡 盯盘巡检 {now_bj.strftime('%m-%d %H:%M')} (北京时间)**"
        push(f"{header}\n\n" + "\n\n".join(reports))
    elif now_bj.hour == 9:
        push(f"**📡 每日心跳 {now_bj.strftime('%m-%d %H:%M')}**\n\n系统正常, 无新信号, 持仓平稳")
    else:
        print(f"=== 静默(无新信号) {now_bj.strftime('%m-%d %H:%M')} ===")

if __name__ == "__main__":
    run_once()
