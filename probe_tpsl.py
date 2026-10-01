# 收尾: 平掉测试遗留的 XAU 小仓, 并给出最终账号状态
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)

for p in (c.get_positions().get("data") or []):
    if p.get("instId") == "XAU-USDT-SWAP" and float(p.get("pos") or 0) != 0:
        sz = abs(float(p.get("pos")))
        ps = p.get("posSide")
        side = "sell" if ps == "long" else "buy"
        print("CLOSE_XAU", ps, sz, json.dumps(c.close_position("XAU-USDT-SWAP", side, sz, td_mode="isolated", pos_side=ps), ensure_ascii=False)[:200])
time.sleep(2)
print("=== FINAL POSITIONS ===")
for p in (c.get_positions().get("data") or []):
    print("  ", p.get("instId"), p.get("posSide"), "pos=", p.get("pos"), "avg=", p.get("avgPx"))
print("=== FINAL TP/SL ===")
for a in (c.get_algo_pending().get("data") or []):
    print("  ", a.get("instId"), a.get("posSide"), "sz=", a.get("sz"), "tp=", a.get("tpTriggerPx"), "sl=", a.get("slTriggerPx"))
