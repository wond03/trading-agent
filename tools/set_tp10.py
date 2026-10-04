# -*- coding: utf-8 -*-
"""把【已持仓】的止盈改到「浮盈 = TP_USD 美元」的价位。
★2026-10-05 用户裁定 "止盈按10u给": 用 modifyTpSlOrder 改交易所端已有的 TP 条件单(不动止损)。
用法: 在 GitHub Actions 里跑(沙盒连不上 WEEX)。
"""
import json
import sys

sys.path.insert(0, "engine")
from weex_trade import WeexTrade, SYMBOL_MAP  # noqa: E402
import config as C  # noqa: E402

USD = float(getattr(C, "TP_USD", 10.0))
c = WeexTrade()
print("configured:", c.configured, "t_off:", c.sync_time())
c.load_specs()

st, pos = c.get_positions_raw()
rows = pos if isinstance(pos, list) else ((pos or {}).get("data") or [])
print(f"持仓数: {len(rows)}   目标浮盈 = {USD}U\n")

_st0, _all0 = c.algo_orders()
print(f"[DEBUG] 账户全部条件单 {len(_all0)} 条:")
for _a in _all0:
    print(f"   {_a.get('symbol')} {_a.get('positionSide')} {_a.get('orderType')} "
          f"trigger={_a.get('triggerPrice')} qty={_a.get('quantity')} status={_a.get('algoStatus')} id={_a.get('algoId')}")
print()

for x in rows:
    sym = (x.get("symbol") or "").upper()
    inst = next((k for k, v in SYMBOL_MAP.items() if v[0].upper() == sym), None)
    if not inst:
        print(f"跳过未知品种 {sym}")
        continue
    size = abs(float(x.get("size") or 0))
    ov = float(x.get("openValue") or 0)
    if size <= 0 or ov <= 0:
        continue
    avg = ov / size
    ps = (x.get("side") or "").upper()              # LONG / SHORT
    dist = USD / size                                # 价格距离 = 目标浮盈 / 数量(币)
    tp_r = c.round_trigger(inst, (avg - dist) if ps == "SHORT" else (avg + dist))
    print(f"=== {sym} {ps} size={size} 均价={avg:.4f} → 新止盈 {tp_r} (距离 {dist:.4f}) ===")
    _st, algos = c.algo_orders(inst)
    mine = [a for a in algos
            if (a.get("positionSide") or "").upper() == ps
            and (a.get("orderType") or "").upper() == "TAKE_PROFIT_MARKET"]
    print(f"  现有TP条件单: {[(a.get('algoId'), a.get('triggerPrice')) for a in mine]}")
    if not mine:
        print("  ⚠️ 无 TP 条件单 → 跳过(需要补挂)"); continue
    for a in mine:
        r = c.modify_tp_sl(a.get("algoId"), tp_r)
        print(f"  → 改 algoId={a.get('algoId')} {a.get('triggerPrice')} → {tp_r} : "
              f"{json.dumps(r, ensure_ascii=False)[:240]}")

print("\n--- 改完回读 ---")
seen = set()
for x in rows:
    sym = (x.get("symbol") or "").upper()
    inst = next((k for k, v in SYMBOL_MAP.items() if v[0].upper() == sym), None)
    if not inst or sym in seen:
        continue
    seen.add(sym)
    _st, algos = c.algo_orders(inst)
    for a in algos:
        print(f"  {sym} {a.get('positionSide')} {a.get('orderType')} "
              f"trigger={a.get('triggerPrice')} algoId={a.get('algoId')} status={a.get('algoStatus')}")
print("\n完成")
