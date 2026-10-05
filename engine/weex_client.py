# 暗夜猎手 (NightHunter) · WEEX 合约公开行情客户端
# 用途: 【信号】与【回测】统一的数据源 (模拟盘交易见 weex_trade/weex_broker)
# 依据: 用户上传的 WEEX 现货 V3 行情文档 + 本机实测 api-contract.weex.com 合约接口
#   GET /capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=1000   → 最近 N 根(新→旧)
#   GET /capi/v2/market/historyCandles?...&endTime=<ms>&limit=100             → 历史分页(向前翻)
#   GET /capi/v2/market/tickers  /contracts                                   → 行情/合约规格
# 返回行格式: ["开盘时间ms", open, high, low, close, volume, quoteVolume]  ★倒序, 数字为字符串
# ★两条铁律(与 engine 其余部分一致):
#   1) 时间戳统一为【秒】
#   2) 未收盘的当根必须剔除 (只保留 ts + 周期时长 <= 当前时刻)
import time
import requests

HOST = "https://api-contract.weex.com"
# 我方品种 → WEEX 合约 symbol (XAU 用真实黄金合约 cmt_xautusdt, 不再用 PAXG 代理)
SYMBOLS = {"BTC-USDT-SWAP": "cmt_btcusdt", "XAU-USDT-SWAP": "cmt_xautusdt"}
GRAN = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1H": "1h", "1h": "1h", "4H": "4h", "4h": "4h", "1D": "1d", "1d": "1d"}
TFSEC = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}


def sym_of(inst_id):
    return SYMBOLS.get(inst_id) or ("cmt_" + inst_id.split("-")[0].lower() + "usdt")


def gran_of(tf):
    g = GRAN.get(tf)
    if not g:
        raise ValueError(f"WEEX 不支持的周期: {tf}")
    return g


def tfsec_of(tf):
    return TFSEC[gran_of(tf)]


def _get(path, params, tries=4):
    last = None
    for k in range(tries):
        try:
            r = requests.get(HOST + path, params=params, timeout=25)
            if r.status_code == 400:
                raise ValueError(f"WEEX 参数错误 {path}: {r.text[:160]}")
            r.raise_for_status()
            return r.json()
        except ValueError:
            raise
        except Exception as e:
            last = e
            time.sleep(1.2 * (k + 1))
    raise RuntimeError(f"WEEX 取数失败 {path}: {last}")


def _to_store(rows, tf, now=None):
    """行 → {ts秒: (o,h,l,c,v)}; ★剔除未收盘的当根"""
    now = now or time.time()
    dur = tfsec_of(tf)
    out = {}
    for x in rows:
        try:
            ts = int(int(x[0]) / 1000)
            if ts + dur > now:              # 未收盘 → 丢
                continue
            out[ts] = (float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]))
        except Exception:
            continue
    return out


def get_candles(inst_id, tf, limit=400, now=None):
    """实盘用: 最近 limit 根【已收盘】K线, 升序元组 [(ts, o,h,l,c,v), ...]"""
    limit = max(1, min(int(limit), 1000))
    rows = _get("/capi/v2/market/candles",
                {"symbol": sym_of(inst_id), "granularity": gran_of(tf), "limit": limit})
    st = _to_store(rows, tf, now)
    ks = sorted(st)[-limit:]
    return [(k, *st[k]) for k in ks]


def get_range(inst_id, tf, start_ts, end_ts):
    """回测/镜像用: [start_ts, end_ts] 内已收盘K线(升序)。
    先取最近 1000 根; 更早的部分用 historyCandles 的【startTime+endTime 时间窗】向前分页(每页≤100根)。
    ★实测: 单给 endTime 无效, 必须同时给 startTime。"""
    dur = tfsec_of(tf)
    st = {}
    rows = _get("/capi/v2/market/candles",
                {"symbol": sym_of(inst_id), "granularity": gran_of(tf), "limit": 1000})
    st.update(_to_store(rows, tf, end_ts))
    have_min = min(st) if st else int(end_ts)
    cur_end = int(end_ts)
    for _ in range(400):                     # 上限 400 页, 防死循环
        if have_min <= start_ts or cur_end <= start_ts:
            break
        win_start = max(int(start_ts), cur_end - 100 * dur)
        try:
            rows = _get("/capi/v2/market/historyCandles",
                        {"symbol": sym_of(inst_id), "granularity": gran_of(tf), "limit": 100,
                         "startTime": win_start * 1000, "endTime": cur_end * 1000})
        except Exception as e:
            print(f"[WEEX] 历史分页停止: {type(e).__name__} {e}")
            break
        new = {k: v for k, v in _to_store(rows, tf).items() if start_ts <= k <= end_ts}
        if new:
            st.update(new)
            have_min = min(have_min, min(new))
            # ★2026-10-03 修复: 原先用 win_start-dur 作下一页边界, 因每页只回 100 根(含端点),
            #   会在每页接缝处丢 1 根(实测 1H 缺19根/15m缺105根)。改为按"本页实际最老的那根"再退一格。
            cur_end = min(new) - dur
        else:
            cur_end = win_start - dur
    return [(k, *st[k]) for k in sorted(st) if start_ts <= k <= end_ts]


def ticker(inst_id):
    """最新价(便捷)"""
    r = _get("/capi/v2/market/ticker", {"symbol": sym_of(inst_id)})
    d = r[0] if isinstance(r, list) and r else r
    return float((d or {}).get("last") or (d or {}).get("close") or 0)
