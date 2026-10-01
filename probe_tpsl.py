# 诊断2: 逐项测试 持仓TP/SL 策略委托, 定位 TP 为何没进单
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
inst = "BTC-USDT-SWAP"

def dump(tag):
    d = c.get_algo_pending(inst_id=inst).get("data") or []
    print(tag, json.dumps(d, ensure_ascii=False)[:900])

def clean():
    for a in (c.get_algo_pending(inst_id=inst).get("data") or []):
        c.cancel_algo(inst, a["algoId"])
    time.sleep(1)

clean()
print("== A: only SL ==")
r = c.place_tpsl(inst, "long", sl=84527.6)
print("resp:", json.dumps(r, ensure_ascii=False)[:300]); time.sleep(1.5); dump("PEND_SL:"); clean()

print("== B: only TP ==")
r = c.place_tpsl(inst, "long", tp=87747.8)
print("resp:", json.dumps(r, ensure_ascii=False)[:300]); time.sleep(1.5); dump("PEND_TP:"); clean()

print("== C: TP+SL ==")
r = c.place_tpsl(inst, "long", tp=87747.8, sl=84527.6)
print("resp:", json.dumps(r, ensure_ascii=False)[:300]); time.sleep(1.5); dump("PEND_BOTH:")
for a in (c.get_algo_pending(inst_id=inst).get("data") or []):
    print("DETAIL:", json.dumps(c.get_algo(inst, a["algoId"]), ensure_ascii=False)[:900])

print("== FINAL: keep TP+SL ==")
clean()
c.place_tpsl(inst, "long", tp=87747.8, sl=84527.6); time.sleep(1.5); dump("FINAL:")
