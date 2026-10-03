# WEEX 第三轮探测: 按 V3 文档核对真实响应 (根数/limit/历史翻页/现货合约/黄金)
import requests

SPOT = "https://api-spot.weex.com"
CON = "https://api-contract.weex.com"
TESTS = [
    ("现货 klines 文档写法", SPOT, "/api/v3/market/klines?symbol=BTCUSDT&interval=1h"),
    ("现货 klines +limit", SPOT, "/api/v3/market/klines?symbol=BTCUSDT&interval=1h&limit=300"),
    ("现货 klines _SPBL 后缀", SPOT, "/api/v3/market/klines?symbol=BTCUSDT_SPBL&interval=1h&limit=5"),
    ("现货 history 翻页", SPOT, "/api/v3/market/historyKlines?symbol=BTCUSDT&interval=1h&limit=100"),
    ("现货 history 带时间窗", SPOT, "/api/v3/market/historyKlines?symbol=BTCUSDT&interval=4h&limit=100"
                                 "&startTime=1756000000000&endTime=1759000000000"),
    ("现货 24hr", SPOT, "/api/v3/market/ticker/24hr?symbol=BTCUSDT"),
    ("现货 15m klines", SPOT, "/api/v3/market/klines?symbol=BTCUSDT&interval=15m&limit=10"),
    ("现货黄金 XAUT", SPOT, "/api/v3/market/klines?symbol=XAUTUSDT&interval=1h&limit=3"),
    ("现货黄金 PAXG", SPOT, "/api/v3/market/klines?symbol=PAXGUSDT&interval=1h&limit=3"),
    ("合约 candles(v2)", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=300"),
    ("合约 klines(v3)", CON, "/capi/v3/market/klines?symbol=cmt_btcusdt&interval=1h&limit=5"),
    ("合约 candles 15m", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=15m&limit=5"),
    ("合约 candles 4h", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=4h&limit=5"),
    ("合约 黄金 XAUT", CON, "/capi/v2/market/candles?symbol=cmt_xautusdt&granularity=1h&limit=3"),
    ("合约 tickers", CON, "/capi/v2/market/tickers"),
]
for name, host, p in TESTS:
    try:
        r = requests.get(host + p, timeout=20)
        t = r.text
        try:
            j = r.json()
        except Exception:
            j = None
        info = ""
        if isinstance(j, list) and j and isinstance(j[0], list):
            info = f"  → {len(j)} 根; 首={j[0][:6]}; 末={j[-1][:6]}"
        elif isinstance(j, list):
            info = f"  → {len(j)} 条; 首={str(j[0])[:120]}"
        print(f"[{r.status_code}] {name}: {host}{p}\n     {t[:180].replace(chr(10),' ')}{info}", flush=True)
    except Exception as e:
        print(f"[ERR] {name}: {type(e).__name__} {str(e)[:110]}", flush=True)
