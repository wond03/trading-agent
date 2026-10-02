# 诊断: XAU 市价单成交延迟有多长 (占位测试, 结束会平仓)
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
INST = "XAU-USDT-SWAP"
c.set_leverage(INST, 50, pos_side="long")
r = c.place_order(INST, "buy", 60, td_mode="isolated", pos_side="long")
oid = (r.get("data") or [{}])[0].get("ordId")
print("PLACED=", json.dumps(r, ensure_ascii=False)[:160])
t0 = time.time()
last = None
for k in range(40):            # 最多约 120 秒
    od = (c.get_order(INST, oid).get("data") or [{}])[0]
    st = od.get("state"); fl = float(od.get("accFillSz") or 0); av = od.get("avgPx")
    if (st, fl) != last:
        print(f"t={time.time()-t0:5.1f}s state={st} fill={fl} avgPx={av}")
        last = (st, fl)
    if fl > 0 or st in ("filled", "canceled"):
        break
    time.sleep(3)
print("ELAPSED=", round(time.time()-t0, 1))
pos = [p for p in (c.get_positions(inst_id=INST).get("data") or []) if p.get("posSide") == "long"]
print("POS=", [(p.get("pos"), p.get("avgPx")) for p in pos])
sz = abs(float(pos[0].get("pos"))) if pos else 0
if sz > 0:
    c.close_position(INST, "sell", sz, td_mode="isolated", pos_side="long"); time.sleep(2)
print("AFTER_CLOSE=", [(p.get("pos")) for p in (c.get_positions(inst_id=INST).get("data") or [])])
