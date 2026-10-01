# 关闭 XAU 持仓 (演示盘垃圾仓)
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
print("=== 撤挂单 ===")
for o in (c._get("/api/v5/trade/orders-pending", {"instType": "SWAP"}).get("data") or []):
    print("  撤", o.get("instId"), o.get("ordId"), json.dumps(c._post("/api/v5/trade/cancel-order", {"instId": o.get("instId"), "ordId": o.get("ordId")}), ensure_ascii=False)[:100])
print("=== 平 XAU 持仓 ===")
for x in (c.get_positions().get("data") or []):
    if "XAU" in x["instId"] and float(x["pos"]) != 0:
        side = "sell" if x["posSide"] == "long" else "buy"
        r = c.place_order(x["instId"], side, x["pos"], td_mode="isolated", pos_side=x["posSide"])
        print("  平", x["instId"], x["posSide"], x["pos"], "->", json.dumps(r, ensure_ascii=False)[:180])
print("=== 剩余持仓 ===")
for x in (c.get_positions().get("data") or []):
    print("  ", x["instId"], x["posSide"], x["pos"])
