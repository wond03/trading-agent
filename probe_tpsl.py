# 诊断6: 找出能"同时保留 TP+SL"的方法 (含 attachAlgoOrds 路线)
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
INST = "BTC-USDT-SWAP"
F = ("algoId", "ordType", "side", "posSide", "sz", "closeFraction",
     "tpTriggerPx", "tpOrdPx", "slTriggerPx", "slOrdPx", "state")

def allpend(tag, inst=INST):
    d = c.get_algo_pending(inst_id=inst).get("data") or []
    print(f"{tag} n={len(d)}")
    for a in d:
        print("   ", json.dumps({k: a.get(k) for k in F}, ensure_ascii=False))

def clean(inst=INST):
    for a in (c.get_algo_pending(inst_id=inst).get("data") or []):
        c.cancel_algo(inst, a["algoId"])
    time.sleep(1)

clean()
print("== A: conditional 组合, tp 更近(85000) ==")
c.place_tpsl(INST, "long", tp=85000, sl=84527.6); time.sleep(1.5); allpend("A"); clean()

print("== B: conditiona组合 + TriggerPxType=mark ==")
print("resp:", json.dumps(c._post("/api/v5/trade/order-algo", {
    "instId": INST, "tdMode": "isolated", "side": "sell", "posSide": "long",
    "ordType": "conditional", "closeFraction": "1",
    "tpTriggerPx": "87747.8", "tpOrdPx": "-1", "tpTriggerPxType": "mark",
    "slTriggerPx": "84527.6", "slOrdPx": "-1", "slTriggerPxType": "mark"}), ensure_ascii=False)[:200])
time.sleep(1.5); allpend("B"); clean()

print("== D: attachAlgoOrds (开仓时附带TP/SL) 路线, 用最小XAU单测试 ==")
XI = "XAU-USDT-SWAP"
c.set_leverage(XI, 50, pos_side="long")
r = c._post("/api/v5/trade/order", {
    "instId": XI, "tdMode": "isolated", "side": "buy", "posSide": "long",
    "ordType": "market", "sz": "1",
    "attachAlgoOrds": [{"tpTriggerPx": "4330", "tpOrdPx": "-1", "slTriggerPx": "4120", "slOrdPx": "-1"}]})
print("D_ORDER_RESP:", json.dumps(r, ensure_ascii=False)[:250]); time.sleep(2)
allpend("D_ALGO", XI)
for p in (c.get_positions(inst_id=XI).get("data") or []):
    print("D_POS", {k: p.get(k) for k in ("instId", "posSide", "pos", "avgPx")})
# 收尾: 撤单+平掉测试仓
clean(XI)
c.close_position(XI, "sell", "1", td_mode="isolated", pos_side="long"); time.sleep(1)
print("D_AFTER_CLOSE:", [(p.get("instId"), p.get("pos")) for p in (c.get_positions(inst_id=XI).get("data") or [])])
