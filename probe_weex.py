# WEEX 第二轮探测: symbol 格式 / 合约接口 / 黄金标的
import requests

SPOT = "https://api-spot.weex.com"
CON = "https://api-contract.weex.com"
TESTS = [
    # 现货 K线: symbol 各种写法
    (SPOT, "/api/v2/market/candles?symbol=btcusdt&period=1h&limit=3"),
    (SPOT, "/api/v2/market/candles?symbol=BTC-USDT&period=1h&limit=3"),
    (SPOT, "/api/v2/market/candles?symbol=BTC_USDT&period=1h&limit=3"),
    (SPOT, "/api/v2/market/candles?symbol=BTCUSDT_SPBL&period=1h&limit=3"),
    (SPOT, "/api/v2/market/candles?symbol=cmt_btcusdt&period=1h&limit=3"),
    (SPOT, "/api/v2/market/candles?symbol=BTCUSDT&interval=1h&limit=3"),
    # 现货 标的清单 / 行情
    (SPOT, "/api/v2/market/tickers"),
    (SPOT, "/api/v2/market/coins"),
    (SPOT, "/api/v2/market/symbol/list"),
    (SPOT, "/api/v2/public/symbols"),
    # 合约
    (CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=3"),
    (CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1H&limit=3"),
    (CON, "/capi/v2/market/candles?symbol=BTCUSDT&granularity=1H&limit=3"),
    (CON, "/capi/v2/market/tickers"),
    (CON, "/capi/v2/market/contracts"),
    # 黄金候选
    (CON, "/capi/v2/market/candles?symbol=cmt_xautusdt&granularity=1h&limit=3"),
    (SPOT, "/api/v2/market/candles?symbol=PAXGUSDT&period=1h&limit=3"),
    (SPOT, "/api/v2/market/candles?symbol=XAUTUSDT&period=1h&limit=3"),
]
for host, p in TESTS:
    try:
        r = requests.get(host + p, timeout=15)
        print(f"[{r.status_code}] {host}{p}\n    {r.text.replace(chr(10),' ')[:300]}", flush=True)
    except Exception as e:
        print(f"[ERR] {host}{p} :: {type(e).__name__} {str(e)[:100]}", flush=True)
