# OKX 合约规格探针 (云端运行, 查XAU相关合约与BTC合约的每张面值/最小下单量/最大杠杆)
import requests, json
def inst(t):
    r = requests.get("https://www.okx.com/api/v5/public/instruments", params={"instType": t}, timeout=20)
    return r.json().get("data", [])

print("===== SWAP 中 XAU/XAUT/GOLD 相关合约 =====")
for i in inst("SWAP"):
    if any(k in i["instId"] for k in ("XAU", "XAUT", "GOLD", "PAX")):
        print(f"{i['instId']} | 每张面值={i['ctVal']} {i['ctValCcy']} | 最小下单={i['minSz']}张 | 下单步长={i['lotSz']} | 最大杠杆={i['lever']} | 类型={i.get('ctType')}")
print("\n===== BTC-USDT-SWAP 规格 =====")
for i in inst("SWAP"):
    if i["instId"] == "BTC-USDT-SWAP":
        print(f"{i['instId']} | 每张面值={i['ctVal']} {i['ctValCcy']} | 最小下单={i['minSz']}张 | 步长={i['lotSz']} | 最大杠杆={i['lever']} | 最大市价单={i['maxMktSz']}张")
print("\n===== SPOT 中 XAU/XAUT/PAX 相关 =====")
for i in inst("SPOT"):
    if any(k in i["instId"] for k in ("XAU", "XAUT", "PAX")):
        print(f"{i['instId']} | 最小下单={i['minSz']} | 步长={i['lotSz']}")
print("\n===== 计价验证 =====")
r = requests.get("https://www.okx.com/api/v5/market/ticker", params={"instId": "BTC-USDT-SWAP"}, timeout=15).json()
print("BTC-USDT-SWAP 现价:", r["data"][0]["last"] if r.get("code")=="0" else r)
