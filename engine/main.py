# 暗夜猎手 (NightHunter) 主循环 —— 双周期方案并行: 4H+1H 与 4H+15m
# 全链路: 行情 → 结构 → 流动性 → 入场 → 风控 → (模拟盘下单) → 企微推送
# 运行模式: DRY_RUN=1 只告警不下单(默认); DRY_RUN=0 启用模拟盘自动下单
import os, sys, json, time, datetime, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
from structure import StructureEngine, Candle
from liquidity import LiquidityEngine
from entry import EntryEngine
from exits import ExitEngine, Position
from risk import RiskManager, size_fixed_margin
from okx_client import OkxClient
import weex_client               # ★2026-10-03 用户裁定: 信号/回测数据源 = WEEX 合约; 模拟盘交易仍在 OKX

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "state.json")
WECOM = os.environ.get(C.WECOM_WEBHOOK_ENV, "")
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"
CAPITAL_USD = float(os.environ.get("CAPITAL_USD", "10000"))   # 账户资金(可用 GitHub Secrets 覆盖)

# ---------- 双方案配置 ----------
PROFILES = getattr(C, "STRATEGY_PROFILES", {
    "4-1-15": {"label": "4-1-15", "base_tf": C.BASE_TF, "htf": "4H",
               "swing_left": 2, "swing_right": 2}})
# 引擎模块运行时读取 config 全局, 故按方案临时切换这组参数
_PROFILE_KEYS = ("BASE_TF", "SWING_LEFT", "SWING_RIGHT")

@contextlib.contextmanager
def profile_ctx(prof):
    saved = {k: getattr(C, k, None) for k in _PROFILE_KEYS}
    C.BASE_TF = prof["base_tf"]
    C.SWING_LEFT = prof.get("swing_left", 2)
    C.SWING_RIGHT = prof.get("swing_right", 2)
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(C, k, v)

def push(text):
    print("=== 推送内容 ===\n" + text + "\n=== 结束 ===\n")   # 同时打印到日志(便于云端诊断)
    if not WECOM:
        print("[企微未配置]"); return
    try:
        import requests
        r = requests.post(WECOM, json={"msgtype": "markdown", "markdown": {"content": text}}, timeout=8)
        print(f"[已推送企微] code={r.status_code}")
    except Exception as e:
        print(f"[推送失败] {e}")


# ---------- 企微【图片】推送 + 信号标注图 (2026-10-03 新增, 用户裁定A: 只在 信号/开仓/平仓 时推) ----------
_PENDING_CHARTS = []


def push_image(png_path):
    """推送企业微信【图片】消息 (msgtype=image, base64+md5)。失败只打印, 不抛异常。"""
    if not WECOM:
        return
    try:
        import base64, hashlib, requests
        raw = open(png_path, "rb").read()
        if len(raw) > 1_800_000:
            print(f"[推送图片] 文件过大跳过 {len(raw)}B"); return
        r = requests.post(WECOM, json={"msgtype": "image", "image": {
            "base64": base64.b64encode(raw).decode(),
            "md5": hashlib.md5(raw).hexdigest()}}, timeout=25)
        print(f"[已推送企微图片] {os.path.basename(png_path)} {len(raw)}B -> {r.text[:120]}")
    except Exception as e:
        print(f"[推送图片失败] {type(e).__name__} {e}")


def push_chart(client, inst_id, lines, title=""):
    """渲染并推送「信号标注图」: 上=1H(结构/截取/BOS/CHoCH) 下=15m(反转预警 CHoCH+FVG)
    并把该笔的 进场/止损/目标 画上去。lines=[(价格,标签,颜色hex)]
    ★容错: 取数/画图/推送 任一步失败都只打印, **绝不影响交易主流程**。"""
    if not WECOM:
        return
    try:
        import signal_chart
        b_main = fetch_candles(client, inst_id, limit=200, tf="1H")
        b_ltf = fetch_candles(client, inst_id, limit=400, tf="15m")
        if len(b_main) < 20 or len(b_ltf) < 20:
            print(f"[图表] {inst_id} K线不足, 跳过"); return
        s_m = StructureEngine(); s_m.process(b_main)
        l_m = LiquidityEngine(); l_m.process(b_main)
        s_l = StructureEngine(); s_l.process(b_ltf)
        l_l = LiquidityEngine(); l_l.process(b_ltf)
        out = os.path.join(BASE, f"chart_{inst_id.replace('-', '_')}.png")
        p = signal_chart.render(inst_id, b_main, b_ltf, s_m, l_m, s_l, l_l, lines, out,
                                title=title, main_n=60, ltf_n=80)
        if p:
            push_image(p)
    except Exception as e:
        print(f"[图表推送异常] {type(e).__name__} {e}")


def queue_chart(inst_id, lines, title=""):
    """登记一张待推送图表(本轮文字推送完再统一发, 保证"先字后图"的顺序)"""
    _PENDING_CHARTS.append((inst_id, lines, title))


def flush_charts(client):
    while _PENDING_CHARTS:
        inst, lines, title = _PENDING_CHARTS.pop(0)
        push_chart(client, inst, lines, title)

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
    r = re.sub(r"转多@[\d.]+", "转多预警", r)
    r = re.sub(r"转空@[\d.]+", "转空预警", r)
    r = r.replace("回踩收阳", "回踩企稳").replace("回踩收阴", "回踩走弱").replace("放量触发", "放量确认")
    r = r.replace("回踩 → 回踩走弱", "回踩走弱").replace("回踩 → 回踩企稳", "回踩企稳").replace("回踩 → 放量确认", "回踩放量确认")
    return r.strip().strip("→ ").replace(" → ", " → ")

def format_signal(inst_id, sig, size, sl_use=None, liq=None, prof_label=""):
    """信号消息模板 (固定保证金模式: 显示爆仓价与强平止损)"""
    name = "BTC" if "BTC" in inst_id else "黄金"
    side = "做多" if sig.direction == "long" else "做空"
    sl = sl_use if sl_use else sig.sl
    sl_pct = abs(sl - sig.entry) / sig.entry * 100
    tp_pct = abs(sig.tp - sig.entry) / sig.entry * 100
    rr = abs(sig.tp - sig.entry) / max(abs(sig.entry - sl), 1e-9)
    _pct_sl = f"{'−' if sig.direction == 'long' else '+'}{sl_pct:.1f}%"
    _pct_tp = f"{'+' if sig.direction == 'long' else '−'}{tp_pct:.1f}%"
    _emoji = "🚨"
    _title = " · ".join([name, side] + ([prof_label] if prof_label else []))
    L = [f"{_emoji} **信号 · {_title}**",
         "───────────────",
         f"**进场** {fmt_price(sig.entry)}",
         f"**止损** {fmt_price(sl)}（{_pct_sl}）",
         f"**目标** {fmt_price(sig.tp)}（{_pct_tp}）",
         f"**盈亏比** 1 : {rr:.1f}"]
    if liq:
        L.append(f"**爆仓价** {fmt_price(liq)}")
    L += ["───────────────",
          f"**依据** {simplify_reason(sig.reason)}",
          f"**下单** {size['lots']}张 · {size['notional']:.0f}U名义 · 保证金{size['margin']:.1f}U · {size['leverage']}倍"]
    if DRY_RUN:
        L += ["", "> 模拟观察，未实际下单"]
    return "\n".join(L)


def why_no_signal(ee):
    """把入场引擎最后的进度翻译成"卡在哪一步" (★仅写运行日志, 不推送企业微信)"""
    st = getattr(ee, "last_steps", None) or {}
    if not st.get("htf_trend"):
        return "卡① 背景: 1H 结构方向未确立"
    if not st.get("trigger"):
        return "卡② 入场: 15m 未出现同向 CHoCH(或不够新)"
    return "②之后被拦(止损/止盈/RR 不达标)"

