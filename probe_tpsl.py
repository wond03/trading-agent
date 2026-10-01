# 诊断4: 找"同时保留 TP+SL"的写法
import sys, os, json, time, requests
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
inst = "BTC-USDT-SWAP"
F = ("algoId", "ordType", "side", "posSide", "sz", "closeFraction",
     "tpTriggerPx", "tpOrdPx", "slTriggerPx", "slOrdPx", "state")

def show(tag):
    for a in (c.get_algo_pending(inst_id=inst).get("data") or []):
        print(tag, json.dumps({k: a.get(k) for k in F}, ensure_ascii=False))

def clean():
    for a in (c.get_algo_pending(inst_id=inst).get("data") or []):
        c.cancel_algo(inst, a["algoId"])
    time.sleep(1)

pos = (c.get_positions(inst_id=inst).get("data") or [{}])[0]
sz = pos.get("pos")
print("POS_SZ=", sz, "avg=", pos.get("avgPx"))

clean()
print("T2: conditional + sz + tp + sl")
print("resp:", json.dumps(c._post("/api/v5/trade/order-algo", {
    "instId": inst, "tdMode": "isolated", "side": "sell", "posSide": "long",
    "ordType": "conditional", "sz": str(sz),
    "tpTriggerPx": "87747.8", "tpOrdPx": "-1", "slTriggerPx": "84527.6", "slOrdPx": "-1"}),
    ensure_ascii=False)[:200]); time.sleep(1.5); show("T2"); clean()

print("T3: oco + sz + tp + sl")
print("resp:", json.dumps(c._post("/api/v5/trade/order-algo", {
    "instId": inst, "tdMode": "isolated", "side": "sell", "posSide": "long",
    "ordType": "oco", "sz": str(sz),
    "tpTriggerPx": "87747.8", "tpOrdPx": "-1", "slTriggerPx": "84527.6", "slOrdPx": "-1"}),
    ensure_ascii=False)[:200]); time.sleep(1.5); show("T3"); clean()

print("T4: 两条独立 conditional (tp-only + sl-only)")
c.place_tpsl(inst, "long", tp=87747.8); time.sleep(1)
c.place_tpsl(inst, "long", sl=84527.6); time.sleep(1.5); show("T4")
print("（保持 T4 的两条挂单）")
