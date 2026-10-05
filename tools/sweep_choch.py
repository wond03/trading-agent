# -*- coding: utf-8 -*-
"""对比: ② CHoCH 语义(旧:即时翻趋势 / 新:只预警等反向BOS确认) —— 90天离线回测"""
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
    ("旧口径+确认门k4", 0, 1, 1, 4),
    ("新口径+确认门k4", 1, 1, 1, 4),
    ("新口径+无确认门", 1, 0, 0, 4),
]
C.TP_MODE = "usd"
print(f"{'方案':<18} {'笔数':>5} {'胜率%':>7} {'净盈亏U':>10} {'每笔U':>8} {'毛盈亏U':>9}")
for label, warn_only, req_ch, req_bo, k in CASES:
    C.CHOCH_IS_WARNING_ONLY = bool(warn_only)
    C.INT_REQUIRE_CHOCH = bool(req_ch)
    C.INT_REQUIRE_BOS = bool(req_bo)
    C.INT_CONFIRM_MAX_AGE_BARS = int(k)
    s = backtest.run_range(90, now)["stats"]
    print(f"{label:<18} {s['n']:>5} {s.get('win_rate'):>7} {s['net']:>10} {s['avg']:>8} {s.get('gross'):>9}", flush=True)
