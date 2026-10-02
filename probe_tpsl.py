# 清理: 撤掉所有孤立挂单(无持仓的TP/SL)与遗留委托
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
for a in (c.get_algo_pending().get("data") or []):
    print("cancel algo", a.get("instId"), a.get("algoId"), json.dumps(c.cancel_algo(a.get("instId"), a.get("algoId")), ensure_ascii=False)[:110])
for a in (c.get_pending_orders().get("data") or []):
    print("cancel ord", a.get("instId"), a.get("ordId"), json.dumps(c.cancel_order(a.get("instId"), a.get("ordId")), ensure_ascii=False)[:110])
import time; time.sleep(2)
print("FINAL POS:", [(p.get("instId"), p.get("pos")) for p in (c.get_positions().get("data") or []) if float(p.get("pos") or 0) != 0])
print("FINAL ALGO:", [(a.get("instId"), a.get("tpTriggerPx"), a.get("slTriggerPx")) for a in (c.get_algo_pending().get("data") or [])])
print("FINAL ORD:", [(a.get("instId"), a.get("sz"), a.get("state")) for a in (c.get_pending_orders().get("data") or [])])
