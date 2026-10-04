# 跟进: 盯住黄金那笔"平半仓"订单(演示盘撮合慢), 成交后按剩余张数重挂保护单
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

ORD = os.environ.get("ORD_ID", "3978862353383325696")
INST = "XAU-USDT-SWAP"

c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)


def pos_now():
    rows = [x for x in (c.get_positions(inst_id=INST).get("data") or [])
            if float(x.get("pos") or 0) != 0 and x.get("posSide") == "short"]
    return float(rows[0]["pos"]) if rows else 0.0


def algos():
    tp = sl = None
    for a in (c.get_algo_pending(inst_type="SWAP", inst_id=INST).get("data") or []):
        if a.get("tpTriggerPx"):
            tp = a
        if a.get("slTriggerPx"):
            sl = a
    return tp, sl


print(f"起始持仓 {pos_now()} 张; 监控订单 {ORD}", flush=True)
filled = 0.0
state = None
for k in range(24):                     # 最多盯 ~4 分钟
    od = (c.get_order(INST, ORD).get("data") or [{}])[0]
    state = od.get("state")
    filled = float(od.get("accFillSz") or 0)
    print(f"  [{k*10}s] state={state} accFillSz={filled} avgPx={od.get('avgPx')}", flush=True)
    if filled > 0 or state in ("filled", "canceled"):
        break
    time.sleep(10)

p = pos_now()
print(f"\n结果: 订单 state={state} 成交={filled} | 当前持仓={p} 张", flush=True)
if p > 0 and filled > 0:
    tp_a, sl_a = algos()
    gtp = float(tp_a["tpTriggerPx"]) if tp_a else None
    gsl = float(sl_a["slTriggerPx"]) if sl_a else None
    cur_sz = float(tp_a["sz"]) if tp_a else None
    print(f"  现有挂单: 止盈={gtp}({cur_sz}张) 止损={gsl}({sl_a.get('sz') if sl_a else '-'}张)")
    if cur_sz != p:                     # 挂单张数与持仓不符 → 撤了按持仓张数重挂
        for a in (tp_a, sl_a):
            if a:
                r = c.cancel_algo(INST, a["algoId"])
                print(f"  撤 algoId={a['algoId']} -> {((r.get('data') or [{}])[0] or {}).get('sCode')}")
        for k2, fn, px in (("止盈", c.place_tp_order, gtp), ("止损", c.place_sl_order, gsl)):
            r = fn(INST, "short", p, "isolated", px)
            dd = ((r.get("data") or [{}])[0] or {})
            print(f"  重挂{k2} sz={p} px={px} sCode={dd.get('sCode')} algoId={dd.get('algoId')}")
print("完成", flush=True)
