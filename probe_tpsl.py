# 集成测试: 挂一笔 XAU 市价单(演示盘会挂住), 打印 ordId 供"挂单待成交"链路验证
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
INST = "XAU-USDT-SWAP"
c.set_leverage(INST, 50, pos_side="long")
r = c.place_order(INST, "buy", 60, td_mode="isolated", pos_side="long")
print("PLACE=", json.dumps(r, ensure_ascii=False)[:220])
oid = (r.get("data") or [{}])[0].get("ordId")
print("ORDID=", oid)
time.sleep(2)
od = (c.get_order(INST, oid).get("data") or [{}])[0]
print("STATE=", od.get("state"), "fill=", od.get("accFillSz"), "avg=", od.get("avgPx"))
