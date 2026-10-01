# OKX 诊断 v2 (只读): 账户模式 + 真实持仓 + XAU最大杠杆 + 订单历史
import sys, os, json, requests
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient
c = OkxClient(simulated=True)

print("=== 1) 账户配置(acctLv/posMode) ===")
print(json.dumps(c._get("/api/v5/account/config", None), ensure_ascii=False)[:400])

print("=== 2) 真实持仓(全部) ===")
p = c.get_positions()
if p.get("code") == "0":
    print("   条数:", len(p.get("data", [])))
    for x in p["data"]:
        print("   ", x.get("instId"), x.get("posSide"), "pos=", x.get("pos"), "avgPx=", x.get("avgPx"),
              "lever=", x.get("lever"), "mgnMode=", x.get("mgnMode"), "upl=", x.get("upl"))
else:
    print("   err", json.dumps(p, ensure_ascii=False)[:300])

print("=== 3) 合约规格/最大杠杆 ===")
for inst in ["XAU-USDT-SWAP", "BTC-USDT-SWAP"]:
    ir = requests.get("https://www.okx.com/api/v5/public/instruments",
                      params={"instType": "SWAP", "instId": inst}, timeout=15).json()
    d = (ir.get("data") or [{}])[0]
    print(f"   {inst}: lever(max)={d.get('lever')} ctVal={d.get('ctVal')} minSz={d.get('minSz')} lotSz={d.get('lotSz')}")

print("=== 4) 最近订单历史 ===")
for inst in ["XAU-USDT-SWAP", "BTC-USDT-SWAP"]:
    oh = c._get("/api/v5/trade/orders-history", {"instType": "SWAP", "instId": inst, "limit": "10"})
    print(f"-- {inst} code={oh.get('code')} 条数={len(oh.get('data') or [])} --")
    for o in (oh.get("data") or []):
        import datetime
        t = datetime.datetime.fromtimestamp(int(o.get("cTime", 0)) / 1000).strftime("%H:%M:%S")
        print(f"   {t} side={o.get('side')} posSide={o.get('posSide')} sz={o.get('sz')} "
              f"fillSz={o.get('fillSz')} avgPx={o.get('avgPx')} state={o.get('state')} ordType={o.get('ordType')}")
