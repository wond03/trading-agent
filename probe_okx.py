# OKX 清理: 撤掉所有挂单 + 平掉所有持仓 (演示盘)
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)

print("=== 1) 撤掉所有挂单 ===")
oo = c._get("/api/v5/trade/orders-pending", {"instType": "SWAP"})
orders = oo.get("data") or []
if not orders:
    print("   （无挂单）")
for o in orders:
    print("   撤单:", o.get("instId"), o.get("ordId"), o.get("side"), o.get("sz"), o.get("state"))
    r = c._post("/api/v5/trade/cancel-order", {"instId": o["instId"], "ordId": o["ordId"]})
    print("     ->", json.dumps(r, ensure_ascii=False)[:160])

print("=== 2) 平掉所有持仓 ===")
p = c.get_positions()
for x in (p.get("data") or []):
    inst, ps, sz = x["instId"], x["posSide"], x["pos"]
    side = "sell" if ps == "long" else "buy"
    r = c.place_order(inst, side, sz, td_mode="isolated", pos_side=ps)
    print("   平仓:", inst, ps, sz, "->", json.dumps(r, ensure_ascii=False)[:200])

print("=== 3) 清理后确认 ===")
oo2 = c._get("/api/v5/trade/orders-pending", {"instType": "SWAP"})
print("   挂单数:", len(oo2.get("data") or []))
p2 = c.get_positions()
print("   持仓数:", len(p2.get("data") or []))
for x in (p2.get("data") or []):
    print("     ", x.get("instId"), x.get("posSide"), x.get("pos"))
