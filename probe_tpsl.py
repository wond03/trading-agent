# 诊断11: ①cancel attached 是否可行 ②sz+reduceOnly 的独立条件单能否多条共存
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
INST = "BTC-USDT-SWAP"
F = ("algoId", "ordType", "side", "posSide", "sz", "closeFraction", "reduceOnly", "tpTriggerPx", "slTriggerPx", "state")

def show(tag):
    d = c.get_algo_pending(inst_id=INST).get("data") or []
    print(f"{tag} n={len(d)}")
    for a in d:
        print("   ", json.dumps({k: a.get(k) for k in F}, ensure_ascii=False))

def clean():
    for a in (c.get_algo_pending(inst_id=INST).get("data") or []):
        c.cancel_algo(INST, a["algoId"])
    time.sleep(1)

# 开一个小额空单
c.set_leverage(INST, 100, pos_side="short")
r = c._post("/api/v5/trade/order", {"instId": INST, "tdMode": "isolated", "side": "sell", "posSide": "short",
    "ordType": "market", "sz": "0.01", "attachAlgoOrds": [{"tpTriggerPx": "83500", "tpOrdPx": "-1", "slTriggerPx": "85600", "slOrdPx": "-1"}]})
oid = (r.get("data") or [{}])[0].get("ordId"); time.sleep(2)

print("== 1. cancel attached (用 attachAlgoId) ==")
od = (c.get_order(INST, oid).get("data") or [{}])[0]
aid = (od.get("attachAlgoOrds") or [{}])[0].get("attachAlgoId")
print("attachAlgoId=", aid)
print("cancel resp:", json.dumps(c.cancel_algo(INST, aid), ensure_ascii=False)[:250])
time.sleep(1.5)
od2 = (c.get_order(INST, oid).get("data") or [{}])[0]
print("after cancel attach=", json.dumps(od2.get("attachAlgoOrds"), ensure_ascii=False)[:300])

print("== 2. sz+reduceOnly 独立条件单: tp-only 再 sl-only ==")
b = {"instId": INST, "tdMode": "isolated", "side": "buy", "posSide": "short", "ordType": "conditional", "sz": "0.01", "reduceOnly": True}
print("R_tp:", json.dumps(c._post("/api/v5/trade/order-algo", dict(b, tpTriggerPx="83500", tpOrdPx="-1")), ensure_ascii=False)[:220])
time.sleep(1)
print("R_sl:", json.dumps(c._post("/api/v5/trade/order-algo", dict(b, slTriggerPx="85600", slOrdPx="-1")), ensure_ascii=False)[:220])
time.sleep(1.5); show("SZ_REDUCEONLY")

print("收尾")
clean()
c._post("/api/v5/trade/close-position", {"instId": INST, "mgnMode": "isolated", "posSide": "short", "autoCxl": True})
time.sleep(1)
print("SHORT_LEFT=", [p.get("pos") for p in (c.get_positions(inst_id=INST).get("data") or []) if p.get("posSide") == "short"])
