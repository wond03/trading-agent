# 诊断10: 两条独立 conditional 委托(tp-only + sl-only) 能否共存
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
INST = "BTC-USDT-SWAP"
F = ("algoId", "ordType", "side", "posSide", "closeFraction", "tpTriggerPx", "slTriggerPx", "state")

def clean():
    for a in (c.get_algo_pending(inst_id=INST).get("data") or []):
        c.cancel_algo(INST, a["algoId"])
    time.sleep(1)

def show(tag):
    d = c.get_algo_pending(inst_id=INST).get("data") or []
    print(f"{tag} n={len(d)}")
    for a in d:
        print("   ", json.dumps({k: a.get(k) for k in F}, ensure_ascii=False))

clean()
r1 = c.place_tpsl(INST, "long", tp=87747.8)
print("R1_TP=", json.dumps(r1, ensure_ascii=False)[:200])
time.sleep(1)
r2 = c.place_tpsl(INST, "long", sl=84527.6)
print("R2_SL=", json.dumps(r2, ensure_ascii=False)[:200])
time.sleep(1.5); show("BOTH")
