# 查成交/平仓历史, 定位 BTC 仓位何时如何被平
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
print("=== FILLS BTC ===")
for f in (c.get_fills(inst_id="BTC-USDT-SWAP", limit=10).get("data") or []):
    print("  ", f.get("ts"), f.get("side"), f.get("posSide"), "fillSz=", f.get("fillSz"), "px=", f.get("fillPx"), "ordType=", f.get("ordType"), "clOrdId=", f.get("clOrdId"))
print("=== FILLS XAU ===")
for f in (c.get_fills(inst_id="XAU-USDT-SWAP", limit=10).get("data") or []):
    print("  ", f.get("ts"), f.get("side"), f.get("posSide"), "fillSz=", f.get("fillSz"), "px=", f.get("fillPx"), "ordType=", f.get("ordType"))
print("=== POSITIONS-HISTORY ===")
try:
    h = c._get("/api/v5/account/positions-history", {"instType": "SWAP", "limit": "10"})
    for x in (h.get("data") or []):
        print("  ", x.get("instId"), x.get("posSide"), "openAvg=", x.get("openAvgPx"), "closeAvg=", x.get("closeAvgPx"),
              "closeType=", x.get("type"), "realPnl=", x.get("realizedPnl"), "utime=", x.get("uTime"))
except Exception as e:
    print("err", e)
