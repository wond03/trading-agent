# -*- coding: utf-8 -*-
"""Internal 结构确认门 对比回测(90天, 离线WEEX缓存, 与线上同参数: 止盈=浮盈10U)"""
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
    ("无确认(现状)", 0, 0, 8),
    ("仅CHoCH", 1, 0, 8),
    ("仅BOS", 0, 1, 8),
    ("CHoCH+BOS k=4", 1, 1, 4),
    ("CHoCH+BOS k=8", 1, 1, 8),
    ("CHoCH+BOS k=16", 1, 1, 16),
    ("CHoCH+BOS k=999", 1, 1, 999),
]
print(f"{'方案':<16} {'笔数':>5} {'胜率%':>7} {'净盈亏U':>10} {'每笔U':>8} {'毛盈亏U':>9}")
C.TP_MODE = "usd"
_lo = int(sys.argv[1]) if len(sys.argv) > 1 else 0
_hi = int(sys.argv[2]) if len(sys.argv) > 2 else len(CASES)
for label, req_ch, req_bo, k in CASES[_lo:_hi]:
    C.INT_REQUIRE_CHOCH = bool(req_ch)
    C.INT_REQUIRE_BOS = bool(req_bo)
    C.INT_CONFIRM_MAX_AGE_BARS = int(k)
    s = backtest.run_range(90, now)["stats"]
    print(f"{label:<16} {s['n']:>5} {s.get('win_rate'):>7} {s['net']:>10} {s['avg']:>8} {s.get('gross'):>9}")
