# 一次性诊断: 同一时刻 OKX XAU-USDT-SWAP 与 WEEX cmt_xautusdt 的价格差
# 背景: 10-03 04:51 信号价(WEEX 15m close)≈4145, 但 OKX 成交价 4205.9, 差约 60 点。
# 目的: 确认这是"跨交易所价差"还是"成交价记录异常"。
# 只在 GitHub Actions 上跑(沙盒连不上 OKX/WEEX)
import datetime
import requests

CST = datetime.timezone(datetime.timedelta(hours=8))
OKX = "https://www.okx.com/api/v5/market"
WEEX = "https://api-contract.weex.com/capi/v2/market"


def T(ts):
    v = float(ts)
    if v > 1_000_000_000_000:
        v /= 1000.0
    return datetime.datetime.fromtimestamp(v, CST).strftime("%m-%d %H:%M")


def okx(path, **params):
    r = requests.get(f"{OKX}/{path}", params=params, timeout=30)
    return r.status_code, r.json()


def weex(path, **params):
    r = requests.get(f"{WEEX}/{path}", params=params, timeout=30)
    return r.status_code, r.json()


print("=" * 72)
print("① OKX 实时行情")
code, j = okx("ticker", instId="XAU-USDT-SWAP")
if code == 200 and j.get("data"):
    d = j["data"][0]
    print(f"  OKX XAU-USDT-SWAP 最新价 {d.get('last')}  (bid {d.get('bidPx')} / ask {d.get('askPx')})")
else:
    print("  ticker 失败", code, str(j)[:200])

code, j = okx("candles", instId="XAU-USDT-SWAP", bar="15m", limit="100")
o15 = {}
if code == 200:
    for row in j.get("data", []):
        o15[int(row[0])] = [float(x) for x in row[1:5]]
    print(f"  OKX 15m K线 {len(o15)} 根, 最新 {T(max(o15))}")
else:
    print("  candles 失败", code, str(j)[:200])

code, j = weex("candles", symbol="cmt_xautusdt", granularity="15m", limit="100")
w15 = {}
if code == 200:
    rows = j.get("data") if isinstance(j, dict) else j
    for row in rows:
        w15[int(row[0])] = [float(x) for x in row[1:5]]
    print(f"  WEEX 15m K线 {len(w15)} 根, 最新 {T(max(w15))}")
else:
    print("  weex 失败", code, str(j)[:200])

print("=" * 72)
print("② 逐根对照(收盘价, 最近的 12 根)")
print(f"  {'时间(CST)':>13} {'OKX收盘':>11} {'WEEX收盘':>11} {'差(OKX-WEEX)':>13}")
for k in sorted(set(o15) | set(w15))[-12:]:
    a = o15.get(k, [None] * 4)[3]
    b = w15.get(k, [None] * 4)[3]
    diff = f"{a - b:+.1f}" if (a and b) else "-"
    print(f"  {T(k):>13} {a if a else '-':>11} {b if b else '-':>11} {diff:>13}")

print("=" * 72)
print("③ 关键窗口 10-03 04:30~05:15 CST (开仓那根)")
want = ["10-03 04:30", "10-03 04:45", "10-03 05:00", "10-03 05:15"]
for k in sorted(set(o15) | set(w15)):
    if T(k) in want:
        a = o15.get(k)
        b = w15.get(k)
        print(f"  {T(k)}  OKX {a}  WEEX {b}  差 {a[3]-b[3]:+.1f}" if (a and b) else f"  {T(k)} OKX={a} WEEX={b}")
print("=" * 72)
print("完成")
