# 诊断⑧: 黄金模拟盘"盘口"到底能不能成交(买单/卖单有没有对手盘)
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

for INST in ("XAU-USDT-SWAP", "BTC-USDT-SWAP"):
    print("=" * 70)
    print("###", INST)
    try:
        t = (c._get("/api/v5/market/ticker", {"instId": INST}).get("data") or [{}])[0]
        for k in ("last", "lastSz", "askPx", "askSz", "bidPx", "bidSz", "open24h", "vol24h"):
            print(f"   {k} = {t.get(k)}")
    except Exception as e:
        print("   ticker失败", e)
    try:
        b = (c._get("/api/v5/market/books", {"instId": INST, "sz": 5}).get("data") or [{}])[0]
        print("   卖盘(ask):", b.get("asks"))
        print("   买盘(bid):", b.get("bids"))
    except Exception as e:
        print("   books失败", e)
    # 对照: 真实盘(公开接口不需要签名, 不加 x-simulated-trading 头 = 真实盘)
    try:
        import requests
        rt = (requests.get("https://www.okx.com/api/v5/market/ticker",
                           params={"instId": INST}, timeout=30).json().get("data") or [{}])[0]
        print(f"   [真实盘对照] last={rt.get('last')} bid={rt.get('bidPx')} ask={rt.get('askPx')}")
    except Exception as e:
        print("   真实盘查询失败", e)
print("完成")
