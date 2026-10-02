# 稳定核验: 多次重试取持仓, 避免接口偶发空返回
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
for k in range(3):
    r = c.get_positions()
    d = r.get("data") or []
    print(f"try{k} code={r.get('code')} n={len(d)}")
    for p in d:
        if float(p.get("pos") or 0) != 0:
            print("   POS", p.get("instId"), p.get("posSide"), "pos=", p.get("pos"), "avg=", p.get("avgPx"))
    time.sleep(1)
print("PENDING TP/SL:")
for a in (c.get_algo_pending().get("data") or []):
    print("   ", a.get("instId"), a.get("posSide"), "sz=", a.get("sz"), "tp=", a.get("tpTriggerPx"), "sl=", a.get("slTriggerPx"))
print("PENDING ORDERS:")
for a in (c.get_pending_orders().get("data") or []):
    print("   ", a.get("instId"), a.get("side"), a.get("sz"), a.get("ordType"), a.get("state"))
