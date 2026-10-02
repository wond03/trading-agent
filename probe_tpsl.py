# 最终核验
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
print("POS:", [(p.get("instId"), p.get("posSide"), p.get("pos")) for p in (c.get_positions().get("data") or []) if float(p.get("pos") or 0) != 0])
print("TP/SL:", [(a.get("instId"), a.get("tpTriggerPx"), a.get("slTriggerPx")) for a in (c.get_algo_pending().get("data") or [])])
print("ORDERS:", [(a.get("instId"), a.get("sz"), a.get("state")) for a in (c.get_pending_orders().get("data") or [])])
