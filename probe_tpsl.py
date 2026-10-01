# 一次性诊断: 验证 OKX 模拟盘能否给"持仓"挂上真实止盈止损(策略委托)
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
BASE = os.path.dirname(os.path.abspath(__file__))

print("TICK_BTC=", c.get_tick("BTC-USDT-SWAP"), "TICK_XAU=", c.get_tick("XAU-USDT-SWAP"))

def show(tag):
    poss = c.get_positions().get("data") or []
    print(tag, [(x.get("instId"), x.get("posSide"), x.get("pos"), "avg=" + str(x.get("avgPx")),
                 "tp=" + str(x.get("tpTriggerPx")), "sl=" + str(x.get("slTriggerPx"))) for x in poss])

show("BEFORE_POS:")

st = json.load(open(os.path.join(BASE, "engine", "state.json")))
for p in st.get("positions", []):
    inst = p["inst"]; ps = "long" if p["direction"] == "long" else "short"
    r = c.place_tpsl(inst, ps, td_mode="isolated", tp=p["tp"], sl=p["sl"], close_fraction="1")
    print("PLACE_TPSL", inst, ps, "tp=", c.round_tick(inst, p["tp"]), "sl=", c.round_tick(inst, p["sl"]),
          "->", json.dumps(r, ensure_ascii=False)[:400])

time.sleep(2)
show("AFTER_POS:")
alg = c.get_algo_pending().get("data") or []
print("ALGO_PENDING:", [(a.get("instId"), a.get("algoId"), a.get("tpTriggerPx"),
                         a.get("slTriggerPx"), a.get("closeFraction"), a.get("state")) for a in alg])
