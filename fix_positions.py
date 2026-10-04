# 一次性修正②: ① BTC 空单止盈改成 1:2  ② 黄金空单减半(60→30张, 让保证金回到 ~5U)
# 只在 GitHub Actions 上跑(需要 OKX 密钥); 每一步都打印交易所回执, 失败不掩盖
import os
import sys
import json
import time
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

CST = datetime.timezone(datetime.timedelta(hours=8))


def T(ts):
    v = float(ts or 0)
    if v > 1_000_000_000_000:
        v /= 1000.0
    return datetime.datetime.fromtimestamp(v, CST).strftime("%m-%d %H:%M:%S")


def pos_of(inst, pos_side):
    rows = [x for x in (c.get_positions(inst_id=inst).get("data") or [])
            if float(x.get("pos") or 0) != 0 and x.get("posSide") == pos_side]
    return rows[0] if rows else None


def algos_of(inst):
    """返回 (tp_algo, sl_algo) —— 从在挂条件单里挑出带 tpTriggerPx / slTriggerPx 的那两条"""
    tp = sl = None
    for a in (c.get_algo_pending(inst_type="SWAP", inst_id=inst).get("data") or []):
        if a.get("tpTriggerPx"):
            tp = a
        if a.get("slTriggerPx"):
            sl = a
    return tp, sl


def guard(inst, pos_side, sz, tp=None, sl=None, tag=""):
    """挂止盈/止损条件单(逐仓, reduceOnly), 打印交易所回执"""
    out = {}
    for k, fn, px in (("止盈", c.place_tp_order, tp), ("止损", c.place_sl_order, sl)):
        if px is None:
            continue
        try:
            r = fn(inst, pos_side, sz, "isolated", px)
            dd = ((r.get("data") or [{}])[0] or {})
            print(f"  [{tag}] 挂{k} sz={sz} 触发价={px} code={r.get('code')} sCode={dd.get('sCode')} "
                  f"algoId={dd.get('algoId')} msg={dd.get('sMsg') or r.get('msg')}")
            if r.get("code") == "0" and dd.get("sCode") == "0":
                out[k] = dd.get("algoId")
        except Exception as e:
            print(f"  [{tag}] 挂{k}异常 {e}")
    return out


c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

# ---------------- ① BTC: 止盈改 1:2 ----------------
print("#" * 78)
print("① BTC-USDT-SWAP 止盈改为 1:2")
p = pos_of("BTC-USDT-SWAP", "short")
if not p:
    print("  无 BTC 空仓, 跳过")
else:
    avg = float(p["avgPx"]); sz = float(p["pos"])
    tp_a, sl_a = algos_of("BTC-USDT-SWAP")
    sl_px = float(sl_a["slTriggerPx"]) if sl_a else None
    print(f"  持仓 {sz}张 @{avg} | 现有止损 {sl_px} | 现有止盈 {tp_a.get('tpTriggerPx') if tp_a else None}")
    if not sl_px:
        print("  !! 读不到止损触发价, 跳过(不乱算)")
    else:
        risk = sl_px - avg                     # 空单: 风险 = 止损 - 均价
        new_tp = c.round_tick("BTC-USDT-SWAP", avg - 2.0 * risk)
        print(f"  风险={risk:.1f} → 1:2 新止盈 = {new_tp}")
        if tp_a:
            r = c.cancel_algo("BTC-USDT-SWAP", tp_a["algoId"])
            print(f"  撤旧止盈 algoId={tp_a['algoId']} -> code={r.get('code')} sCode={((r.get('data') or [{}])[0] or {}).get('sCode')}")
        guard("BTC-USDT-SWAP", "short", sz, tp=new_tp, tag="BTC")

# ---------------- ② 黄金: 减半 ----------------
print("#" * 78)
print("② XAU-USDT-SWAP 持仓减半 (60 → 30 张)")
g = pos_of("XAU-USDT-SWAP", "short")
if not g:
    print("  无黄金空仓, 跳过")
else:
    gsz = float(g["pos"]); gavg = float(g["avgPx"])
    tp_a, sl_a = algos_of("XAU-USDT-SWAP")
    gtp = float(tp_a["tpTriggerPx"]) if tp_a else None
    gsl = float(sl_a["slTriggerPx"]) if sl_a else None
    print(f"  持仓 {gsz}张 @{gavg} | 止盈 {gtp} | 止损 {gsl}")
    half = c.round_sz("XAU-USDT-SWAP", gsz / 2.0)
    print(f"  拟平掉 {half} 张")
    # 先撤掉两条保护单(它们是按 60 张挂的)
    for a in (tp_a, sl_a):
        if a:
            r = c.cancel_algo("XAU-USDT-SWAP", a["algoId"])
            print(f"  撤单 algoId={a['algoId']} -> code={r.get('code')} sCode={((r.get('data') or [{}])[0] or {}).get('sCode')}")
    # 市价平掉一半(buy 平 short), 确认成交
    r = c.close_position("XAU-USDT-SWAP", "buy", half, td_mode="isolated", pos_side="short")
    dd = ((r.get("data") or [{}])[0] or {})
    print(f"  平仓 code={r.get('code')} sCode={dd.get('sCode')} ordId={dd.get('ordId')} msg={dd.get('sMsg') or r.get('msg')}")
    filled = 0.0
    if r.get("code") == "0" and dd.get("sCode") == "0" and dd.get("ordId"):
        for _ in range(8):
            od = (c.get_order("XAU-USDT-SWAP", dd["ordId"]).get("data") or [{}])[0]
            filled = float(od.get("accFillSz") or 0)
            if filled > 0 or od.get("state") in ("filled", "canceled"):
                print(f"  成交 {filled}张 @{od.get('avgPx')} state={od.get('state')}")
                break
            time.sleep(0.8)
    # 按剩余张数重新挂保护单
    time.sleep(1.0)
    left = pos_of("XAU-USDT-SWAP", "short")
    lsz = float(left["pos"]) if left else 0.0
    print(f"  剩余持仓 {lsz}张")
    if lsz > 0:
        guard("XAU-USDT-SWAP", "short", lsz, tp=gtp, sl=gsl, tag="XAU")

# ---------------- 结果 ----------------
print("#" * 78)
print("收尾核对")
for inst in ("BTC-USDT-SWAP", "XAU-USDT-SWAP"):
    p = pos_of(inst, "short")
    if p:
        print(f"  {inst}: {p['pos']}张 @{p['avgPx']} 保证金={p.get('margin')} 名义={p.get('notionalUsd')} "
              f"杠杆={p.get('lever')} 爆仓={p.get('liqPx')} upl={p.get('upl')}")
    else:
        print(f"  {inst}: 无持仓")
    tp_a, sl_a = algos_of(inst)
    print(f"     挂单: 止盈={tp_a.get('tpTriggerPx') if tp_a else None}({tp_a.get('sz') if tp_a else '-'}张) "
          f"止损={sl_a.get('slTriggerPx') if sl_a else None}({sl_a.get('sz') if sl_a else '-'}张)")
print("完成")
