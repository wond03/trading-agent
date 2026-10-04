# 拉全: WEEX 持仓 + 条件单(止盈止损) + 最近委托 —— 判定 tp/sl 挂没挂、挂在哪
import json
import sys
import time
import urllib.parse

import requests

sys.path.insert(0, "engine")
from weex_trade import WeexTrade, BASE  # noqa: E402

c = WeexTrade()
c.sync_time()


def raw_get(path, params=None):
    query = urllib.parse.urlencode(params) if params else ""
    url = BASE + path + (("?" + query) if query else "")
    ts = int(time.time() * 1000) + c._t_off
    h = c._headers(ts, "GET", path, query, "")
    try:
        r = requests.get(url, headers=h, timeout=20)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text[:500]
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def show(title, obj):
    print(f"\n========== {title} ==========")
    print(json.dumps(obj, ensure_ascii=False, indent=1))


# 1) 持仓
st, j = raw_get("/capi/v3/sim/position/allPosition")
show(f"持仓 (http {st})", j)

# 2) 条件单 (止盈止损) —— 全量
st, j = raw_get("/capi/v3/openAlgoOrders", {"page": 1, "limit": 100})
show(f"条件单 openAlgoOrders (http {st})", j)

# 3) 最近委托
st, j = c.get_order_history(limit=12)
show(f"最近委托 (http {st})", j)

print("\n完成")
