# 诊断7: attachAlgoOrds 路线 (开仓附带TP/SL), 用小额BTC空单, 不碰现有持仓
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
c.set_leverage(INST, 100, pos_side="short")
r = c._post("/api/v5/trade/order", {
    "instId": INST, "tdMode": "isolated", "side": "sell", "posSide": "short",
    "ordType": "market", "sz": "0.01",
    "attachAlgoOrds": [{"tpTriggerPx": "83500", "tpOrdPx": "-1", "slTriggerPx": "85600", "slOrdPx": "-1"}]})
print("ORDER_RESP=", json.dumps(r, ensure_ascii=False)[:250]); time.sleep(2)
ps = [p for p in (c.get_positions(inst_id=INST).get("data") or []) if p.get("posSide") == "short"]
print("SHORT_POS=", [{k: p.get(k) for k in ("pos", "avgPx")} for p in ps])
allpend("AFTER_ATTACH")
print("收尾: 平掉测试空单")
c.close_position(INST, "buy", "0.01", td_mode="isolated", pos_side="short"); time.sleep(1.5)
clean()
print("SHORT_LEFT=", [p.get("pos") for p in (c.get_positions(inst_id=INST).get("data") or []) if p.get("posSide") == "short"])
