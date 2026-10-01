# 诊断12: reduceOnly 方案全流程验证 (挂TP+SL -> 撤SL -> 改SL重挂)
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
INST = "BTC-USDT-SWAP"
F = ("algoId", "ordType", "side", "posSide", "sz", "reduceOnly", "tpTriggerPx", "slTriggerPx", "state")

def li(tag):
    d = c.get_algo_pending(inst_id=INST).get("data") or []
    print(f"{tag} n={len(d)}")
    for a in d:
        print("   ", json.dumps({k: a.get(k) for k in F}, ensure_ascii=False))

def clean():
    for a in (c.get_algo_pending(inst_id=INST).get("data") or []):
        print("  cancel", a["algoId"], json.dumps(c.cancel_algo(INST, a["algoId"]), ensure_ascii=False)[:120])
    time.sleep(1)

clean()
c.set_leverage(INST, 100, pos_side="short")
c._post("/api/v5/trade/order", {"instId": INST, "tdMode": "isolated", "side": "sell", "posSide": "short", "ordType": "market", "sz": "0.01"})
time.sleep(2)
BT = {"instId": INST, "tdMode": "isolated", "side": "buy", "posSide": "short", "ordType": "conditional", "sz": "0.01", "reduceOnly": True}
print("PLACE_TP:", json.dumps(c._post("/api/v5/trade/order-algo", dict(BT, tpTriggerPx="83500", tpOrdPx="-1")), ensure_ascii=False)[:160])
time.sleep(1)
rsl = c._post("/api/v5/trade/order-algo", dict(BT, slTriggerPx="85600", slOrdPx="-1"))
print("PLACE_SL:", json.dumps(rsl, ensure_ascii=False)[:160]); time.sleep(1.5); li("STEP1")

slid = rsl["data"][0]["algoId"]
print("CANCEL_SL:", json.dumps(c.cancel_algo(INST, slid), ensure_ascii=False)[:160]); time.sleep(1.5); li("STEP2")
print("REPLACE_SL:", json.dumps(c._post("/api/v5/trade/order-algo", dict(BT, slTriggerPx="85400", slOrdPx="-1")), ensure_ascii=False)[:160]); time.sleep(1.5); li("STEP3")

print("cleanup")
clean()
c._post("/api/v5/trade/close-position", {"instId": INST, "mgnMode": "isolated", "posSide": "short", "autoCxl": True}); time.sleep(1)
print("SHORT_LEFT=", [p.get("pos") for p in (c.get_positions(inst_id=INST).get("data") or []) if p.get("posSide") == "short"])