def _hist_inst(h):
    """平仓记录品种: 新记录带 inst, 旧记录从 detail 兜底解析"""
    s = h.get("inst") or h.get("detail") or ""
    return "BTC" if "BTC" in s else "黄金"


def _hist_dir(h):
    """平仓记录方向: 新记录带 direction, 旧记录从 detail 兜底解析"""
    return h.get("direction") or ("long" if "LONG" in (h.get("detail") or "") else "short")


def build_daily_report(state, now_bj):
    """每日日报 (北京时间早8点后首次运行推送)
    2026-10-03 定版: ① 24h战绩(总计 + 分品种 笔数/方向/盈亏/胜率) ② 持仓 ③ 诊断"""
    day = now_bj.strftime("%m-%d")
    hist = [h for h in state.get("history", []) if time.time() - h.get("ts", 0) < 86400]
    # 只统计真实成交的平仓(历史遗留的"未成交·作废"记录不计入笔数/胜率)
    exs = [h for h in hist if h["type"] == "exit"
           and not h.get("void") and "作废" not in (h.get("detail") or "")]
    pos = state.get("positions", [])

    L = [f"🌙 **暗夜猎手 · 日报 {day}**", ""]

    # ① 24h 战绩(核心) —— 总计 + 分品种
    if exs:
        pnl = sum(h.get("pnl", 0) for h in exs)
        wins = sum(1 for h in exs if h.get("pnl", 0) > 0)
        L.append(f"**📊 24h** {len(exs)}笔 · 胜{wins}/{len(exs)} · **{pnl:+.2f}U**")
        agg = {}
        for h in exs:
            a = agg.setdefault(_hist_inst(h), {"n": 0, "w": 0, "p": 0.0, "L": 0, "S": 0})
            a["n"] += 1
            a["w"] += 1 if h.get("pnl", 0) > 0 else 0
            a["p"] += h.get("pnl", 0)
            if _hist_dir(h) == "long":
                a["L"] += 1
            else:
                a["S"] += 1
        for nm in ("BTC", "黄金"):
            a = agg.get(nm)
            if not a:
                continue
            _d = (f"多{a['L']}" if a["L"] else "") + (f"空{a['S']}" if a["S"] else "")
            L.append(f"· **{nm}** {a['n']}笔 {_d} | {a['p']:+.2f}U | 胜{a['w']}/{a['n']}")
    else:
        L.append("**📊 24h** 无平仓")

    # ② 持仓(排在战绩之后)
    L.append("")
    if pos:
        for i, p in enumerate(pos):
            nm = "BTC" if "BTC" in p["inst"] else "黄金"
            sd = "做多" if p["direction"] == "long" else "做空"
            _ex = " | 已挂单✅" if (p.get("tp_algo_id") or p.get("sl_algo_id")) else ""
            tag = "**💰 持仓** " if i == 0 else "　"
            L.append(f"{tag}{nm}{sd} | 进{fmt_price(p['entry'])} 损{fmt_price(p['sl'])} "
                     f"标{fmt_price(p['tp'])}{_ex}")
    else:
        L.append("**💰 持仓** 空仓")

    # ③ 诊断(一行结论)
    try:
        from auto_calibrator import analyze
        d = analyze(state.get("history", []))
        L += ["", f"**🔬 诊断** {d.get('brief') or d['summary']}"]
    except Exception as e:
        print(f"[诊断异常] {e}")

    L += ["", f"_{C.MARGIN_PER_TRADE:.0f}U/单 · {C.LEVERAGE_FIXED}倍_"]
    return "\n".join(L)

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
    # ★2026-10-03 未来函数修复: 只保留已收盘K线(row[7]=="true"), 剔除正在形成的当根
    _out = []
    for d in r.json():
        if len(d) > 7 and str(d[7]) == "true":
            _ts = int(d[0])
            if _ts > 1_000_000_000_000:       # 统一成【秒】(与 OKX/回测口径一致)
                _ts //= 1000
            _out.append(Candle(_ts, float(d[5]), float(d[3]), float(d[4]), float(d[2]), float(d[1])))
    return _out

def fetch_candles(client, inst_id, limit=300, tf=None):
    """数据源路由 + 故障自愈 (2026-10-03 用户裁定: 信号用【WEEX 合约】, 模拟盘交易仍在 OKX)
    链路: WEEX 合约 → OKX → Gate 现货, 逐级自愈; 每一级都会打印实际用的源"""
    tf = tf or C.BASE_TF
    gate_tf = {"1H": "1h", "4H": "4h", "15m": "15m", "5m": "5m"}.get(tf, "1h")
    if os.environ.get("DATA_SOURCE") == "gate":          # 仅离线诊断用
        return _fetch_gate(inst_id, limit, gate_tf)
    # ① WEEX 合约 (与回测同一口径)
    try:
        rows = weex_client.get_candles(inst_id, tf, limit)
        if rows:
            return [Candle(*r) for r in rows]
        raise RuntimeError("返回空")
    except Exception as e:
        print(f"[自愈] WEEX({tf})失败({type(e).__name__}): {str(e)[:120]} → 切 OKX")
    # ② OKX (交易所在所, 兼作备用)
    try:
        return client.get_candles(inst_id, tf, limit)
    except Exception as e:
        print(f"[自愈] OKX({tf})失败({type(e).__name__}) → 切 Gate")
    # ③ Gate 现货 (最后兜底; XAU 走 PAXG 代理, 与前两级有基差)
    k = _fetch_gate(inst_id, limit, gate_tf)
    print(f"[自愈] Gate 备用源成功: {len(k)}根")
    return k

def get_htf_trend(client, inst_id, candles_base, htf="4H"):
    """大级别趋势 = 【结构方向】(课程原文: 趋势看截取/BOS 的方向, 不是"相对几根K线涨跌")
    用高一级周期的结构状态机方向 se.trend; 判不出 → 返回 None(不开单)
    ★口径(2026-10-03 用户裁定): CHoCH 的语义是【反转预警】(市场"可能"反转, 不是一定反转);
      当前实现仍是 CHoCH 即时翻转 trend —— 是否改为"预警 + 等反向 BOS 确认"待用户看回测后决定
    2026-10-02 按原文重建: 废弃原先的"最新收盘 vs 20根前收盘"两点比价, 以及 1H 斜率回退"""
    try:
        c = fetch_candles(client, inst_id, limit=200, tf=htf)
        if len(c) >= 60:
            _se = StructureEngine(); _se.process(c)
            if _se.trend in ("up", "down"):
                return _se.trend, htf
            print(f"[HTF] {htf} 结构方向未确立 → 本轮不做")
    except Exception as e:
        print(f"[HTF] {htf}获取失败({type(e).__name__})")
    return None, htf

def resolve_leverage(client, inst_id, desired, td_mode, pos_side):
    """设置杠杆并返回实际生效值。各品种上限不同(XAU实测最高50), 100被拒(59102)时逐级下调。"""
    for lev in (desired, 50, 20, 10, 5, 2):
        if lev > desired:
            continue
        try:
            r = client.set_leverage(inst_id, lev, td_mode, pos_side=pos_side)
        except Exception as e:
            print(f"[杠杆] {inst_id} {lev}x 异常 {type(e).__name__}")
            continue
        if r.get("code") == "0":
            if lev != desired:
                print(f"[杠杆] {inst_id} {desired}x被拒, 实际使用 {lev}x")
            return lev
    print(f"[杠杆] {inst_id} 各档位均失败, 兜底10x")
    return 10

