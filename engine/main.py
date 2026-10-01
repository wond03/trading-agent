# 暗夜猎手 (NightHunter) 主循环 —— 串起全链路: 行情 → 结构 → 流动性 → 入场 → 风控 → (模拟盘下单) → 企微推送
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
    """读取状态: 主文件损坏时自动回退备份(错误自愈)"""
    for path in (STATE_FILE, STATE_FILE + ".bak"):
        try:
            return json.load(open(path))
        except Exception:
            continue
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
    _g = getattr(sig, "grade", "A")
    _emoji = "🚨" if _g == "A" else "📣"
    msg = (f"{_emoji} **{_g}级信号 · {name} {side}**\n\n"
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
    """每日日报 (北京时间早8点后首次运行推送)"""
    day = now_bj.strftime("%m-%d")
    runs = state.get("run_count_today", 0)
    hist = [h for h in state.get("history", []) if time.time() - h.get("ts", 0) < 86400]
    sigs = [h for h in hist if h["type"] == "signal"]
    exs = [h for h in hist if h["type"] == "exit"]
    pos = state.get("positions", [])

    lines = [f"🌙 **暗夜猎手 · 日报 {day}**", ""]
    lines.append(f"**系统** ✅ 今日运行 {runs} 次")
    lines.append(f"**交易** 信号 {len(sigs)} · 出场 {len(exs)} · 持仓 {len(pos)}")
    if exs:
        pnl = sum(h.get("pnl", 0) for h in exs)
        wins = sum(1 for h in exs if h.get("pnl", 0) > 0)
        lines.append(f"**盈亏** {pnl:+.2f}U · 胜率 {wins}/{len(exs)}")
    else:
        lines.append("**盈亏** 暂无平仓样本")

    if pos:
        lines.append("")
        lines.append("**当前持仓**")
        for p in pos:
            nm = "BTC" if "BTC" in p["inst"] else "黄金"
            sd = "做多" if p["direction"] == "long" else "做空"
            tag = "🧪模拟" if p.get("simulated") else "💰实盘"
            lines.append(f"{tag} {nm}{sd} · 进{fmt_price(p['entry'])} 损{fmt_price(p['sl'])} 标{fmt_price(p['tp'])}")

    if sigs:
        lines.append("")
        _ga = sum(1 for h in sigs if h.get("grade", "A") == "A")
        _gb = len(sigs) - _ga
        lines.append(f"**24h 信号**（A级{_ga} · B级{_gb}）")
        for h in sigs[-3:]:
            lines.append(f"· [{h.get('grade','A')}] {h['detail']}")

    ms = state.get("market_snapshot", [])
    if ms:
        lines.append("")
        lines.append("**市场状态**")
        lines.extend(ms)

    try:
        from auto_calibrator import analyze
        d = analyze(state.get("history", []))
        lines.append("")
        lines.append(f"**🔬 诊断** {d['summary']}")
        for a in d.get("advice", [])[:2]:
            lines.append(f"· {a}")
    except Exception as e:
        print(f"[诊断异常] {e}")

    lines.append("")
    lines.append(f"_{'模拟观察' if DRY_RUN else '模拟盘自动交易'} · {C.MARGIN_PER_TRADE:.0f}U/单 · {C.LEVERAGE_FIXED}倍_")
    return "\n".join(lines)

def save_state(s):
    """保存前先备份旧状态(错误自愈)"""
    try:
        if os.path.exists(STATE_FILE):
            import shutil
            shutil.copy(STATE_FILE, STATE_FILE + ".bak")
    except Exception:
        pass
    json.dump(s, open(STATE_FILE, "w"), ensure_ascii=False, indent=1)

PAIR_MAP = {"BTC-USDT-SWAP": "BTC_USDT", "XAU-USDT-SWAP": "PAXG_USDT"}

def _fetch_gate(inst_id, limit, tf="1h"):
    import requests
    pair = PAIR_MAP.get(inst_id, "BTC_USDT")
    r = requests.get("https://api.gateio.ws/api/v4/spot/candlesticks",
                     params={"currency_pair": pair, "interval": tf, "limit": limit}, timeout=15)
    return [Candle(int(d[0]), float(d[5]), float(d[3]), float(d[4]), float(d[2]), float(d[1])) for d in r.json()]

def fetch_candles(client, inst_id, limit=300, tf=None):
    """数据源路由 + 故障自愈: OKX主力 → 失败自动切换 Gate.io 备用"""
    tf = tf or C.BASE_TF
    gate_tf = {"1H": "1h", "4H": "4h", "15m": "15m"}.get(tf, "1h")
    if os.environ.get("DATA_SOURCE") == "gate":
        return _fetch_gate(inst_id, limit, gate_tf)
    try:
        return client.get_candles(inst_id, tf, limit)
    except Exception as e:
        print(f"[自愈] OKX行情({tf})失败({type(e).__name__}), 切换备用源...")
        try:
            k = _fetch_gate(inst_id, limit, gate_tf)
            print(f"[自愈] 备用源成功: {len(k)}根")
            return k
        except Exception as e2:
            raise RuntimeError(f"主源失败({e}) 且备用源失败({e2})")

def get_htf_trend(client, inst_id, candles_1h):
    """大周期趋势: 优先用真实4H数据(课程A6: 只推一级); 失败回退1H斜率
    4H窗口20根 ≈ 3.3天, 比原来1H-50根(2天)更稳定, 避免趋势频繁翻转"""
    try:
        c4 = fetch_candles(client, inst_id, limit=60, tf="4H")
        if len(c4) >= 21:
            return ("up" if c4[-1].close > c4[-20].close else "down"), "4H"
    except Exception as e:
        print(f"[HTF] 4H获取失败({type(e).__name__}), 回退1H斜率")
    return ("up" if candles_1h[-1].close > candles_1h[-50].close else "down"), "1H(回退)"

def run_once():
    state = load_state()
    now_bj = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    # 节流: 距上次运行<25分钟则跳过 (配合cron-job.org每30分钟触发, 控制Actions额度)
    last = state.get("last_run_ts", 0)
    if time.time() - last < 25 * 60:
        print(f"[节流跳过] 距上次运行{int((time.time()-last)/60)}分钟 <25分钟")
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
    market_notes = []

    # 连亏保护(自进化阶段②-轻量): 最近3笔全亏 → 本轮不开新仓(持仓照常管理)
    recent3 = [h for h in state.get("history", []) if h.get("type") == "exit"][-3:]
    halt_new = len(recent3) == 3 and all(h.get("pnl", 0) <= 0 for h in recent3)
    if halt_new:
        print("[连亏保护] 最近3笔全亏, 本轮不开新仓")

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
        htf, htf_src = get_htf_trend(client, inst_id, candles)
        px = candles[-1].close

        # ---- 市场状态采集(供日报) ----
        _nmk = "BTC" if "BTC" in inst_id else "黄金"
        _trend = {"up": "上涨", "down": "下跌", None: "震荡"}.get(se.trend, "不明")
        _af = le.snapshot()["active_fvgs"]
        _fvg = f"{_af[-1]['bottom']:,.0f}~{_af[-1]['top']:,.0f}" if _af else "无"
        _lv = le.sweeps[-1] if le.sweeps else None
        _sweep_txt = f"{'扫上' if _lv[1]=='up' else '扫下'}{_lv[2]:,.0f}({_lv[3]}点)" if _lv else "无近期截取"
        market_notes.append(f"· {_nmk}: {_trend}趋势 | 活跃FVG {_fvg} | 最近截取 {_sweep_txt}")

        # ---- 新信号检测 (含指纹去重: 同一信号只推一次) ----
        ee = EntryEngine()
        sig = ee.evaluate(candles, se, le, htf, bar_i=len(candles)-1)
        if sig:
            # 指纹用稳定特征: 品种+方向+止损结构位(取整到10美元, 抗ATR微漂移)
            fp = f"{inst_id}|{sig.direction}|{round(sig.sl / 10) * 10}"
            if fp in state.get("pushed_signals", []):
                print(f"[跳过重复信号] {fp}")
                sig = None
        # 该品种已有持仓 → 不重复开仓(防同波行情过度交易)
        _has_pos = any(p["inst"] == inst_id for p in state.get("positions", []))
        if sig and _has_pos:
            print(f"[跳过] {inst_id} 已有持仓, 不重复开仓")
            sig = None
        if sig:
            ok, detail = risk.check_gates(sig)
            if ok and halt_new:
                reports.append(f"🛑 **连亏保护** 最近3笔全亏，跳过开仓（{inst_id}）")
                ok = False
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
                    # DRY_RUN: 建立虚拟持仓 → 观察期自动统计模拟盈亏
                    state["positions"].append({"inst": inst_id, "direction": sig.direction,
                                               "entry": sig.entry, "sl": sl_use, "tp": sig.tp,
                                               "size": size["lots"], "ratio": 1.0,
                                               "risk_free": False, "tp1_hit": False,
                                               "leverage": size["leverage"], "simulated": True,
                                               "opened": int(time.time())})
                reports.append(line)
                _nmx = "BTC" if "BTC" in inst_id else "黄金"
                _sdx = "做多" if sig.direction == "long" else "做空"
                _rrx = abs(sig.tp - sig.entry) / max(abs(sig.entry - sl_use), 1e-9)
                state.setdefault("history", []).append({"type": "signal", "ts": time.time(),
                    "grade": getattr(sig, "grade", "A"),
                    "detail": f"{_nmx}{_sdx} · 进{fmt_price(sig.entry)} 损{fmt_price(sl_use)} 标{fmt_price(sig.tp)} · RR1:{_rrx:.0f}"})
            else:
                reports.append(f"⚠️ **{inst_id} 信号被风控拦截**\n" + "\n".join(f"· {d}" for d in detail if "❌" in d))
            # 记录指纹(去重), 保留最近60条
            state.setdefault("pushed_signals", []).append(fp)
            state["pushed_signals"] = state["pushed_signals"][-60:]

        # ---- B级机会观察(埋伏提示: 截取+回踩到位, 尚未转势) ----
        if not sig:
            w = ee.evaluate_watch(candles, se, le, htf, bar_i=len(candles) - 1)
            if w:
                wfp = f"WATCH|{inst_id}|{w['direction']}|{round(w['sweep_level'] / 10) * 10}"
                if wfp not in state.get("pushed_watch", []):
                    _wnm = "BTC" if "BTC" in inst_id else "黄金"
                    _wd = "做多" if w["direction"] == "up" else "做空"
                    reports.append(
                        f"👀 **B级机会观察 · {_wnm}{_wd}**\n\n"
                        f"**已完成** 扫过流动性 {fmt_price(w['sweep_level'])}（{w['sweep_pts']}点），价格回踩到位\n"
                        f"**等什么** 等『实体突破结构』的转势确认 → 确认后升级为 A 级信号\n"
                        f"**现价** {fmt_price(w['px'])}")
                    state.setdefault("pushed_watch", []).append(wfp)
                    state["pushed_watch"] = state["pushed_watch"][-40:]

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
                    exit_px = act[2] if len(act) > 2 else p["entry"]
                    ctval = C.INST_SPECS.get(inst_id, {}).get("ctVal", 0)
                    sign = 1 if p["direction"] == "long" else -1
                    pnl = (exit_px - p["entry"]) * sign * p["size"] * ctval
                    tag = "(模拟)" if p.get("simulated") else ""
                    reports.append(f"🏁 **出场{tag} · {_nm} {_sd}**\n**原因** {act[1]}\n"
                                   f"**进场** {fmt_price(p['entry'])} → **出场** {fmt_price(exit_px)}\n"
                                   f"**盈亏** {pnl:+.2f}U ({pnl / C.MARGIN_PER_TRADE * 100:+.0f}%保证金)")
                    state.setdefault("history", []).append({"type": "exit", "ts": time.time(), "pnl": round(pnl, 2),
                        "detail": f"{_nm} {p['direction'].upper()} {pnl:+.2f}U"})
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

    # ---- 每日日报: 北京时间8点后当天首次运行触发(窗口放宽, 防止调度错过8点档) ----
    if now_bj.hour >= 8 and state.get("daily_report_date") != today:
        push(build_daily_report(state, now_bj))
        state["daily_report_date"] = today

    # ---- 推送策略: 有实质内容才推; 无内容静默 ----
    if reports:
        header = f"🌙 **暗夜猎手 · 巡检** {now_bj.strftime('%m-%d %H:%M')}"
        push(f"{header}\n\n" + "\n\n".join(reports))
    else:
        print(f"=== 静默(无新信号) {now_bj.strftime('%m-%d %H:%M')} ===")

    state["history"] = state.get("history", [])[-100:]   # 历史保留最近100条
    state["market_snapshot"] = market_notes               # 供日报展示
    state["fail_streak"] = 0                              # 运行成功, 重置失败计数
    save_state(state)

if __name__ == "__main__":
    try:
        run_once()
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        try:
            st = load_state()
            st["fail_streak"] = st.get("fail_streak", 0) + 1
            save_state(st)
            n = st["fail_streak"]
            if n >= 3:
                push(f"🔴 **暗夜猎手 · 连续{n}次运行失败**\n\n```\n{str(e)[:200]}\n```\n请检查 Actions 日志")
            else:
                push(f"⚠️ **暗夜猎手 · 运行异常（第{n}次）**\n\n```\n{str(e)[:200]}\n```")
        except Exception as e2:
            print(f"[告警也失败了] {e2}")
        raise
