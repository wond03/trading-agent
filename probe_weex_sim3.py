# 探测④: exchangeInfo 全量(交易对精度/杠杆) + 更多撤单路径候选
import json
import requests

BASE = "https://api-contract.weex.com"
H = {"Content-Type": "application/json", "User-Agent": "nighthunter-probe/1.0"}

r = requests.get(BASE + "/capi/v3/market/exchangeInfo", headers=H, timeout=40)
j = r.json()
print("### exchangeInfo 顶层 keys =", list(j.keys()))
for k, v in j.items():
    if isinstance(v, list):
        print(f"   {k}: list len={len(v)}  样例={json.dumps(v[0], ensure_ascii=False)[:600] if v else None}")

syms = j.get("symbols") or j.get("contracts") or []
for want in ("BTCSUSDT", "XAUTSUSDT", "BTCUSDT", "XAUTUSDT"):
    for s in syms:
        if isinstance(s, dict) and (s.get("symbol") or s.get("symbolName")) == want:
            print(f"\n### {want} 全字段:")
            print(json.dumps(s, ensure_ascii=False, indent=2)[:1500])
            break

print("\n### 撤单候选路径扫描")
for m, p in [("POST", "/capi/v3/sim/cancel"), ("POST", "/capi/v3/sim/orderCancel"),
             ("POST", "/capi/v3/sim/orders/cancel"), ("POST", "/capi/v3/sim/order/cancel_order"),
             ("POST", "/capi/v3/sim/orderCancelAll"), ("POST", "/capi/v3/sim/cancelAllOrders"),
             ("POST", "/capi/v3/sim/order/revoke"), ("POST", "/capi/v3/sim/cancelOrderAll"),
             ("GET", "/capi/v3/sim/order/query"), ("GET", "/capi/v3/sim/orderDetail"),
             ("GET", "/capi/v3/sim/position/allPosition"), ("GET", "/capi/v3/sim/balance"),
             ("GET", "/capi/v3/sim/order/fills"), ("GET", "/capi/v3/sim/userTrades")]:
    try:
        rr = requests.request(m, BASE + p, headers=H, json={} if m == "POST" else None, timeout=25)
        print(f"   {m:5} {p:40} → {rr.status_code}  {rr.text[:100].replace(chr(10),' ')}")
    except Exception as e:
        print(f"   {m:5} {p:40} → 异常 {type(e).__name__}")
print("完成")
