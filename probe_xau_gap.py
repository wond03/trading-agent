# 诊断③: OKX「真实盘」vs「模拟盘」的行情对照 (XAU / BTC)
# 背景: 模拟盘这笔黄金成交在 4205.9, 但真实市场黄金约 4147 → 差 60 点。定位偏离来自哪一侧。
# 只在 GitHub Actions 上跑
import datetime
import requests

CST = datetime.timezone(datetime.timedelta(hours=8))
DEMO = {"x-simulated-trading": "1"}


def T(ts):
    v = float(ts)
    if v > 1_000_000_000_000:
        v /= 1000.0
    return datetime.datetime.fromtimestamp(v, CST).strftime("%m-%d %H:%M")


def tick(inst, demo=False):
    r = requests.get("https://www.okx.com/api/v5/market/ticker", params={"instId": inst},
                     headers=DEMO if demo else {}, timeout=30)
    d = (r.json().get("data") or [{}])[0]
    return d.get("last"), d.get("bidPx"), d.get("askPx"), d.get("ts"), r.status_code


def candles(inst, demo=False, bar="15m", limit="8"):
    r = requests.get("https://www.okx.com/api/v5/market/candles",
                     params={"instId": inst, "bar": bar, "limit": limit},
                     headers=DEMO if demo else {}, timeout=30)
    return r.json().get("data") or []


def weex(inst_w, tf="15m", limit="8"):
    r = requests.get("https://api-contract.weex.com/capi/v2/market/candles",
                     params={"symbol": inst_w, "granularity": tf, "limit": limit}, timeout=30)
    j = r.json()
    return j.get("data") if isinstance(j, dict) else j


print("=" * 74)
print("① 实时 ticker 对照")
for inst, w in (("XAU-USDT-SWAP", "cmt_xautusdt"), ("BTC-USDT-SWAP", "cmt_btcusdt")):
    a = tick(inst, demo=False)
    b = tick(inst, demo=True)
    print(f"  {inst}")
    print(f"    真实盘  last={a[0]} bid/ask={a[1]}/{a[2]}  时间={T(a[3]) if a[3] else '-'} (http {a[4]})")
    print(f"    模拟盘  last={b[0]} bid/ask={b[1]}/{b[2]}  时间={T(b[3]) if b[3] else '-'} (http {b[4]})")
    try:
        wa = w
        wr = weex(inst_w=wa)
        if wr:
            print(f"    WEEX    last={wr[0][4]} (15m收盘 时间={T(wr[0][0])})")
    except Exception as e:
        print("    WEEX 读取失败", e)

print("=" * 74)
print("② 最近 8 根 15m 收盘 对照 (真实盘 / 模拟盘 / WEEX)")
for inst, w in (("XAU-USDT-SWAP", "cmt_xautusdt"), ("BTC-USDT-SWAP", "cmt_btcusdt")):
    lv = {int(x[0]): float(x[4]) for x in candles(inst, False)}
    dm = {int(x[0]): float(x[4]) for x in candles(inst, True)}
    wx = {}
    try:
        for row in (weex(inst_w=w) or []):
            wx[int(row[0])] = float(row[4])
    except Exception:
        pass
    print(f"  --- {inst} ---")
    print(f"    {'时间':>12} {'真实盘':>10} {'模拟盘':>10} {'WEEX':>10} {'模拟-真实':>10}")
    for k in sorted(set(lv) | set(dm) | set(wx))[-6:]:
        d = f"{dm[k]-lv[k]:+.1f}" if (k in dm and k in lv) else "-"
        print(f"    {T(k):>12} {lv.get(k, '-'):>10} {dm.get(k, '-'):>10} {wx.get(k, '-'):>10} {d:>10}")
print("=" * 74)
print("完成")
