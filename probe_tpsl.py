# 诊断: XAU 盘口 + 限价单能否成交
import sys, os, json, time, requests
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)
INST = "XAU-USDT-SWAP"
tk = requests.get("https://www.okx.com/api/v5/market/ticker", params={"instId": INST}, timeout=10).json()
print("TICKER=", json.dumps(tk.get("data"), ensure_ascii=False)[:300])
bk = requests.get("https://www.okx.com/api/v5/market/books", params={"instId": INST, "sz": "5"}, timeout=10).json()
print("BOOK_ASKS=", json.dumps((bk.get("data") or [{}])[0].get("asks"), ensure_ascii=False))
print("BOOK_BIDS=", json.dumps((bk.get("data") or [{}])[0].get("bids"), ensure_ascii=False))

c.set_leverage(INST, 50, pos_side="long")
ask = float(((bk.get("data") or [{}])[0].get("asks") or [["0"]])[0][0])
px = c.round_tick(INST, ask + c.get_tick(INST))
print("LIMIT_BUY_AT=", px)
r = c._post("/api/v5/trade/order", {"instId": INST, "tdMode": "isolated", "side": "buy",
                                    "posSide": "long", "ordType": "limit", "sz": "60", "px": str(px)})
oid = (r.get("data") or [{}])[0].get("ordId")
print("PLACED=", json.dumps(r, ensure_ascii=False)[:160])
t0 = time.time()
for k in range(12):
    od = (c.get_order(INST, oid).get("data") or [{}])[0]
    print(f"t={time.time()-t0:5.1f}s state={od.get('state')} fill={od.get('accFillSz')} avg={od.get('avgPx')}")
    if float(od.get("accFillSz") or 0) > 0 or od.get("state") in ("filled", "canceled"):
        break
    time.sleep(3)
pos = [p for p in (c.get_positions(inst_id=INST).get("data") or []) if p.get("posSide") == "long"]
print("POS=", [(p.get("pos"), p.get("avgPx")) for p in pos])
sz = abs(float(pos[0].get("pos"))) if pos else 0
if sz > 0:
    c.close_position(INST, "sell", sz, td_mode="isolated", pos_side="long"); time.sleep(2)
print("AFTER_CLOSE=", [(p.get("pos")) for p in (c.get_positions(inst_id=INST).get("data") or [])])
