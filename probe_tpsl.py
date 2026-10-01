# 诊断9: 验证 amend-algos 能否改 attached 策略单的 SL (为"移动止损同步"铺路)
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
INST = "BTC-USDT-SWAP"

c.set_leverage(INST, 100, pos_side="short")
r = c._post("/api/v5/trade/order", {
    "instId": INST, "tdMode": "isolated", "side": "sell", "posSide": "short",
    "ordType": "market", "sz": "0.01",
    "attachAlgoOrds": [{"tpTriggerPx": "83500", "tpOrdPx": "-1", "slTriggerPx": "85600", "slOrdPx": "-1"}]})
oid = (r.get("data") or [{}])[0].get("ordId"); time.sleep(2)
od = (c.get_order(INST, oid).get("data") or [{}])[0]
aid = (od.get("attachAlgoOrds") or [{}])[0].get("attachAlgoId")
print("ATTACH_ALGO_ID=", aid, "tp/sl=", (od.get("attachAlgoOrds") or [{}])[0].get("tpTriggerPx"),
      (od.get("attachAlgoOrds") or [{}])[0].get("slTriggerPx"))

print("AMEND resp:", json.dumps(c._post("/api/v5/trade/amend-algos", {
    "instId": INST, "algoId": aid, "newSlTriggerPx": "85400", "newSlOrdPx": "-1"}), ensure_ascii=False)[:250])
time.sleep(1.5)
od2 = (c.get_order(INST, oid).get("data") or [{}])[0]
print("AFTER_AMEND tp/sl=", (od2.get("attachAlgoOrds") or [{}])[0].get("tpTriggerPx"),
      (od2.get("attachAlgoOrds") or [{}])[0].get("slTriggerPx"))

print("收尾: 平空单")
c.close_position(INST, "buy", "0.01", td_mode="isolated", pos_side="short"); time.sleep(1.5)
print("SHORT_LEFT=", [p.get("pos") for p in (c.get_positions(inst_id=INST).get("data") or []) if p.get("posSide") == "short"])
