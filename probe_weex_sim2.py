# 探测③: sim 契约细节 —— 交易对全字段(精度) + 撤单/订单/杠杆接口路径扫描 + 服务器时间
import json
import requests

BASE = "https://api-contract.weex.com"
H = {"Content-Type": "application/json", "User-Agent": "nighthunter-probe/1.0"}


def code(r):
    return r.status_code


# ① 交易对全字段(BTC/XAUT 的精度、最大杠杆等)
r = requests.get(BASE + "/capi/v3/market/apiTradingSymbols", headers=H, timeout=30)
j = r.json()
data = j.get("data") if isinstance(j, dict) else j
print(f"### apiTradingSymbols 顶层 keys={list(j.keys()) if isinstance(j, dict) else 'list'} 条数={len(data) if isinstance(data, list) else '?'}")
if isinstance(data, list) and data:
    print("### 单条记录的全部字段(样例):")
    print(json.dumps(data[0], ensure_ascii=False, indent=2)[:1200])
for want in ("BTCSUSDT", "XAUTSUSDT", "BTCUSDT"):
    if isinstance(data, list):
        for x in data:
            nm = x if isinstance(x, str) else (x.get("symbol") or x.get("symbolName") or "")
            if nm == want:
                print(f"### {want} 全字段:")
                print(json.dumps(x, ensure_ascii=False, indent=2)[:900])
                break

# ② 服务器时间
r = requests.get(BASE + "/capi/v3/market/time", headers=H, timeout=30)
print(f"### GET /capi/v3/market/time status={code(r)} → {r.text[:200]}")

# ③ 路径存在性扫描(无签名: 401=存在需鉴权 / 400=存在参数错 / 404=不存在)
CAND = [
    ("POST", "/capi/v3/sim/order"), ("DELETE", "/capi/v3/sim/order"),
    ("POST", "/capi/v3/sim/order/cancel"), ("POST", "/capi/v3/sim/cancelOrder"),
    ("POST", "/capi/v3/sim/order/cancelOrder"), ("POST", "/capi/v3/sim/order/close"),
    ("GET", "/capi/v3/sim/order"), ("GET", "/capi/v3/sim/order/detail"),
    ("GET", "/capi/v3/sim/order/get"), ("GET", "/capi/v3/sim/openOrders"),
    ("GET", "/capi/v3/sim/order/pending"), ("GET", "/capi/v3/sim/position"),
    ("GET", "/capi/v3/sim/order/history"),
    ("POST", "/capi/v3/sim/leverage"), ("POST", "/capi/v3/sim/position/leverage"),
    ("POST", "/capi/v3/sim/setLeverage"), ("POST", "/capi/v3/sim/margin/leverage"),
    ("POST", "/capi/v3/sim/position/marginType"),
    ("GET", "/capi/v3/market/contracts"), ("GET", "/capi/v3/market/instruments"),
    ("GET", "/capi/v3/market/exchangeInfo"),
]
for m, p in CAND:
    try:
        r = requests.request(m, BASE + p, headers=H, json={} if m == "POST" else None, timeout=25)
        print(f"### {m:6} {p:42} → {code(r)}  {r.text[:110].replace(chr(10),' ')}")
    except Exception as e:
        print(f"### {m:6} {p:42} → 异常 {type(e).__name__}")
print("完成")
