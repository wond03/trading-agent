# 一次性诊断⑦: 原样打印 position-tiers 各种查询条件, 确认模拟盘是否支持
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

QUERIES = [
    ("XAU-USDT isolated", {"instType": "SWAP", "tdMode": "isolated", "instFamily": "XAU-USDT"}),
    ("XAU-USDT cross", {"instType": "SWAP", "tdMode": "cross", "instFamily": "XAU-USDT"}),
    ("BTC-USDT isolated", {"instType": "SWAP", "tdMode": "isolated", "instFamily": "BTC-USDT"}),
    ("BTX uly 写法", {"instType": "SWAP", "tdMode": "isolated", "uly": "XAU-USDT"}),
]
for name, params in QUERIES:
    print("=" * 70)
    print("Q:", name, params)
    try:
        j = c._get("/api/v5/public/position-tiers", params)
        d = j.get("data") or []
        print(f"  code={j.get('code')} msg={j.get('msg')} 档数={len(d)}")
        for t in d[:6]:
            if t.get("instId", "").startswith(("XAU", "BTC")):
                print("   ", json.dumps(t, ensure_ascii=False))
    except Exception as e:
        print("  异常", type(e).__name__, e)
print("完成")
