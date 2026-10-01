# OKX模拟盘链路自检: 连通性 → 余额 → 设杠杆 → 测试下单 → 立即平仓
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient

c = OkxClient(simulated=True)
print("=== OKX 模拟盘链路自检 ===")
print("1) 公开接口连通:", c.ping_public())

try:
    bal = c.get_balance()
    if bal.get("code") == "0":
        d = bal["data"][0]
        print(f"2) 账户模式: {d.get('acctLv')} | 总权益: {d.get('totalEq')}")
        for det in d.get("details", [])[:3]:
            print(f"   {det.get('ccy')}: 可用 {det.get('availBal')} / 冻结 {det.get('frozenBal')}")
    else:
        print(f"2) 余额查询失败: {bal}")
except Exception as e:
    print(f"2) 余额异常: {e}")

print("3) 设置杠杆(100倍 逐仓):")
print("   ", c.set_leverage("BTC-USDT-SWAP", 100, "isolated", pos_side="long"))

print("4) 测试下单(买 0.01张 市价):")
r = c.place_order("BTC-USDT-SWAP", "buy", 0.01, td_mode="isolated", pos_side="long")
print("   ", json.dumps(r, ensure_ascii=False)[:300])

if r.get("code") == "0":
    print("5) 立即平仓:")
    r2 = c.close_position("BTC-USDT-SWAP", "sell", 0.01, td_mode="isolated", pos_side="long")
    print("   ", json.dumps(r2, ensure_ascii=False)[:300])
    print("✅ 下单+平仓链路正常")
else:
    print("❌ 下单失败 — 需排查(常见: 模拟盘未开通/无资金/权限不足)")
