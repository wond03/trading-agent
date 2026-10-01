# 诊断3: 明确打印 TP/SL 关键字段
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
inst = "BTC-USDT-SWAP"
F = ("algoId", "ordType", "side", "posSide", "closeFraction",
     "tpTriggerPx", "tpOrdPx", "slTriggerPx", "slOrdPx", "state")

def show(tag):
    for a in (c.get_algo_pending(inst_id=inst).get("data") or []):
        print(tag, json.dumps({k: a.get(k) for k in F}, ensure_ascii=False))

def clean():
    for a in (c.get_algo_pending(inst_id=inst).get("data") or []):
        c.cancel_algo(inst, a["algoId"])
    time.sleep(1)

clean()
print("B: only TP")
c.place_tpsl(inst, "long", tp=87747.8); time.sleep(1.5); show("TP_ONLY"); clean()
print("C: TP+SL")
c.place_tpsl(inst, "long", tp=87747.8, sl=84527.6); time.sleep(1.5); show("TP_SL")
print("最终保留 TP+SL 已挂")
