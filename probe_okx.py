import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
print("VERIFY_POSITIONS:")
for x in (c.get_positions().get("data") or []):
    print("   POS", x.get("instId"), x.get("posSide"), "pos=", x.get("pos"), "avgPx=", x.get("avgPx"))
oo = c._get("/api/v5/trade/orders-pending", {"instType": "SWAP"})
print("VERIFY_PENDING:", len(oo.get("data") or []))
