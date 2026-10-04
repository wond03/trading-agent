# 一次性诊断⑦: 原样打印 position-tiers 各种查询条件, 确认模拟盘是否支持
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

QUERIES = [
    ("全品种 isolated", {"instType": "SWAP", "tdMode": "isolated"}),
    ("单独 XAU isolated", {"instType": "SWAP", "tdMode": "isolated", "instId": "XAU-USDT-SWAP"}),
    ("单独 XAU cross", {"instType": "SWAP", "tdMode": "cross", "instId": "XAU-USDT-SWAP"}),
    ("全品种 cross", {"instType": "SWAP", "tdMode": "cross"}),
    ("全品种 no tdMode", {"instType": "SWAP"}),
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
