# OKX 模拟盘诊断: 查真实持仓 + 打印下单返回的 code/sCode/sMsg (定位为什么订单没开上)
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)

print("=== 1) 账户 ===")
bal = c.get_balance()
if bal.get("code") == "0":
    d = bal["data"][0]
    print("acctLv:", d.get("acctLv"), "| posMode:", d.get("posMode"), "| totalEq:", d.get("totalEq"))
    for det in d.get("details", []):
        if float(det.get("eq", 0) or 0) > 0:
            print("   ", det.get("ccy"), "eq", det.get("eq"), "avail", det.get("availBal"))
else:
    print("   balance err:", json.dumps(bal, ensure_ascii=False)[:300])

print("=== 2) 当前真实持仓 ===")
pos = c.get_positions()
if pos.get("code") == "0":
    if not pos.get("data"):
        print("   （无持仓）")
    for p in pos["data"]:
        print("   ", p.get("instId"), p.get("posSide"), "pos=", p.get("pos"), "avgPx=", p.get("avgPx"), "upl=", p.get("upl"))
else:
    print("   positions err:", json.dumps(pos, ensure_ascii=False)[:300])

def try_order(inst, sz, ps, side):
    print(f"\n-- {inst} 设杠杆100x --")
    print("   ", json.dumps(c.set_leverage(inst, 100, "isolated", pos_side=ps), ensure_ascii=False)[:200])
    r = c.place_order(inst, side, sz, td_mode="isolated", pos_side=ps)
    print(f"-- {inst} 下单 sz={sz} 返回 --")
    print("   raw:", json.dumps(r, ensure_ascii=False)[:600])
    if r.get("code") == "0" and r.get("data"):
        dd = r["data"][0]
        print("   >>> ordId:", dd.get("ordId"), "| sCode:", dd.get("sCode"), "| sMsg:", dd.get("sMsg"))

print("=== 3) 按引擎的方式真实试单 ===")
try_order("XAU-USDT-SWAP", "120", "long", "buy")   # 与07:01那笔完全一致
try_order("BTC-USDT-SWAP", "0.59", "long", "buy")

print("\n=== 4) 试单后再查持仓 ===")
pos2 = c.get_positions()
if pos2.get("code") == "0":
    if not pos2.get("data"):
        print("   （仍无持仓 → 订单确实没成交）")
    for p in pos2["data"]:
        print("   ", p.get("instId"), p.get("posSide"), "pos=", p.get("pos"), "avgPx=", p.get("avgPx"))
