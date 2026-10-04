# 一次性: 黄金持仓减半(60→30) —— 多种下单方式依次尝试, 每种都不成交就撤单换下一种
#   目标: 定位"为什么上一轮市价/穿盘口限价都不成交"
import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

INST, PS, TD = "XAU-USDT-SWAP", "short", "isolated"
c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)


def getpos():
    for x in (c.get_positions(INST).get("data") or []):
        if abs(float(x.get("pos") or 0)) > 0:
            return x
    return None


p = getpos()
print("① 当前持仓:", json.dumps({k: p.get(k) for k in ("pos", "posSide", "avgPx", "margin", "lever")},
                             ensure_ascii=False) if p else "无")
if not p:
    print("无持仓, 退出"); sys.exit()
cur = abs(float(p["pos"]))

algo = c.get_algo_pending(inst_id=INST).get("data") or []
print("② 当前条件单:", [(a.get("algoId"), a.get("tpTriggerPx"), a.get("slTriggerPx"), a.get("sz")) for a in algo])
tp_px = next((a.get("tpTriggerPx") for a in algo if a.get("tpTriggerPx")), None)
sl_px = next((a.get("slTriggerPx") for a in algo if a.get("slTriggerPx")), None)

t = (c._get("/api/v5/market/ticker", {"instId": INST}).get("data") or [{}])[0]
bid, ask, tick = float(t["bidPx"]), float(t["askPx"]), c.get_tick(INST)
print(f"③ 盘口: last={t['last']} bid={bid} ask={ask} tick={tick}")

sz = c.round_sz(INST, cur / 2)
print(f"④ 减半目标: {cur} → 平掉 {sz} 张")


def attempt(tag, body, wait=20):
    r = c._post("/api/v5/trade/order", body)
    dd = (r.get("data") or [{}])[0]
    print(f"[{tag}] resp: {json.dumps(r, ensure_ascii=False)[:260]}")
    if r.get("code") != "0" or dd.get("sCode") != "0":
        print(f"[{tag}] ❌ 被拒 sCode={dd.get('sCode')} {dd.get('sMsg')}")
        return False
    oid = dd.get("ordId")
    for _ in range(wait):
        time.sleep(1)
        od = (c.get_order(INST, oid).get("data") or [{}])[0]
        if float(od.get("accFillSz") or 0) > 0 or od.get("state") in ("filled", "partially_filled", "canceled"):
            print(f"[{tag}] 状态={od.get('state')} 成交={od.get('accFillSz')} 均价={od.get('avgPx')}")
            return float(od.get("accFillSz") or 0) > 0
    od = (c.get_order(INST, oid).get("data") or [{}])[0]
    print(f"[{tag}] ⏳{wait}s未成交(状态={od.get('state')} 成交={od.get('accFillSz')}) → 撤单")
    c.cancel_order(INST, oid)
    time.sleep(2)
    return False


done = False
for tag, body in [
    ("M1 市价 reduceOnly", {"instId": INST, "tdMode": TD, "side": "buy", "posSide": PS,
                            "ordType": "market", "sz": str(sz), "reduceOnly": "true"}),
    ("M2 限价=卖一(穿盘口) reduceOnly", {"instId": INST, "tdMode": TD, "side": "buy", "posSide": PS,
                                        "ordType": "limit", "px": str(c.round_tick(INST, ask)),
                                        "sz": str(sz), "reduceOnly": "true"}),
    ("M3 限价=卖一+3tick 不设reduceOnly", {"instId": INST, "tdMode": TD, "side": "buy", "posSide": PS,
                                          "ordType": "limit", "px": str(c.round_tick(INST, ask + tick * 3)),
                                          "sz": str(sz)}),
    ("M4 市价 不设reduceOnly", {"instId": INST, "tdMode": TD, "side": "buy", "posSide": PS,
                                "ordType": "market", "sz": str(sz)}),
]:
    if done:
        break
    if attempt(tag, body):
        print(f"✅ {tag} 成交")
        done = True

time.sleep(2)
p2 = getpos()
print("⑤ 平后持仓:", json.dumps({k: p2.get(k) for k in ("pos", "avgPx", "margin")}, ensure_ascii=False) if p2 else "无")

if done and p2:
    print("⑥ 重挂 TP/SL 到新张数")
    for a in (c.get_algo_pending(inst_id=INST).get("data") or []):
        print("   撤", a.get("algoId"), c.cancel_algo(INST, a.get("algoId")).get("code"))
    time.sleep(1)
    ns = abs(float(p2["pos"]))
    if tp_px:
        print("   挂TP", tp_px, "张", ns, c.place_tp_order(INST, PS, ns, TD, float(tp_px)).get("code"))
    if sl_px:
        print("   挂SL", sl_px, "张", ns, c.place_sl_order(INST, PS, ns, TD, float(sl_px)).get("code"))
    print("   剩余条件单:", [(a.get("algoId"), a.get("tpTriggerPx"), a.get("slTriggerPx"), a.get("sz"))
                       for a in (c.get_algo_pending(inst_id=INST).get("data") or [])])
else:
    print("⑥ 未成交, 持仓与原条件单保持不动")
print("完成")
