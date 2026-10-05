# -*- coding: utf-8 -*-
"""探测 WEEX v3 行情接口(v2 已下线, 返回 40018 "use the v3 service")。
沙盒连不上 weex → 必须在 GitHub Actions 里跑。
目的: 确认 v3 的 klines/historyKlines 路径、symbol 命名(含黄金)、以及行格式。"""
import json
import requests

HOST = "https://api-contract.weex.com"


def try_get(path, params):
    try:
        r = requests.get(HOST + path, params=params, timeout=25)
        print(f"  {path} {params} -> HTTP {r.status_code} | {r.text[:260]}")
        if r.status_code == 200:
            try:
                j = r.json()
                rows = j if isinstance(j, list) else (j.get("data") or [])
                if isinstance(rows, list) and rows:
                    print(f"     行数={len(rows)}  首行={json.dumps(rows[0], ensure_ascii=False)[:220]}")
            except Exception:
                pass
        return r.status_code
    except Exception as e:
        print(f"  {path} {params} -> EXC {type(e).__name__} {e}")
        return None


print("=== 1) exchangeInfo (找黄金/合约符号) ===")
try:
    r = requests.get(HOST + "/capi/v3/market/exchangeInfo", timeout=25)
    print("  http", r.status_code)
    j = r.json()
    rows = j if isinstance(j, list) else (j.get("data") or j.get("symbols") or [])
    syms = []
    for x in rows:
        s = x.get("symbol") if isinstance(x, dict) else x
        if s:
            syms.append(str(s))
    print("  合约数:", len(syms))
    print("  含 BTC:", [s for s in syms if "BTC" in s.upper()][:15])
    print("  含 XAU/GOLD/XAUT:", [s for s in syms if ("XAU" in s.upper() or "GOLD" in s.upper() or "XAUT" in s.upper())][:25])
    if rows and isinstance(rows[0], dict):
        print("  首行字段:", list(rows[0].keys()))
except Exception as e:
    print("  失败:", type(e).__name__, e)

print("=== 2) klines 候选 ===")
for sym in ["BTCUSDT", "cmt_btcusdt", "XAUTUSDT", "cmt_xautusdt"]:
    try_get("/capi/v3/market/klines", {"symbol": sym, "interval": "1h", "limit": 3})

print("=== 3) historyKlines ===")
try_get("/capi/v3/market/historyKlines", {"symbol": "BTCUSDT", "interval": "1h", "limit": 3})

print("=== 4) 备选路径 (防 v3 也换了名) ===")
try_get("/capi/v3/market/candles", {"symbol": "BTCUSDT", "interval": "1h", "limit": 3})
try_get("/capi/v3/market/ticker/24hr", {"symbol": "BTCUSDT"})
try_get("/capi/v3/market/time", {})
