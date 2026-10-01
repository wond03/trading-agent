# 诊断5: 确认"两条独立委托"是否都保留; 并复核 oco
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
inst = "BTC-USDT-SWAP"
F = ("algoId", "ordType", "side", "posSide", "sz", "closeFraction",
     "tpTriggerPx", "tpOrdPx", "slTriggerPx", "slOrdPx", "state")

d = c.get_algo_pending(inst_id=inst).get("data") or []
print("PEND_COUNT=", len(d))
for a in d:
    print("PEND_ITEM", json.dumps({k: a.get(k) for k in F}, ensure_ascii=False))

# oco 完整响应
r = c._post("/api/v5/trade/order-algo", {
    "instId": inst, "tdMode": "isolated", "side": "sell", "posSide": "long",
    "ordType": "oco", "sz": "0.59",
    "tpTriggerPx": "87747.8", "tpOrdPx": "-1", "slTriggerPx": "84527.6", "slOrdPx": "-1"})
print("OCO_RESP=", json.dumps(r, ensure_ascii=False)[:400])
