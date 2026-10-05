# -*- coding: utf-8 -*-
"""③ 结构分层(高周期大swing定方向 / 低周期小swing做Internal) 对比回测 —— 90天离线"""
import sys
import os
import json

TOOLS = "/sandbox/workspace/trading_agent/tools"
sys.path.insert(0, TOOLS)
sys.path.insert(0, "/sandbox/workspace/trading_agent/engine")

import _fetch_cache  # noqa: E402
_orig = _fetch_cache.fetch_range


def fr(inst, tf, s, e, allow_fetch=True):
    return _orig(inst, tf, s, e, allow_fetch=False)


import backtest  # noqa: E402
backtest.fetch_range = fr
import config as C  # noqa: E402

d = json.load(open(os.path.join(TOOLS, "_cache_weex", "BTC-USDT-SWAP_15m.json")))
now = max(int(k) for k in d)

CASES = [
    ("1H=4 /15m=4 (旧)", 4, 4),
    ("1H=10/15m=4", 10, 4),
    ("1H=12/15m=4", 12, 4),
    ("1H=15/15m=4", 15, 4),
    ("1H=12/15m=2", 12, 2),
    ("1H=12/15m=5", 12, 5),
]
C.TP_MODE = "usd"
C.CHOCH_IS_WARNING_ONLY = True
C.INT_REQUIRE_CHOCH = True
C.INT_REQUIRE_BOS = True
C.INT_CONFIRM_MAX_AGE_BARS = 4
_lo = int(sys.argv[1]) if len(sys.argv) > 1 else 0
_hi = int(sys.argv[2]) if len(sys.argv) > 2 else len(CASES)
print(f"{'分层(1H/15m swing)':<20} {'笔数':>5} {'胜率%':>7} {'净盈亏U':>10} {'每笔U':>8} {'毛盈亏U':>9}", flush=True)
for label, sh, sl in CASES[_lo:_hi]:
    C.SWING_LEN_HTF = int(sh)
    C.SWING_LEN_LTF = int(sl)
    s = backtest.run_range(90, now)["stats"]
    print(f"{label:<20} {s['n']:>5} {s.get('win_rate'):>7} {s['net']:>10} {s['avg']:>8} {s.get('gross'):>9}", flush=True)