def real_margin_per_contract(client, inst_id, price, td_mode="isolated"):
    """★2026-10-04 方案A(用户裁定): 返回交易所口径下【每张合约实际占用保证金】(USDT)。
    优先级:
      ① 实测持仓反推 —— 用 margin/|pos| 得"每张占用", 再按"有效倍率"换算到当前价
      ② 梯度保证金表 imr (/public/position-tiers) —— 官方初始保证金率
      ③ 都取不到 → None(调用方退回"名义÷杠杆"估算)
    理由: OKX 对 XAU 实收保证金 ≠ 名义÷设置杠杆(账户设50却按≈25收, 且会自己变),
          只有按【实际占用】换算, 张数乘出来才真是 5U。"""
    ctval = (C.INST_SPECS.get(inst_id) or {}).get("ctVal")
    if not ctval:
        return None
    try:
        for p in (client.get_positions(inst_id).get("data") or []):
            pos = abs(float(p.get("pos") or 0))
            mgn = float(p.get("margin") or 0)
            apx = float(p.get("avgPx") or 0) or price
            if pos > 0 and mgn > 0:
                eff = ctval * apx * pos / mgn                       # 实测有效倍率
                if eff > 0:
                    per = ctval * price / eff
                    print(f"[保证金] {inst_id} 实测每张占用 {per:.6f}U "
                          f"(有效倍率 eff={eff:.2f}, 持仓{pos}张 margin={mgn:.4f})")
                    return per
    except Exception as e:
        print(f"[保证金] {inst_id} 实测持仓读取失败 {type(e).__name__}")
    try:
        imr = client.position_tier_imr(inst_id, td_mode)
        if imr and imr > 0:
            if imr > 1:                                             # 部分接口返回百分比
                imr /= 100.0
            per = imr * ctval * price
            print(f"[保证金] {inst_id} 梯度表 imr={imr} → 每张占用 {per:.6f}U")
            return per
    except Exception as e:
        print(f"[保证金] {inst_id} 梯度表读取失败 {type(e).__name__}")
    print(f"[保证金] {inst_id} 取不到实际占用, 退回 名义÷杠杆 估算")
    return None


# ---------- 交易所端止盈止损 (reduceOnly 条件单) ----------
def adaptive_sl(entry_px, direction, sig_sl, sig_entry, leverage):
    """止损口径 (2026-10-03 用户裁定【B/C】): **严格执行 FVG(结构)止损**。
    结构止损随"真实成交价"平移(保持 sig_sl 相对 sig_entry 的距离), 杠杆不参与止损计算。
    ★爆仓价一律以【交易所返回的 liqPx】为准 —— 本地**不再估算**(2026-10-03 用户裁定:
      "爆仓价格按照交易所的价格, 不要自己臆想")。
    返回 (结构止损价, None)  # 第二项已废弃, 仅为兼容旧调用点保留"""
    struct_sl = sig_sl + (entry_px - sig_entry)
    return struct_sl, None


def tp_from_rr(entry_px, direction, sl_px, rr=None):
    """止盈 = 进场价 ± rr × 风险距离 (固定盈亏比)
    ★2026-10-04 用户裁定: 止盈不再挂"对侧结构点/腿的另一端", 改为我们自己设的盈亏比(C.TP_RR=2.0)。
    用【真实成交价 + 实际止损价】算 → 名义RR与实际RR一致(顺带修掉"止损平移了、止盈没平移"的毛病)。"""
    rr = C.TP_RR if rr is None else rr
    risk = abs(entry_px - sl_px)
    return entry_px + rr * risk if direction == "long" else entry_px - rr * risk


def _ex_liqpx(client, inst_id, pos_side):
    """取【交易所返回的爆仓价 liqPx】(2026-10-03 用户裁定: 不允许本地臆算)。
    取不到(净持仓模式/演示盘未返回等) → 返回 None, 由调用方如实告知, 绝不编一个数。"""
    try:
        rows = [x for x in (client.get_positions(inst_id=inst_id).get("data") or [])
                if float(x.get("pos") or 0) != 0]
        if not rows:
            return None
        pick = next((x for x in rows if x.get("posSide") == pos_side), None) or rows[0]
        v = float(pick.get("liqPx") or 0)
        return v if v > 0 else None
    except Exception:
        return None
def _place_exchange_tpsl(client, inst_id, pos_side, sz, td_mode, tp, sl):
    """把止盈/止损真实挂到交易所, 返回 algoId
    ★严格校验(2026-10-02): 必须 code=0 且 sCode=0 且 algoId 非空 才算挂上; 否则不写id并记入err(防"假成功")
    返回 {"tp_algo_id":.., "sl_algo_id":.., "err":[...]}"""
    out = {"tp_algo_id": None, "sl_algo_id": None, "err": []}
    for key, fn, px in (("tp_algo_id", client.place_tp_order, tp), ("sl_algo_id", client.place_sl_order, sl)):
        _lb = "TP" if key.startswith("tp") else "SL"
        try:
            r = fn(inst_id, pos_side, sz, td_mode, px)
            dd = ((r.get("data") or [{}])[0] or {})
            print(f"[挂{_lb}] {inst_id} sz={sz} px={px} code={r.get('code')} sCode={dd.get('sCode')} "
                  f"msg={r.get('msg') or dd.get('sMsg')} | {json.dumps(r, ensure_ascii=False)[:300]}")
            if r.get("code") == "0" and dd.get("sCode") == "0" and dd.get("algoId"):
                out[key] = dd.get("algoId")
            else:
                out["err"].append(f"{_lb}[{dd.get('sCode') or r.get('code')}:{dd.get('sMsg') or r.get('msg')}]")
        except Exception as e:
            out["err"].append(f"{_lb}[exc:{e}]")
            print(f"[挂{_lb}异常] {inst_id} {e}")
    return out

def _cancel_exchange_tpsl(client, inst_id, p):
    """撤掉持仓对应的交易所止盈/止损挂单"""
    for k in ("tp_algo_id", "sl_algo_id"):
        aid = p.get(k)
        if aid:
            try:
                client.cancel_algo(inst_id, aid)
            except Exception as e:
                print(f"[撤单异常] {k} {e}")
            p[k] = None

def _close_position_now(client, state, p, sym_cfg, reason):
    """撤交易所止盈止损 → 市价平仓 → 以交易所真实成交价结算 → 从state移除; 返回推送文本"""
    inst_id = p["inst"]
    _psx = "long" if p["direction"] == "long" else "short"
    exit_px = p.get("entry"); _src = "按K线结构"
    if not DRY_RUN:
        _cancel_exchange_tpsl(client, inst_id, p)
        side = "sell" if p["direction"] == "long" else "buy"
        try:
            resp = client.close_position(inst_id, side, p["size"],
                                         td_mode=sym_cfg.get("td_mode", "isolated"), pos_side=_psx)
            _cod = ((resp.get("data") or [{}])[0] or {}).get("ordId")
            for _ in range(5):
                _od = (client.get_order(inst_id, _cod).get("data") or [{}])[0]
                if float(_od.get("accFillSz") or 0) > 0 or _od.get("state") in ("filled", "canceled"):
                    exit_px = float(_od.get("avgPx") or exit_px); _src = "交易所成交价"; break
                time.sleep(0.8)
        except Exception as e:
            print(f"[平仓异常] {inst_id} {e}")
    ctval = C.INST_SPECS.get(inst_id, {}).get("ctVal", 0)
    sign = 1 if p["direction"] == "long" else -1
    pnl = (exit_px - p["entry"]) * sign * p["size"] * ctval
    _nm = "BTC" if "BTC" in inst_id else "黄金"
    _sd = "多单" if p["direction"] == "long" else "空单"
    _pf = C.STRATEGY_PROFILES.get(p.get("profile", ""), {}).get("label", p.get("profile", ""))
    state.setdefault("history", []).append({"type": "exit", "ts": time.time(), "profile": p.get("profile", ""),
        "pnl": round(pnl, 2), "entry": round(p["entry"], 2), "exit": round(exit_px, 2),
        "detail": f"[{_pf}] {_nm} {p['direction'].upper()} {pnl:+.2f}U"})
    if p in state.get("positions", []):
        state["positions"].remove(p)
    _ico = "✅" if pnl > 1e-9 else ("➖" if pnl > -1e-9 else "❌")
    return (f"{_ico} **已平仓 · {_nm} {_sd} [{_pf}]**\n"
            f"**进出** {fmt_price(p['entry'])} → {fmt_price(exit_px)}（{_src}）\n"
            f"**盈亏** {pnl:+.2f}U\n**原因** {reason}")

