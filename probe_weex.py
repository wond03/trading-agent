# WEEX 公开行情接口探测 (在 GitHub Actions 上跑; 沙盒无法访问 weex)
import requests

HOSTS = ["https://api-spot.weex.com", "https://api.weex.com", "https://api-contract.weex.com"]
PATHS = [
    "/",
    "/api/v2/market/tickers",
    "/api/v2/market/ticker?symbol=BTCUSDT",
    "/api/v2/market/candles?symbol=BTCUSDT&period=1h&limit=3",
    "/api/v2/market/klines?symbol=BTCUSDT&period=1h&limit=3",
    "/api/v2/market/symbols",
    "/api/v2/market/depth?symbol=BTCUSDT&limit=5",
    "/api/v2/public/time",
    "/capi/v2/market/candles?symbol=BTCUSDT&granularity=1h&limit=3",
    "/api/v1/market/candles?symbol=BTCUSDT&period=1h&limit=3",
]
for h in HOSTS:
    for p in PATHS:
        try:
            r = requests.get(h + p, timeout=15)
            body = r.text.replace("\n", " ")[:300]
            print(f"[{r.status_code}] {h}{p}\n    {body}", flush=True)
        except Exception as e:
            print(f"[ERR] {h}{p} :: {type(e).__name__} {str(e)[:120]}", flush=True)
