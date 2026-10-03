# WEEX 第三轮探测: 按 V3 文档核对真实响应 (根数/limit/历史翻页/现货合约/黄金)
import requests

SPOT = "https://api-spot.weex.com"
CON = "https://api-contract.weex.com"
TESTS = [
    ("hist limit=100", CON, "/capi/v2/market/historyCandles?symbol=cmt_btcusdt&granularity=1h&limit=100"),
    ("hist limit=200", CON, "/capi/v2/market/historyCandles?symbol=cmt_btcusdt&granularity=1h&limit=200"),
    ("hist endTime翻页", CON, "/capi/v2/market/historyCandles?symbol=cmt_btcusdt&granularity=1h&limit=100&endTime=1758000000000"),
    ("hist 时间窗", CON, "/capi/v2/market/historyCandles?symbol=cmt_btcusdt&granularity=1h&limit=100&startTime=1757000000000&endTime=1758000000000"),
    ("hist 15m endTime", CON, "/capi/v2/market/historyCandles?symbol=cmt_btcusdt&granularity=15m&limit=200&endTime=1758000000000"),
    ("hist 黄金 endTime", CON, "/capi/v2/market/historyCandles?symbol=cmt_xautusdt&granularity=1h&limit=100&endTime=1758000000000"),
    ("hist 最老能到哪", CON, "/capi/v2/market/historyCandles?symbol=cmt_btcusdt&granularity=1d&limit=100"),
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