def _last_realized(client, inst_id, pos_side):
    """取该品种最近一笔已平仓的交易所实现盈亏与平仓均价(用于'交易所端自动平仓'对账)"""
    try:
        h = client._get("/api/v5/account/positions-history",
                        {"instType": "SWAP", "instId": inst_id, "limit": "5"})
        for x in (h.get("data") or []):
            if x.get("posSide") == pos_side:
                return float(x.get("realizedPnl") or 0), float(x.get("closeAvgPx") or 0)
    except Exception as e:
        print(f"[对账] 历史查询失败 {e}")
    return 0.0, None

def run_once():
    state = load_state()
    print(f"[暗夜猎手 v3] 周期链={list(PROFILES)} DRY_RUN={DRY_RUN} 特性=两级别(1H+15m)+开仓当根不判出场")
    print(f"[数据源] 信号/回测 = WEEX 合约 ({weex_client.HOST}) | 交易 = OKX 模拟盘 | DRY_RUN={DRY_RUN}")
    now_bj = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    # 节流: 距上次运行<25分钟则跳过 (配合cron-job.org每30分钟触发, 控制Actions额度)
    last = state.get("last_run_ts", 0)
    if time.time() - last < 3 * 60:   # 2026-10-02: 25分钟→3分钟, 支持高频轮询攒样本(仅防并发重复触发)
        print(f"[节流跳过] 距上次运行{int((time.time()-last)/60)}分钟 <3分钟")
        return
    state["last_run_ts"] = time.time()
    today = now_bj.date().isoformat()
    if state.get("daily", {}).get("date") != today:
        state["daily"] = {"date": today, "trades": 0, "by_profile": {pn: 0 for pn in PROFILES}}
        state["run_count_today"] = 0
    state["daily"].setdefault("by_profile", {pn: 0 for pn in PROFILES})
    state["run_count_today"] = state.get("run_count_today", 0) + 1
    # ---- 兼容: 周期链改名(旧 4H+1H/4H+15m → 4-1-15), 单链下自动迁移历史 state, 防旧持仓失管 ----
    if len(PROFILES) == 1:
        _only = next(iter(PROFILES))
        for _p in list(state.get("positions", [])) + list(state.get("pending_entries", [])):
            if _p.get("profile") not in PROFILES:
                _p["profile"] = _only
        _bp = state["daily"].get("by_profile", {})
        state["daily"]["by_profile"] = {_only: sum(v for v in _bp.values() if isinstance(v, int))}

    client = OkxClient(simulated=True)

    # ★2026-10-03 图表推送测试开关: PUSH_TEST=1 → 只推一张测试图, **不做任何交易**(提前返回, 不改状态)
    if os.environ.get("PUSH_TEST") == "1":
        push("🧪 **图表推送测试** — 本条为测试消息，未做任何交易")
        push_chart(client, "BTC-USDT-SWAP", [], "🧪 图表推送测试")
        return

    reports = []
    market_notes = []
    def add(cat, txt):
        reports.append((cat, txt))

    # ---- 处理"上轮挂单待成交"的入场单 (XAU演示盘成交慢, 挂单后下轮确认) ----
    if state.get("pending_entries") and not DRY_RUN:
        _keep = []
        for pe in state["pending_entries"]:
            _pinst = pe["inst"]
            _pl = C.STRATEGY_PROFILES.get(pe.get("profile", ""), {}).get("label", pe.get("profile", ""))
            _nm = "BTC" if "BTC" in _pinst else "黄金"
            try:
                od = (client.get_order(_pinst, pe["ord_id"]).get("data") or [{}])[0]
            except Exception as e:
                print(f"[待成交查询异常] {_pinst} {e}"); _keep.append(pe); continue
            _st = od.get("state")
            _fl = float(od.get("accFillSz") or 0)
            _avg = float(od.get("avgPx") or pe.get("signal_entry", 0))
            # 兼容演示盘"已成交但订单状态未更新" → 用持仓反查
            if _fl <= 0 and _st not in ("canceled", "filled"):
                try:
                    _pp = [x for x in (client.get_positions(inst_id=_pinst).get("data") or [])
                           if x.get("posSide") == ("long" if pe["direction"] == "long" else "short")
                           and float(x.get("pos") or 0) > 0]
                except Exception:
                    _pp = []
                _tracked = any(x["inst"] == _pinst and x["direction"] == pe["direction"] for x in state.get("positions", []))
                if _pp and not _tracked:
                    _fl = float(_pp[0].get("pos") or 0)
                    _avg = float(_pp[0].get("avgPx") or _avg)
                    print(f"[待成交] {_pinst} 订单仍live但已有持仓 → 判定已成交 {_fl}@{_avg}")
            if _fl > 0:
                _slf = adaptive_sl(_avg, pe["direction"], pe.get("sl", pe.get("signal_entry", _avg)),
                                   pe.get("signal_entry", _avg), pe["lev"])[0]
                _psx = "long" if pe["direction"] == "long" else "short"
                _tdx = C.SYMBOLS.get(_pinst, {}).get("td_mode", "isolated")
                _tpf = tp_from_rr(_avg, pe["direction"], _slf)          # 止盈按实际成交价+实际止损重算(1:TP_RR)
                _po = {"inst": _pinst, "direction": pe["direction"], "entry": _avg, "sl": _slf, "tp": _tpf,
                       "size": _fl, "ratio": 1.0, "risk_free": False, "tp1_hit": False,
                       "leverage": pe["lev"], "profile": pe.get("profile", "4H+1H"),
                       "run_id": state["last_run_ts"], "opened": int(time.time())}
                _po.update(_place_exchange_tpsl(client, _pinst, _psx, _fl, _tdx, _tpf, _slf))
                state["positions"].append(_po)
                state["daily"]["trades"] = state["daily"].get("trades", 0) + 1
                state["daily"].setdefault("by_profile", {})
                _pf = pe.get("profile", "4H+1H")
                state["daily"]["by_profile"][_pf] = state["daily"]["by_profile"].get(_pf, 0) + 1
                _erl = _po.get("err") or []
                _tgt = (f"> 🎯 交易所已挂 止盈 {fmt_price(pe['tp'])} / 止损 {fmt_price(_slf)}" if not _erl else
                        f"> ❌ 交易所挂单**未挂上** {'；'.join(_erl)}（本地记录 止盈 {fmt_price(pe['tp'])} / 止损 {fmt_price(_slf)}，请手动确认）")
                add("铁律", f"✅ **挂单成交建仓 · {_nm} {_pl}**\n"
                               f"> 成交 {_fl}张 @{_avg:,.1f}\n" + _tgt)
            elif _st == "canceled":
                add("巡检", f"⚠️ **挂单已取消 · {_nm} {_pl}**（交易所端撤销，未成交）\n"
                               f"> {pe.get('size')}张 · 信号进场 {fmt_price(pe.get('signal_entry', 0))}")
            elif time.time() - pe.get("ts", 0) > 900:
                try:
                    client.cancel_order(_pinst, pe["ord_id"])
                except Exception as e:
                    print(f"[撤待成交异常] {e}")
                add("巡检", f"⚠️ **挂单已撤 · {_nm} {_pl}**（挂满15分钟未成交）\n"
                               f"> {pe.get('size')}张 · 信号进场 {fmt_price(pe.get('signal_entry', 0))}\n"
                               f"> 已撤销，本轮不开仓")
            else:
                _keep.append(pe)
                add("巡检", f"⏳ **{_nm} {_pl}** 挂单待成交中（已等待{int((time.time() - pe.get('ts', 0)) / 60)}分钟）")
        state["pending_entries"] = _keep

    # ---- 对账: 与交易所持仓核对(防状态漂移) ----
    # 交易所端触发的止盈/止损会把仓位平掉, 但引擎不知情 → 这里同步, 保证报表=交易所
    if not DRY_RUN:
        _lp = {}
        for _ in range(3):                     # 3次取并集, 规避接口偶发空返回导致误判
            try:
                for x in (client.get_positions().get("data") or []):
                    _kk = (x["instId"], x.get("posSide"))
                    _lp[_kk] = max(_lp.get(_kk, 0), float(x.get("pos") or 0))
            except Exception as e:
                print(f"[对账] 查询失败 {e}")
            time.sleep(0.5)
        print(f"[对账] 交易所持仓={_lp} 本地={[(x['inst'], x['direction'], x.get('size')) for x in state.get('positions', [])]}")
        # ★张数同步(2026-10-02): 本地与交易所不一致(如历史"部分平仓"残留 0.295 这类非整倍张数)
        #   → 以交易所为准, 并撤掉旧TP/SL(由持仓循环的自愈按正确张数重挂)
        for _p in list(state.get("positions", [])):
            _key = (_p["inst"], "long" if _p["direction"] == "long" else "short")
            _exz = _lp.get(_key, 0)
            if _exz > 0 and abs(float(_p.get("size", 0)) - _exz) > 1e-9:
                print(f"[对账] {_p['inst']} 本地张数 {_p.get('size')} → 交易所 {_exz}, 已同步并准备重挂TP/SL")
                _cancel_exchange_tpsl(client, _p["inst"], _p)
                _p["size"] = _exz
        _state_keys = set()
        for _p in list(state.get("positions", [])):
            _key = (_p["inst"], "long" if _p["direction"] == "long" else "short")
            _state_keys.add(_key)
            if _lp.get(_key, 0) > 0:
                continue
            _nm = "BTC" if "BTC" in _p["inst"] else "黄金"
            _pf = C.STRATEGY_PROFILES.get(_p.get("profile", ""), {}).get("label", _p.get("profile", ""))
            _rp, _cpx = _last_realized(client, _p["inst"], _key[1])
            state["positions"].remove(_p)
            state.setdefault("history", []).append({"type": "exit", "ts": time.time(),
                "profile": _p.get("profile", ""), "pnl": round(_rp, 2),
                "entry": round(_p["entry"], 2), "exit": round(_cpx or _p["entry"], 2),
                "detail": f"[{_pf}] {_nm} {_p['direction'].upper()} {_rp:+.2f}U(交易所端)"})
            add("巡检", f"🏁 **交易所端已平仓 · {_nm} {_pf}**\n"
                           f"> 交易所止盈/止损已触发，引擎已同步\n"
                           f"> **进出** {fmt_price(_p['entry'])} → {fmt_price(_cpx or _p['entry'])}\n"
                           f"> **盈亏** {_rp:+.2f}U（交易所实现盈亏）")
            queue_chart(_p["inst"], [(_p["entry"], "进场", "#1f6feb"),
                                     (_cpx or _p["entry"], "离场", "#7b1fa2")],
                        title=f"平仓 · {_p['direction'].upper()} · {_rp:+.2f}U")
        for _k, _sz in _lp.items():
            if _sz > 0 and _k not in _state_keys:
                # ★接管游离持仓(2026-10-02 用户裁定A): 交易所持仓存在但本地无记录 → 按交易所均价重建并补挂TP/SL
                _ins, _psd = _k[0], _k[1]
                _nmx = "BTC" if "BTC" in _ins else "黄金"
                _dirx = "long" if _psd == "long" else "short"
                _levx = C.INST_LEVER.get(_ins, C.LEVERAGE_FIXED)
                _tdx = C.SYMBOLS.get(_ins, {}).get("td_mode", "isolated")
                try:
                    _pd = next((x for x in (client.get_positions(inst_id=_ins).get("data") or [])
                                if x.get("posSide") == _psd and float(x.get("pos") or 0) > 0), {})
                except Exception:
                    _pd = {}
                _epx = float(_pd.get("avgPx") or _pd.get("markPx") or 0)
                if _epx <= 0:
                    add("巡检", f"⚠️ **交易所端游离持仓** {_ins} {_psd} {_sz} — 取不到开仓均价，未接管，请核对")
                    continue
                # 孤儿仓(原始信号已丢失, 无 FVG 依据) → 用【交易所返回的爆仓价 liqPx】做保命止损
                # ★2026-10-03 用户裁定: 爆仓价必须取交易所实际值, 本地不估算; 取不到就不擅自接管
                _lqx = float(_pd.get("liqPx") or 0)
                if _lqx <= 0:
                    add("巡检", f"⚠️ **交易所端游离持仓** {_ins} {_psd} {_sz} — 交易所未返回爆仓价(liqPx)，未接管，请手动处理")
                    continue
                _slx = _lqx * (1 - C.LIQ_BUFFER_PCT) if _dirx == "long" else _lqx * (1 + C.LIQ_BUFFER_PCT)
                _rk = abs(_epx - _slx)
                _tpx = _epx + _rk * C.RR_MIN_GROWTH if _dirx == "long" else _epx - _rk * C.RR_MIN_GROWTH
                _np = {"inst": _ins, "direction": _dirx, "entry": round(_epx, 4), "sl": round(_slx, 4),
                       "tp": round(_tpx, 4), "size": _sz, "ratio": 1.0, "risk_free": False, "tp1_hit": False,
                       "leverage": _levx, "profile": next(iter(PROFILES)), "adopted": True,
                       "run_id": state["last_run_ts"], "opened": int(time.time()), "adopted": True}
                _np.update(_place_exchange_tpsl(client, _ins, _psd, _sz, _tdx, _tpx, _slx))
                state["positions"].append(_np)
                _erlx = _np.get("err") or []
                print(f"[接管] {_ins} {_psd} {_sz}@{_epx} TP={_tpx} SL={_slx} err={_erlx}")
                _plist = []
                if _np.get("tp_algo_id"): _plist.append(f"止盈 {fmt_price(_tpx)}")
                if _np.get("sl_algo_id"): _plist.append(f"止损 {fmt_price(_slx)}")
                _ptxt = ("已补挂 " + " / ".join(_plist)) if _plist else "⚠️ 未挂上任何保护单"
                add("巡检", f"🛡️ **接管交易所游离持仓 · {_nmx} {_dirx.upper()}**\n"
                             f"> {_sz}张 @{_epx:,.1f}（交易所均价）· 杠杆 {_levx}x\n"
                             f"> {_ptxt}" + ("" if not _erlx else f"\n> ⚠️ 交易所回执：{'；'.join(_erlx)}"))
        # 顺带清理"无持仓"的孤立止盈/止损挂单
        try:
            for _a in (client.get_algo_pending().get("data") or []):
                if _lp.get((_a.get("instId"), _a.get("posSide")), 0) <= 0:
                    client.cancel_algo(_a.get("instId"), _a.get("algoId"))
                    print(f"[清理孤立挂单] {_a.get('instId')} {_a.get('algoId')}")
        except Exception as e:
            print(f"[孤立挂单清理异常] {e}")

    # ---- 同品种同向只留一个仓 (用户规则): 多余同向仓按"等级优先"清理 ----
    if not DRY_RUN:
        _grp = {}
        for _p in list(state.get("positions", [])):
            _grp.setdefault((_p["inst"], _p["direction"]), []).append(_p)
        for _key, _lst in _grp.items():
            if len(_lst) < 2:
                continue
            _lst.sort(key=lambda x: abs(x["tp"] - x["entry"]) / max(abs(x["entry"] - x["sl"]), 1e-9), reverse=True)
            for _drop in _lst[1:]:
                add("铁律", _close_position_now(client, state, _drop,
                                                   C.SYMBOLS.get(_drop["inst"], {}), "同向重复仓清理(只留一个)"))

    for inst_id, sym_cfg in C.SYMBOLS.items():
        if not sym_cfg.get("enabled"):
            continue

        # ---- 逐方案运行 (4+1 / 4+15 并行) ----
        for pname, prof in PROFILES.items():
            plabel = prof.get("label", pname)
            with profile_ctx(prof):
                try:
                    candles = fetch_candles(client, inst_id, tf=prof["base_tf"])
                except Exception as e:
                    add("巡检", f"❌ `{plabel}` {inst_id} 行情失败: {e}"); continue
                if len(candles) < 120:
                    continue
                se, le = StructureEngine(), LiquidityEngine()
                se.process(candles); le.process(candles)
                htf, htf_src = get_htf_trend(client, inst_id, candles, htf=prof.get("htf", "4H"))
                # 小级别(下一级): 课程C1"截取后切小级别看反转预警/回踩" → 反转预警与FVG都在此级别判定
                ltf_se = ltf_le = ltf_candles = None
                _ltf = prof.get("ltf")
                if _ltf:
                    try:
                        _lc = fetch_candles(client, inst_id, limit=200, tf=_ltf)
                        if len(_lc) >= 60:
                            ltf_candles = _lc
                            ltf_se = StructureEngine(); ltf_se.process(_lc)
                            ltf_se.last_idx = len(_lc) - 1
                            ltf_le = LiquidityEngine(); ltf_le.process(_lc)
                    except Exception as e:
                        print(f"[LTF] {_ltf}获取失败({type(e).__name__})")
                px = candles[-1].close

                # ---- 市场状态采集(供日报) ----
                _nmk = "BTC" if "BTC" in inst_id else "黄金"
                _trend = {"up": "上涨", "down": "下跌", None: "震荡"}.get(se.trend, "不明")
                _af = le.snapshot()["active_fvgs"]
                _fvg = f"{_af[-1]['bottom']:,.0f}~{_af[-1]['top']:,.0f}" if _af else "无"
                _lv = le.sweeps[-1] if le.sweeps else None
                _sweep_txt = f"{'扫上' if _lv[1]=='up' else '扫下'}{_lv[2]:,.0f}({_lv[3]}点)" if _lv else "无近期截取"
                market_notes.append(f"· **{_nmk}** {_trend} | FVG {_fvg} | {_sweep_txt}")

                # ---- 风控/连亏保护 (按方案独立) ----
                risk = RiskManager(capital_usd=CAPITAL_USD, risk_score=3)
                risk.daily_trades = state["daily"]["by_profile"].get(pname, 0)
                _rec = [h for h in state.get("history", [])
                        if h.get("type") == "exit" and h.get("profile") == pname][-3:]
                halt_new = len(_rec) == 3 and all(h.get("pnl", 0) <= 0 for h in _rec)
                if halt_new:
                    print(f"[连亏保护] {plabel} 最近3笔全亏, 本轮不开新仓")

                # ---- 新信号检测 (指纹含方案, 每方案独立去重) ----
                ee = EntryEngine()
                sig = ee.evaluate(candles, se, le, htf, bar_i=len(candles) - 1, ltf_se=ltf_se, ltf_le=ltf_le, ltf_candles=ltf_candles)
                if sig is None:
                    print(f"[无信号] {inst_id} {plabel} → {why_no_signal(ee)}")
                fp = None
                if sig:
                    # 指纹用稳定特征: 方案+品种+方向+止损结构位(取整到10美元, 抗ATR微漂移)
                    fp = f"{pname}|{inst_id}|{sig.direction}|{round(sig.sl / 10) * 10}"
                    if fp in state.get("pushed_signals", []):
                        print(f"[跳过重复信号] {fp}")
                        sig = None
                # 同品种「同方向」只留一仓(用户规则): 已有同向仓/挂单 → 直接忽略新信号, 不换仓; 不同方向可并存
                _same = next((p for p in state.get("positions", [])
                              if p["inst"] == inst_id and p["direction"] == sig.direction), None) if sig else None
                _same_pend = any(pe.get("inst") == inst_id and pe.get("direction") == sig.direction
                                 for pe in state.get("pending_entries", [])) if sig else False
                if sig and (_same_pend or _same):
                    # 同品种同向只留一仓: 已有同向仓/挂单 → 忽略新信号(不再分等级, 故不换仓)
                    print(f"[跳过] {plabel} {inst_id} 已有同向仓/挂单, 不重复开仓")
                    sig = None

                if sig:
                    ok, detail = risk.check_gates(sig)
                    if ok and halt_new:
                        add("巡检", f"🛑 **`{plabel}` 连亏保护** 最近3笔全亏，跳过开仓（{inst_id}）")
                        ok = False
                    if ok:
                        _ps = "long" if sig.direction == "long" else "short"
                        _td = sym_cfg.get("td_mode", "isolated")
                        # 杠杆: 各品种实际上限不同(BTC=100, XAU=50); 写死100会被OKX拒(59102)
                        want_lev = C.INST_LEVER.get(inst_id, C.LEVERAGE_FIXED)
                        used_lev = resolve_leverage(client, inst_id, want_lev, _td, _ps) if not DRY_RUN else want_lev
                        size = size_fixed_margin(px, inst_id, leverage=used_lev,
                                                 mgn_per_contract=(None if DRY_RUN else
                                                                   real_margin_per_contract(client, inst_id, px, _td)))
                        print(f"[仓位] {inst_id} {size['lots']}张 名义{size['notional']}U "
                              f"保证金{size['margin']}U (来源={size.get('margin_src')})")
                        sl_use, liq_px = adaptive_sl(sig.entry, sig.direction, sig.sl, sig.entry, used_lev)
                        line = format_signal(inst_id, sig, size, sl_use, liq_px, prof_label=plabel)
                        _opened = False
                        if not DRY_RUN:
                            side = "buy" if sig.direction == "long" else "sell"
                            resp = client.place_order(inst_id, side, size["lots"], td_mode=_td, pos_side=_ps)
                            dd = (resp.get("data") or [{}])[0]
                            print(f"[下单] {inst_id} {side} {size['lots']} lev={used_lev} -> {json.dumps(resp, ensure_ascii=False)[:280]}")
                            # ★核心1: 同时校验 code 与 订单级 sCode(被拒单不能记持仓)
                            if resp.get("code") == "0" and dd.get("sCode") == "0":
                                ordid = dd.get("ordId")
                                # ★核心2: 市价单可能"已接受但未成交"(真成交才算开仓), 轮询确认
                                stt, fl, avg = "live", 0.0, sig.entry
                                for _ in range(5):
                                    od = (client.get_order(inst_id, ordid).get("data") or [{}])[0]
                                    stt = od.get("state"); fl = float(od.get("accFillSz") or 0); avg = float(od.get("avgPx") or sig.entry)
                                    if fl > 0 or stt in ("filled", "partially_filled", "canceled"):
                                        break
                                    time.sleep(0.8)
                                if fl > 0:
                                    sl_fill = adaptive_sl(avg, sig.direction, sig.sl, sig.entry, used_lev)[0]  # 止损按"真实成交价"平移重算
                                    tp_fill = tp_from_rr(avg, sig.direction, sl_fill)                        # 止盈 = 1:TP_RR(同口径)
                                    posobj = {"inst": inst_id, "direction": sig.direction,
                                              "entry": avg, "sl": sl_fill, "tp": tp_fill,
                                              "size": fl, "ratio": 1.0,
                                              "risk_free": False, "tp1_hit": False,
                                              "leverage": used_lev, "profile": pname,
                                              "run_id": state["last_run_ts"],
                                              "opened": int(time.time())}
                                    # ★ 把止盈/止损真实挂到交易所(reduceOnly条件单), App可见
                                    posobj.update(_place_exchange_tpsl(client, inst_id, _ps, fl, _td, tp_fill, sl_fill))
                                    # ★爆仓价: 取【交易所返回的 liqPx】(用户裁定: 不本地臆算; 取不到就如实说明)
                                    _lqd = _ex_liqpx(client, inst_id, _ps)
                                    posobj["liq_px"] = _lqd
                                    state["positions"].append(posobj)
                                    _erl2 = posobj.get("err") or []
                                    line += (f"\n\n> ✅ 已开仓 {fl}张 @{avg:,.1f} · 订单 {ordid}"
                                             + (f"\n> 🎯 交易所已挂 止盈 {fmt_price(sig.tp)} / 止损 {fmt_price(sl_fill)}" if not _erl2 else
                                                f"\n> ❌ 交易所挂单**未挂上** {'；'.join(_erl2)}（本地记录 止盈 {fmt_price(sig.tp)} / 止损 {fmt_price(sl_fill)}，请手动确认）")
                                             + (f"\n> 💥 爆仓价 {fmt_price(_lqd)}（交易所）" if _lqd
                                                else "\n> 💥 爆仓价：交易所未返回（不本地估算）"))
                                    state["daily"]["trades"] += 1
                                    state["daily"]["by_profile"][pname] = state["daily"]["by_profile"].get(pname, 0) + 1
                                    _opened = True
                                else:
                                    # 成交慢(尤其XAU演示盘) → 不撤单, 转"挂单待成交", 下轮巡检确认
                                    state.setdefault("pending_entries", []).append({
                                        "inst": inst_id, "direction": sig.direction, "size": size["lots"],
                                        "ord_id": ordid, "tp": sig.tp, "profile": pname, "lev": used_lev,
                                        "sl": sig.sl,
                                        "signal_entry": sig.entry, "ts": int(time.time())})
                                    line += (f"\n\n> ⏳ 已挂单待成交（状态{stt}）· 订单 {ordid}"
                                             f"\n> 演示盘成交慢，下轮巡检确认成交后再建仓")
                            else:
                                line += f"\n\n> ❌ 开仓失败 [{dd.get('sCode') or resp.get('code')}] {dd.get('sMsg') or resp.get('msg')}"
                        else:
                            # DRY_RUN: 建立虚拟持仓 → 观察期自动统计模拟盈亏
                            state["positions"].append({"inst": inst_id, "direction": sig.direction,
                                                       "entry": sig.entry, "sl": sl_use, "tp": sig.tp,
                                                       "size": size["lots"], "ratio": 1.0,
                                                       "risk_free": False, "tp1_hit": False,
                                                       "leverage": used_lev, "profile": pname,
                                                       "run_id": state["last_run_ts"],
                                                       "simulated": True, "opened": int(time.time())})
                            _opened = True
                        add("哨兵", line)
                        queue_chart(inst_id, [(sig.entry, "进场", "#1f6feb"),
                                              (sl_use, "止损", "#d32f2f"),
                                              (sig.tp, "目标", "#2e7d32")],
                                    title=f"{'做多' if sig.direction == 'long' else '做空'} · {plabel}")
                        if _opened:
                            _nmx = "BTC" if "BTC" in inst_id else "黄金"
                            _sdx = "做多" if sig.direction == "long" else "做空"
                            _rrx = abs(sig.tp - sig.entry) / max(abs(sig.entry - sl_use), 1e-9)
                            state.setdefault("history", []).append({"type": "signal", "ts": time.time(),
                                "profile": pname,
                                "detail": f"{_nmx}{_sdx} · 进{fmt_price(sig.entry)} 损{fmt_price(sl_use)} 标{fmt_price(sig.tp)} · RR1:{_rrx:.0f}"})
                    else:
                        add("哨兵", f"⚠️ **`{plabel}` {inst_id} 信号被风控拦截**\n" + "\n".join(f"· {d}" for d in detail if "❌" in d))
                    # 记录指纹(去重), 保留最近60条
                    state.setdefault("pushed_signals", []).append(fp)
                    state["pushed_signals"] = state["pushed_signals"][-60:]
                # ---- 持仓管理 (出场引擎; 按方案过滤) ----
                for p in list(state["positions"]):
                    if p["inst"] != inst_id or p.get("profile", "4H+1H") != pname:
                        continue
                    # 本轮新建的仓位: 当根K线不做出场判断(修复"开仓即被当根影线打损"顽疾)
                    if p.get("run_id") == state.get("last_run_ts"):
                        print(f"[新仓位保护] {inst_id} 本轮新建, 跳过出场判断(下轮起管理)")
                        continue
                    # ★ 自愈: 确保交易所端止盈/止损挂单存在(缺哪条补哪条)
                    #   ★严格校验: 必须 code=0 且 sCode=0 且拿到 algoId 才算成功; 否则绝不推"已挂"
                    if not DRY_RUN:
                        _psh = "long" if p["direction"] == "long" else "short"
                        _tdh = sym_cfg.get("td_mode", "isolated")
                        _fixed, _failed = [], []
                        try:
                            _live = client.algo_ids(inst_id)
                        except Exception:
                            _live = None
                        if _live is not None:
                            if p.get("tp_algo_id") not in _live:
                                _r = client.place_tp_order(inst_id, _psh, p["size"], _tdh, p["tp"])
                                _dd = ((_r.get("data") or [{}])[0] or {})
                                print(f"[补挂TP] {inst_id} sz={p['size']} px={p['tp']} code={_r.get('code')} sCode={_dd.get('sCode')} msg={_r.get('msg') or _dd.get('sMsg')} | {json.dumps(_r, ensure_ascii=False)[:300]}")
                                if _r.get("code") == "0" and _dd.get("sCode") == "0" and _dd.get("algoId"):
                                    p["tp_algo_id"] = _dd.get("algoId"); _fixed.append("止盈")
                                else:
                                    _failed.append(f"止盈[{_dd.get('sCode') or _r.get('code')}:{_dd.get('sMsg') or _r.get('msg')}]")
                            if p.get("sl_algo_id") not in _live:
                                _r = client.place_sl_order(inst_id, _psh, p["size"], _tdh, p["sl"])
                                _dd = ((_r.get("data") or [{}])[0] or {})
                                print(f"[补挂SL] {inst_id} sz={p['size']} px={p['sl']} code={_r.get('code')} sCode={_dd.get('sCode')} msg={_r.get('msg') or _dd.get('sMsg')} | {json.dumps(_r, ensure_ascii=False)[:300]}")
                                if _r.get("code") == "0" and _dd.get("sCode") == "0" and _dd.get("algoId"):
                                    p["sl_algo_id"] = _dd.get("algoId"); _fixed.append("止损")
                                else:
                                    _failed.append(f"止损[{_dd.get('sCode') or _r.get('code')}:{_dd.get('sMsg') or _r.get('msg')}]")
                        if _fixed:
                            add("巡检", f"🛡️ **`{plabel}` {inst_id}** 已补挂交易所 {'/'.join(_fixed)}：止盈 {fmt_price(p['tp'])} / 止损 {fmt_price(p['sl'])}")
                        if _failed:
                            _fsig = "|".join(_failed)
                            if p.get("tpsl_fail") != _fsig:
                                p["tpsl_fail"] = _fsig
                                add("巡检", f"❌ **`{plabel}` {inst_id}** 交易所挂单**失败**：{'；'.join(_failed)}\n> 本地记录 止盈 {fmt_price(p['tp'])} / 止损 {fmt_price(p['sl'])}，但交易所端无此挂单，请手动确认")
                        else:
                            p.pop("tpsl_fail", None)
                    pos = Position(p["direction"], p["entry"], p["sl"], p["tp"],
                                   size=p.get("ratio", 1.0), opened_bar=0,
                                   inst=inst_id, lots=p.get("size", 0))
                    pos.risk_free = p.get("risk_free", False)
                    pos.tp1_hit = p.get("tp1_hit", False)
                    xe = ExitEngine()
                    acts = xe.manage(pos, candles, se, le)
                    exited = False
                    _ps = "long" if p["direction"] == "long" else "short"
                    for act in acts:
                        if act[0] == "EXIT":
                            _nm = "BTC" if "BTC" in inst_id else "黄金"
                            _sd = "多单" if p["direction"] == "long" else "空单"
                            exit_px = act[2] if len(act) > 2 else p["entry"]
                            _src = "按K线结构"
                            _closed = True
                            if not DRY_RUN:
                                # 先撤交易所止盈/止损挂单, 再市价平仓, 并以交易所真实成交价为准
                                _cancel_exchange_tpsl(client, inst_id, p)
                                side = "sell" if p["direction"] == "long" else "buy"
                                resp = client.close_position(inst_id, side, p["size"],
                                                             td_mode=sym_cfg.get("td_mode", "isolated"), pos_side=_ps)
                                _rd = ((resp.get("data") or [{}])[0] or {})
                                _cod = _rd.get("ordId")
                                _fill = 0.0
                                if resp.get("code") == "0" and _rd.get("sCode") == "0" and _cod:
                                    for _ in range(6):
                                        _od = (client.get_order(inst_id, _cod).get("data") or [{}])[0]
                                        _fill = float(_od.get("accFillSz") or 0)
                                        if _fill > 0 or _od.get("state") in ("filled", "canceled"):
                                            exit_px = float(_od.get("avgPx") or exit_px); break
                                        time.sleep(0.8)
                                if _fill <= 0:
                                    # ★严格校验(2026-10-02): 未确认成交 → 绝不删本地记录, 下轮重试(防"假平仓"丢仓)
                                    print(f"[平仓未确认] {inst_id} sz={p['size']} code={resp.get('code')} sCode={_rd.get('sCode')} msg={resp.get('msg') or _rd.get('sMsg')} | {json.dumps(resp, ensure_ascii=False)[:300]}")
                                    add("巡检", f"❌ **`{plabel}` {inst_id} 平仓未成交**：{_rd.get('sMsg') or resp.get('msg') or '未确认成交'}\n> 交易所端仓位仍在，本轮**不删记录**，下轮重试")
                                    _closed = False
                                else:
                                    _src = "交易所成交价"
                            if not _closed:
                                continue
                            ctval = C.INST_SPECS.get(inst_id, {}).get("ctVal", 0)
                            sign = 1 if p["direction"] == "long" else -1
                            pnl = (exit_px - p["entry"]) * sign * p["size"] * ctval
                            _ico = "✅" if pnl > 1e-9 else ("➖" if pnl > -1e-9 else "❌")
                            _sim = "（模拟）" if p.get("simulated") else ""
                            _t = " · ".join(x for x in [_nm, _sd, plabel] if x) + _sim
                            add("铁律", f"{_ico} **已平仓 · {_t}**\n"
                                           f"**进出** {fmt_price(p['entry'])} → {fmt_price(exit_px)}（{_src}）\n"
                                           f"**盈亏** {pnl:+.2f}U（{pnl / C.MARGIN_PER_TRADE * 100:+.0f}%）\n"
                                           f"**原因** {act[1]}")
                            queue_chart(p["inst"], [(p["entry"], "进场", "#1f6feb"),
                                                    (exit_px, "离场", "#7b1fa2")],
                                        title=f"平仓 · {p['direction'].upper()} · {pnl:+.2f}U")
                            state.setdefault("history", []).append({"type": "exit", "ts": time.time(),
                                "profile": pname, "pnl": round(pnl, 2),
                                "entry": round(p["entry"], 2), "exit": round(exit_px, 2),
                                "detail": f"[{plabel}] {_nm} {p['direction'].upper()} {pnl:+.2f}U"})
                            state["positions"].remove(p)
                            exited = True
                            break
                        elif act[0] == "PARTIAL_TP":
                            cut = round(p["size"] * 0.5, 6)
                            if not DRY_RUN:
                                side = "sell" if p["direction"] == "long" else "buy"
                                client.close_position(inst_id, side, cut,
                                                      td_mode=sym_cfg.get("td_mode", "isolated"), pos_side=_ps)
                            p["size"] = round(p["size"] - cut, 6)
                            p["ratio"] = pos.size
                            p["tp1_hit"] = True
                            # 仓位变小 → 交易所止盈/止损按剩余量重挂
                            if not DRY_RUN:
                                _cancel_exchange_tpsl(client, inst_id, p)
                                p.update(_place_exchange_tpsl(client, inst_id, _ps, p["size"],
                                                              sym_cfg.get("td_mode", "isolated"), p["tp"], p["sl"]))
                            add("铁律", f"➗ **{plabel} · {inst_id}** {act[1]}")
                        elif act[0] == "MOVE_SL":
                            p["sl"] = pos.sl
                            p["risk_free"] = pos.risk_free
                            # 止损移动 → 撤旧挂新, 保持交易所与报表一致
                            if not DRY_RUN and p.get("sl_algo_id"):
                                try:
                                    client.cancel_algo(inst_id, p["sl_algo_id"])
                                except Exception as e:
                                    print(f"[撤旧SL异常] {e}")
                                _r = client.place_sl_order(inst_id, _ps, p["size"],
                                                           sym_cfg.get("td_mode", "isolated"), pos.sl)
                                p["sl_algo_id"] = ((_r.get("data") or [{}])[0] or {}).get("algoId")
                            add("巡检", f"🛡️ **{plabel} · {inst_id}** {act[1]}")
                    if not exited:
                        # 状态写回(修复Bug2: 保本/部分止盈持久化)
                        p["sl"] = pos.sl
                        p["risk_free"] = pos.risk_free
                        p["tp1_hit"] = pos.tp1_hit
                        p["ratio"] = pos.size

    # ---- 每日日报: 北京时间8点后当天首次运行触发(窗口放宽, 防止调度错过8点档) ----
    if os.environ.get("FORCE_DAILY") == "1":        # ★测试钩子: 强制推一次日报(不改状态)
        push(build_daily_report(state, now_bj))
    elif now_bj.hour >= 8 and state.get("daily_report_date") != today:
        push(build_daily_report(state, now_bj))
        state["daily_report_date"] = today

    # ---- 推送策略: 有实质内容才推; 无内容静默 ----
    if reports:
        _order = ["哨兵", "铁律", "巡检"]
        _blk = {}
        for _c, _t in reports:
            _blk.setdefault(_c, []).append(_t)
        header = f"🌙 **暗夜猎手** {now_bj.strftime('%m-%d %H:%M')}"
        _parts = [header, "━━━━━━━━━━━━━━━"]
        for _c in _order:
            if _c in _blk:
                _parts.append(f"**【{_c}】**")
                _parts.extend(_blk[_c])
        push("\n\n".join(_parts))
    else:
        print(f"=== 静默(无新信号) {now_bj.strftime('%m-%d %H:%M')} ===")

    # ---- 图表推送(裁定A: 只在 信号/开仓/平仓 时登记) ★文字先发, 图后发 ----
    flush_charts(client)

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
