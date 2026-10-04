# 探测: WEEX 模拟盘【真实持仓全字段】+ 订单历史 + 余额
# 目的: 核对 (1) 逐仓/全仓 marginMode (2) 引擎仓 vs 手动仓 (3) 实际止盈止损触发价
import json
import sys

sys.path.insert(0, "engine")
from weex_trade import WeexTrade  # noqa: E402

c = WeexTrade()
print("configured:", c.configured)
print("time_offset_ms:", c.sync_time())

# 余额
st, j = c.get_balance()
print("\n### /sim/balance http", st)
print(json.dumps(j, ensure_ascii=False, indent=2)[:1500])

# 全持仓 (raw, 全字段)
st, j = c.get_positions_raw()
print("\n### /sim/position/allPosition http", st)
rows = j if isinstance(j, list) else (j.get("data") or [])
print("持仓数:", len(rows))
for x in rows:
    print("  ", json.dumps(x, ensure_ascii=False))

# 订单历史
st, j = c.get_order_history(limit=30)
print("\n### /sim/order/history http", st)
rows = j if isinstance(j, list) else (j.get("data") or [])
print("委托数:", len(rows))
for x in rows[:30]:
    print("  ", json.dumps(x, ensure_ascii=False))

print("\n完成")
