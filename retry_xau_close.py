# 重试②: 撤掉卡住的市价平仓单 → 用【限价单穿盘口】平掉黄金一半 → 按剩余张数重挂保护单
import os
import sys
import json
import time
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

INST = "XAU-USDT-SWAP"
OLD_ORD = os.environ.get("OLD_ORD", "3978862353383325696")

c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)


def pos_row():
    rows = [x for x in (c.get_positions(inst_id=INST).get("data") or [])
            if float(x.get("pos") or 0) != 0 and x.get("posSide") == "short"]
    return rows[0] if rows else None


def algos():
    tp = sl = None
    for a in (c.get_algo_pending(inst_type="SWAP", inst_id=INST).get("data") or []):
        if a.get("tpTriggerPx"):
            tp = a
        if a.get("slTriggerPx"):
            sl = a
    return tp, sl


def ticker():
    try:
        d = requests.get("https://www.okx.com/api/v5/market/ticker",
                         params={"instId": INST}, timeout=20).json()
        t = (d.get("data") or [{}])[0]
        return float(t.get("bidPx") or 0), float(t.get("askPx") or 0)
    except Exception as e:
        print("   ticker 失败:", e)
        return 0.0, 0.0


print("① 撤掉卡住的旧平仓单", OLD_ORD)
try:
    r = c.cancel_order(INST, OLD_ORD)
    print("   cancel ->", r.get("code"), ((r.get("data") or [{}])[0] or {}).get("sCode"), r.get("msg"))
except Exception as e:
    print("   cancel 异常:", e)
try:
    pend = [x for x in (c.get_pending_orders(inst_type="SWAP").get("data") or []) if x.get("instId") == INST]
    print("   撤后仍在该合约挂单:", [(x.get("ordId"), x.get("state"), x.get("sz")) for x in pend])
except Exception as e:
    print("   查挂单失败", e)

row = pos_row()
if not row:
    print("② 无持仓, 结束"); raise SystemExit
sz0 = float(row["pos"]); avg = float(row["avgPx"])
print(f"② 当前持仓 {sz0} 张 @{avg} markPx={row.get('markPx')} last={row.get('last')}")
half = c.round_sz(INST, sz0 / 2.0)

bid, ask = ticker()
if ask <= 0:
    ask = max(float(row.get("markPx") or 0), float(row.get("last") or 0), avg) * 1.01
    print(f"   盘口取不到, 用 {ask:.2f} 兜底")
else:
    print(f"   盘口 bid={bid} ask={ask}")
px = c.round_tick(INST, ask * 1.005)

print(f"③ 限价平仓 {half} 张 @ {px} (穿盘口)")
body = {"instId": INST, "tdMode": "isolated", "side": "buy", "posSide": "short",
        "ordType": "limit", "sz": str(half), "px": str(px), "reduceOnly": True}
r = c._post("/api/v5/trade/order", body)
dd = ((r.get("data") or [{}])[0] or {})
print(f"   -> code={r.get('code')} sCode={dd.get('sCode')} ordId={dd.get('ordId')} msg={dd.get('sMsg') or r.get('msg')}")
filled = 0.0
if r.get("code") == "0" and dd.get("sCode") == "0" and dd.get("ordId"):
    for k in range(18):
        od = (c.get_order(INST, dd["ordId"]).get("data") or [{}])[0]
        filled = float(od.get("accFillSz") or 0)
        print(f"   [{k*5}s] state={od.get('state')} accFillSz={filled} avgPx={od.get('avgPx')}")
        if filled > 0 or od.get("state") in ("filled", "canceled"):
            break
        time.sleep(5)

time.sleep(1.0)
row = pos_row()
p = float(row["pos"]) if row else 0.0
print(f"④ 成交 {filled} 张 | 剩余持仓 {p} 张")
if p > 0 and filled > 0:
    tp_a, sl_a = algos()
    gtp = float(tp_a["tpTriggerPx"]) if tp_a else None
    gsl = float(sl_a["slTriggerPx"]) if sl_a else None
    cur = float(tp_a["sz"]) if tp_a and tp_a.get("sz") else None
    print(f"   现有挂单 止盈={gtp}({cur}张) 止损={gsl}({sl_a.get('sz') if sl_a else '-'}张)")
    if cur != p:
        for a in (tp_a, sl_a):
            if a:
                rr = c.cancel_algo(INST, a["algoId"])
                print(f"   撤 algoId={a['algoId']} -> {((rr.get('data') or [{}])[0] or {}).get('sCode')}")
        for k2, fn, px2 in (("止盈", c.place_tp_order, gtp), ("止损", c.place_sl_order, gsl)):
            rr = fn(INST, "short", p, "isolated", px2)
            d2 = ((rr.get("data") or [{}])[0] or {})
            print(f"   重挂{k2} sz={p} px={px2} sCode={d2.get('sCode')} algoId={d2.get('algoId')}")

print("⑤ 收尾")
row = pos_row()
if row:
    print(f"   {INST}: {row['pos']}张 @{row['avgPx']} 保证金={row.get('margin')} 名义={row.get('notionalUsd')} 杠杆={row.get('lever')} 爆仓={row.get('liqPx')}")
tp_a, sl_a = algos()
print(f"   挂单: 止盈={tp_a.get('tpTriggerPx') if tp_a else None}({tp_a.get('sz') if tp_a else '-'}) "
      f"止损={sl_a.get('slTriggerPx') if sl_a else None}({sl_a.get('sz') if sl_a else '-'})")
print("完成")
