# -*- coding: utf-8 -*-
"""复盘器: 用【引擎自己的代码】逐根 15m 回放, 统计信号 + 打印"卡在哪一步"。
   用法: python tools/diag_why.py [品种] [最近N根] [K=V ...]   (K=V 会 setattr 到 config, 再回放)
   例:   python tools/diag_why.py XAU-USDT-SWAP 96 SWING_LEN_HTF=4
"""
import sys
import os
import json
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))

import config as C  # noqa: E402
from structure import StructureEngine, Candle  # noqa: E402
from liquidity import LiquidityEngine  # noqa: E402
from entry import EntryEngine  # noqa: E402
from main import why_no_signal  # noqa: E402

args = sys.argv[1:]
INST = args[0] if len(args) > 0 else "XAU-USDT-SWAP"
N = int(args[1]) if len(args) > 1 else 96
for kv in args[2:]:
    if "=" in kv:
        k, v = kv.split("=", 1)
        try:
            v = int(v)
        except ValueError:
            try:
                v = float(v)
            except ValueError:
                v = {"True": True, "False": False}.get(v, v.strip('"'))
        setattr(C, k, v)
        print(f"[override] {k} = {getattr(C, k)}")

CST = datetime.timezone(datetime.timedelta(hours=8))
d = json.load(open(os.path.join(HERE, "_cache_weex", f"{INST}_15m.json")))
keys = sorted(int(k) for k in d)


def cd(i, n):
    ks = keys[max(0, i - n + 1): i + 1]
    return [Candle(k, d[str(k)][0], d[str(k)][1], d[str(k)][2], d[str(k)][3], d[str(k)][4]) for k in ks]


def T(ts):
    return datetime.datetime.fromtimestamp(ts, CST).strftime("%m-%d %H:%M")


sigs = []
gates = {}
for i in range(max(0, len(keys) - N), len(keys)):
    c300 = cd(i, 300)
    if len(c300) < 120:
        continue
    se = StructureEngine(C.SWING_LEN_HTF); se.process(c300)
    le = LiquidityEngine(); le.process(c300)
    c200 = cd(i, 200)
    lse = StructureEngine(C.SWING_LEN_LTF); lse.process(c200); lse.last_idx = len(c200) - 1
    lle = LiquidityEngine(); lle.process(c200)
    hse = StructureEngine(C.SWING_LEN_HTF); hse.process(c200); htf = hse.trend
    ee = EntryEngine()
    sig = ee.evaluate(c300, se, le, htf, bar_i=len(c300) - 1,
                      ltf_se=lse, ltf_le=lle, ltf_candles=c200)
    if sig:
        sigs.append((T(keys[i]), c300[-1].close, sig.direction, sig.entry, sig.sl, sig.tp))
    else:
        g = why_no_signal(ee).split(" ")[0]
        gates[g] = gates.get(g, 0) + 1

print(f"\n[{INST}] 最近 {min(N, len(keys))} 根 15m | SWING_LEN_HTF={C.SWING_LEN_HTF} "
      f"k={C.INT_CONFIRM_MAX_AGE_BARS} RETRACE={C.RETRACE_MAX_AGE_BARS} "
      f"REQ_BOS={C.INT_REQUIRE_BOS} REQ_CHOCH={C.INT_REQUIRE_CHOCH} WARN_ONLY={C.CHOCH_IS_WARNING_ONLY}")
print("  信号数:", len(sigs), " | 卡点分布:", gates)
for s in sigs:
    print(f"   ★ {s[0]} 收{s[1]:.1f} {s[2].upper()} 进{s[3]:.1f} 损{s[4]:.1f} 标{s[5]:.1f}")
