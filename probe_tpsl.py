# 验证: 待成交订单的真实状态 vs 交易所持仓
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
OID = "3973070357083361280"
od = (c.get_order("XAU-USDT-SWAP", OID).get("data") or [{}])[0]
print("ORDER state=", od.get("state"), "accFillSz=", od.get("accFillSz"), "avgPx=", od.get("avgPx"))
print("POSITIONS:")
for p in (c.get_positions().get("data") or []):
    if float(p.get("pos") or 0) != 0:
        print("   ", p.get("instId"), p.get("posSide"), "pos=", p.get("pos"), "avg=", p.get("avgPx"))
print("FILLS XAU:")
for f in (c.get_fills(inst_id="XAU-USDT-SWAP", limit=5).get("data") or []):
    print("   ", f.get("ts"), f.get("side"), f.get("fillSz"), f.get("fillPx"), "ordId=", f.get("ordId"))
