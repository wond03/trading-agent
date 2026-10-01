# 核验: 交易所持仓 + 已挂止盈止损
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
print("=== POSITIONS ===")
for p in (c.get_positions().get("data") or []):
    print("  ", p.get("instId"), p.get("posSide"), "pos=", p.get("pos"), "avg=", p.get("avgPx"))
print("=== PENDING TP/SL (策略委托) ===")
for a in (c.get_algo_pending().get("data") or []):
    print("  ", {k: a.get(k) for k in ("instId", "posSide", "sz", "reduceOnly", "tpTriggerPx", "slTriggerPx", "state", "algoId")})
