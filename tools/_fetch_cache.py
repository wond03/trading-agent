# 数据抓取 + 磁盘缓存 —— ★数据源: WEEX 合约 (2026-10-03 用户裁定: 信号/回测同源)
# 供 backtest / 复核图 / 等价性检查复用
# ★沙盒无法直连 WEEX → 本地请先执行: python tools/weex_cache.py pull (从仓库镜像拉)
import os, json, sys, time

_ENGINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)
import weex_client                     # noqa: E402

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache_weex")


def _path(inst, tf):
    return os.path.join(CACHE_DIR, f"{inst}_{tf}.json")


def load_cache(inst, tf):
    p = _path(inst, tf)
    if os.path.exists(p):
        try:
            return {int(k): v for k, v in json.load(open(p)).items()}
        except Exception:
            return {}
    return {}


def save_cache(inst, tf, store):
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump({str(k): store[k] for k in sorted(store)}, open(_path(inst, tf), "w"))


def fetch_range(inst, tf, start_ts, end_ts, allow_fetch=True):
    """返回 ([start_ts, end_ts] 内已收盘K线的时间戳列表(升序), {ts: [o,h,l,c,v]})"""
    store = load_cache(inst, tf)
    dur = weex_client.tfsec_of(tf)
    ok = bool(store) and min(store) <= start_ts and max(store) >= end_ts - 2 * dur
    if not ok and allow_fetch:
        try:
            rows = weex_client.get_range(inst, tf, start_ts, end_ts)
            for r in rows:
                store[r[0]] = list(r[1:])
            if rows:
                save_cache(inst, tf, store)
            print(f"[WEEx] {inst} {tf} 抓取 {len(rows)} 根 (缓存共 {len(store)})")
        except Exception as e:
            print(f"[WEEX] 抓取失败({type(e).__name__}: {str(e)[:100]}) —— "
                  f"沙盒无法直连 WEEX, 请先跑: python tools/weex_cache.py pull")
    keys = [k for k in sorted(store) if start_ts <= k <= end_ts]
    return keys, store


# ---------- 以下为旧 Gate 现货取数(已不用, 仅留作对照/诊断) ----------
import requests                        # noqa: E402
URL = "https://api.gateio.ws/api/v4/spot/candlesticks"
PAIR_MAP = {"BTC-USDT-SWAP": "BTC_USDT", "XAU-USDT-SWAP": "PAXG_USDT"}
TF_GATE = {"1H": "1h", "4H": "4h", "15m": "15m", "5m": "5m"}
CACHE_DIR_GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")


def _get(params, tries=6):
    last = None
    for k in range(tries):
        try:
            r = requests.get(URL, params=params, timeout=45)
            if r.status_code == 400:
                raise ValueError(r.text[:200])
            r.raise_for_status()
            return r.json()
        except ValueError:
            raise
        except Exception as e:
            last = e
            time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"gate fetch failed: {last}")
