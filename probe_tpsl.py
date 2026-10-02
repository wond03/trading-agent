# 收尾: 平掉测试遗留的游离 XAU 持仓
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
for p in (c.get_positions().get("data") or []):
    if float(p.get("pos") or 0) != 0:
        sz = abs(float(p.get("pos"))); ps = p.get("posSide")
        side = "sell" if ps == "long" else "buy"
        print("CLOSE", p.get("instId"), ps, sz, json.dumps(c.close_position(p["instId"], side, sz, td_mode="isolated", pos_side=ps), ensure_ascii=False)[:150])
time.sleep(2)
print("FINAL POS:", [(p.get("instId"), p.get("posSide"), p.get("pos")) for p in (c.get_positions().get("data") or []) if float(p.get("pos") or 0) != 0])
print("FINAL TP/SL:", [(a.get("instId"), a.get("tpTriggerPx"), a.get("slTriggerPx")) for a in (c.get_algo_pending().get("data") or [])])
