# 一次性诊断②: 直接读 OKX 这笔黄金空单的真实数据
#   ① 持仓: avgPx(真实开仓均价) / liqPx(交易所爆仓价) / lever / upl
#   ② 成交明细: XAU 最近的成交流水(时间/价格/方向) → 定位到底什么时间、什么价成交的
# 只在 GitHub Actions 上跑(需要 OKX 密钥, 沙盒连不上 OKX)
import os
import sys
import json
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

CST = datetime.timezone(datetime.timedelta(hours=8))


def T(ts):
    v = float(ts)
    if v > 1_000_000_000_000:
        v /= 1000.0
    return datetime.datetime.fromtimestamp(v, CST).strftime("%m-%d %H:%M:%S")


c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

print("=" * 72)
print("① OKX 持仓 (XAU-USDT-SWAP)")
try:
    r = c.get_positions(inst_id="XAU-USDT-SWAP")
    rows = [x for x in (r.get("data") or []) if float(x.get("pos") or 0) != 0]
    if not rows:
        print("  无持仓", json.dumps(r, ensure_ascii=False)[:300])
    for x in rows:
        print(f"  方向={x.get('posSide')} 张数={x.get('pos')} 开仓均价(avgPx)={x.get('avgPx')} "
              f"爆仓价(liqPx)={x.get('liqPx')} 杠杆={x.get('lever')} 模式={x.get('mgnMode')}")
        print(f"  标记价(markPx)={x.get('markPx')} 最新价(last)={x.get('last')} "
              f"未实现盈亏(upl)={x.get('upl')} 保证金={x.get('margin')} 时间={T(x.get('uTime') or 0)}")
except Exception as e:
    print("  读取失败", type(e).__name__, e)

print("=" * 72)
print("② OKX 标的行情")
try:
    t = c.get_tick("XAU-USDT-SWAP").get("data") or [{}]
    print("  XAU-USDT-SWAP ticker:", json.dumps(t[0], ensure_ascii=False)[:260])
except Exception as e:
    print("  ticker 失败", e)

print("=" * 72)
print("③ 最近成交流水 (XAU-USDT-SWAP)")
try:
    r = c.get_fills(inst_type="SWAP", inst_id="XAU-USDT-SWAP", limit=20)
    for x in (r.get("data") or []):
        print(f"  {T(x.get('ts'))}  {x.get('side')}  价={x.get('fillPx')}  张={x.get('fillSz')}  "
              f"单号={x.get('ordId')} 类型={x.get('ordType')} 备注={x.get('tag') or '-'}")
except Exception as e:
    print("  流水失败", type(e).__name__, e)
print("=" * 72)
print("完成")
