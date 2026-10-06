# -*- coding: utf-8 -*-
"""诊断: 用户手画的 BOS/CHoCH 为什么引擎认不出来 —— 逐档 swing_length 看结构事件。
用法: python tools/diag_struct_marks.py [品种] [起始"MM-DD HH:MM"] [结束] [swing...]
"""
import sys, os, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import config as C
from structure import StructureEngine, Candle

CST = datetime.timezone(datetime.timedelta(hours=8))
INST = sys.argv[1] if len(sys.argv) > 1 else "XAU-USDT-SWAP"
d = json.load(open(os.path.join(HERE, "_cache_weex", f"{INST}_15m.json")))
keys = sorted(int(k) for k in d)


def T(ts):
    return datetime.datetime.fromtimestamp(ts, CST).strftime("%m-%d %H:%M")


def tp(s):
    return datetime.datetime.strptime("2026-" + s, "%Y-%m-%d %H:%M").replace(tzinfo=CST).timestamp()


lo, hi = tp(sys.argv[2]), tp(sys.argv[3])
sws = [int(x) for x in sys.argv[4:]] or [1, 2, 3, 4, 5, 8, 10]
s = [j for j, k in enumerate(keys) if k >= lo - 300 * 900][0]
c = [Candle(keys[j], *d[str(keys[j])][:5]) for j in range(s, len(keys))]
print(f"{INST} 窗口 {T(lo)} → {T(hi)}  (共 {len(c)} 根喂入, 含预热)")
for sw in sws:
    se = StructureEngine(sw); se.process(c)
    ev = [(T(c[i].ts), t, p) for i, t, p in se.events if lo <= c[i].ts <= hi]
    print(f"\n  ── swing_length = {sw} ── 事件 {len(ev)} 个")
    for t, k, p in ev:
        print(f"     {t}  {k:<11} {p:.1f}")
