# 探测②: WEEX 合约 sim 接口是否真实存在 + 交易对清单(公开接口, 无需签名)
import json
import requests

BASE = "https://api-contract.weex.com"
H = {"Content-Type": "application/json", "User-Agent": "nighthunter-probe/1.0"}


def show(tag, r):
    print(f"### {tag}  status={r.status_code}")
    print("   ", r.text[:600].replace("\n", " "))


# ① 交易对清单 (错误码 -1058 里提到的官方接口)
for path in ("/capi/v3/market/apiTradingSymbols", "/capi/v2/market/apiTradingSymbols"):
    try:
        r = requests.get(BASE + path, headers=H, timeout=30)
        print(f"### {path} status={r.status_code}")
        if r.status_code == 200:
            j = r.json()
            data = j.get("data") if isinstance(j, dict) else j
            syms = []
            if isinstance(data, list):
                for x in data:
                    syms.append(x if isinstance(x, str) else (x.get("symbol") or x.get("symbolName") or str(x)[:40]))
            print(f"    共 {len(syms)} 个; 含 BTC/XAU 的:")
            for s in syms:
                if "BTC" in str(s).upper() or "XAU" in str(s).upper() or "XAUT" in str(s).upper():
                    print("      ", s)
            if syms:
                print("    前10个样例:", syms[:10])
        else:
            print("   ", r.text[:300])
    except Exception as e:
        print(f"### {path} 失败 {type(e).__name__} {e}")

# ② sim 接口是否存在(不带签名 → 预期返回鉴权错误, 但可证明路径存在)
show("GET /capi/v3/sim/balance (无签名)", requests.get(BASE + "/capi/v3/sim/balance", headers=H, timeout=30))
show("GET /capi/v3/sim/position/allPosition (无签名)",
     requests.get(BASE + "/capi/v3/sim/position/allPosition", headers=H, timeout=30))
show("POST /capi/v3/sim/order (无签名)",
     requests.post(BASE + "/capi/v3/sim/order", headers=H, json={}, timeout=30))

# ③ 猜测: 撤单/杠杆/订单详情 路径是否可用(无签名时区分 404 与 401)
for p in ("/capi/v3/sim/order/cancel", "/capi/v3/sim/leverage", "/capi/v3/sim/order/detail",
          "/capi/v3/sim/position/leverage"):
    show(f"POST {p} (无签名)", requests.post(BASE + p, headers=H, json={}, timeout=30))

# ④ 行情: 确认 sim 对应的合约 symbol 能不能取到 K 线
for sym in ("cmt_btcusdt", "cmt_xautusdt", "BTCSUSDT", "BTCUSDT"):
    try:
        r = requests.get(BASE + "/capi/v2/market/candles",
                         params={"symbol": sym, "granularity": "1m", "limit": 2}, headers=H, timeout=30)
        print(f"### candles symbol={sym} status={r.status_code} → {r.text[:160]}")
    except Exception as e:
        print(f"### candles symbol={sym} 失败 {e}")
print("完成")
