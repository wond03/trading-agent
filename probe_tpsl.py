# 诊断8: attachAlgoOrds 后, TP/SL 记在哪 (订单明细 + 持仓全字段)
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
oid = (r.get("data") or [{}])[0].get("ordId")
print("ORD=", oid); time.sleep(2)
od = (c.get_order(INST, oid).get("data") or [{}])[0]
print("ORDER_ATTACH=", json.dumps(od.get("attachAlgoOrds"), ensure_ascii=False))
print("ORDER_SL_TP=", od.get("slTriggerPx"), od.get("tpTriggerPx"), "state=", od.get("state"))
for p in (c.get_positions(inst_id=INST).get("data") or []):
    if p.get("posSide") == "short":
        print("POS_FIELDS=", json.dumps({k: v for k, v in p.items() if "p" in k.lower() or "l" in k.lower() or "s" in k.lower()}, ensure_ascii=False)[:600])
# 待查: 无过滤的 algo-pending
print("ALGO_NOFILTER=", json.dumps(c._get("/api/v5/trade/orders-algo-pending", {"instType": "SWAP"}), ensure_ascii=False)[:300])
print("收尾: 平空单")
c.close_position(INST, "buy", "0.01", td_mode="isolated", pos_side="short"); time.sleep(1.5)
print("SHORT_LEFT=", [p.get("pos") for p in (c.get_positions(inst_id=INST).get("data") or []) if p.get("posSide") == "short"])
