# WEEX 第三轮探测: 按 V3 文档核对真实响应 (根数/limit/历史翻页/现货合约/黄金)
import requests

SPOT = "https://api-spot.weex.com"
CON = "https://api-contract.weex.com"
TESTS = [
    ("candles limit=10", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=10"),
    ("candles limit=50", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=50"),
    ("candles limit=100", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=100"),
    ("candles limit=200", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=200"),
    ("candles limit=1000", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=1000"),
    ("candles 时间窗", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=200"
                            "&startTime=1755000000000&endTime=1759000000000"),
    ("candles endTime翻页", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1h&limit=200"
                              "&endTime=1758000000000"),
    ("history/candles", CON, "/capi/v2/market/history/candles?symbol=cmt_btcusdt&granularity=1h&limit=200"),
    ("历史K线 v2", CON, "/capi/v2/market/historyCandles?symbol=cmt_btcusdt&granularity=1h&limit=200"),
    ("granularity=1m", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1m&limit=5"),
    ("granularity=30m", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=30m&limit=5"),
    ("granularity=1d", CON, "/capi/v2/market/candles?symbol=cmt_btcusdt&granularity=1d&limit=5"),
    ("现货 history limit=100", SPOT, "/api/v3/market/historyKlines?symbol=BTCUSDT&interval=1h&limit=100"),
    ("现货 history limit=10", SPOT, "/api/v3/market/historyKlines?symbol=BTCUSDT&interval=1h&limit=10"),
    ("合约 交易对信息", CON, "/capi/v2/market/contracts"),
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
