# 核验: 清理后交易所现状
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
print("=== POSITIONS ===")
for p in (c.get_positions().get("data") or []):
    if float(p.get("pos") or 0) != 0:
        print("  ", p.get("instId"), p.get("posSide"), "pos=", p.get("pos"), "avg=", p.get("avgPx"))
print("=== PENDING TP/SL ===")
for a in (c.get_algo_pending().get("data") or []):
    print("  ", a.get("instId"), a.get("posSide"), "sz=", a.get("sz"), "tp=", a.get("tpTriggerPx"), "sl=", a.get("slTriggerPx"))
