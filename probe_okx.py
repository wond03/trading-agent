# 诊断: XAU/BTC 的 K线收盘价 vs 最新成交价 (查是否"行情源与可成交价"背离)
import sys, os, json, requests
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)

print("=== 当前持仓 ===")
p = c.get_positions()
for x in (p.get("data") or []):
    print("   ", x.get("instId"), x.get("posSide"), "pos=", x.get("pos"), "avgPx=", x.get("avgPx"), "lever=", x.get("lever"))
if not (p.get("data") or []):
    print("   （无）")

print("=== K线收盘 vs 最新成交价 (同一合约) ===")
for inst in ["XAU-USDT-SWAP", "BTC-USDT-SWAP"]:
    k = c.get_candles(inst, "1H", 3)
    t = requests.get("https://www.okx.com/api/v5/market/ticker", params={"instId": inst}, timeout=15).json()
    last = t["data"][0]["last"] if t.get("code") == "0" else "?"
    gap = (float(last) - k[-1].close) / k[-1].close * 100 if last != "?" else None
    print(f"   {inst}: K线末收盘={k[-1].close:.2f}  最新价={last}  偏离={gap:+.2f}%" if gap is not None else f"   {inst}: K线末收盘={k[-1].close} 最新价={last}")
