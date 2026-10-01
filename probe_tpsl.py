# 核验2: 打印原始返回, 确认持仓是否真存在
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
r = c.get_positions()
print("POS_RAW code=", r.get("code"), "msg=", r.get("msg"), "n=", len(r.get("data") or []))
for p in (r.get("data") or []):
    print("  POS", p.get("instId"), p.get("posSide"), "pos=", p.get("pos"), "avg=", p.get("avgPx"))
r2 = c.get_positions(inst_id="BTC-USDT-SWAP")
print("POS_BTC n=", len(r2.get("data") or []), json.dumps(r2, ensure_ascii=False)[:400])
