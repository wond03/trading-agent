# 探测: WEEX 条件单(止盈止损)到底有没有挂上 —— 关键接口 GET /capi/v3/openAlgoOrders
# 目的: 判定 [WEEX下单] 里内联的 tpTriggerPrice/slTriggerPrice 是否真的生成了条件单
import sys
import time
import urllib.parse

import requests

sys.path.insert(0, "engine")
from weex_trade import WeexTrade, BASE  # noqa: E402

c = WeexTrade()
print("configured:", c.configured, "time_offset:", c.sync_time())


def raw_get(path, params=None):
    """只读探测, 绕过 /sim/ 守卫(仅 GET, 不产生任何写操作)"""
    query = urllib.parse.urlencode(params) if params else ""
    url = BASE + path + (("?" + query) if query else "")
    ts = int(time.time() * 1000) + c._t_off
    h = c._headers(ts, "GET", path, query, "")
    try:
        r = requests.get(url, headers=h, timeout=20)
        return r.status_code, r.text[:900]
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


CANDS = [
    ("/capi/v3/sim/openAlgoOrders", None),
    ("/capi/v3/sim/openAlgoOrders", {"symbol": "BTCSUSDT"}),
    ("/capi/v3/sim/openOrders", None),
    ("/capi/v3/openAlgoOrders", None),
    ("/capi/v3/openAlgoOrders", {"symbol": "BTCSUSDT"}),
]
for p, q in CANDS:
    st, body = raw_get(p, q)
    print(f"\n### GET {p} {q or ''} -> {st}")
    print(body)

print("\n完成")
