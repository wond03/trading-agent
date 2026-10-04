# 一次性诊断⑥: 取交易所"实际保证金率"(position-tiers / instruments) 对照线仓实测
#   目的: 决定 size_fixed_margin 用哪个数据源换算"每张占用保证金"
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

for INST in ("XAU-USDT-SWAP", "BTC-USDT-SWAP"):
    print("#" * 78)
    print(f"### {INST}")
    print("#" * 78)

    print("① 合约规格 /public/instruments")
    try:
        j = c._get("/api/v5/public/instruments", {"instType": "SWAP", "instId": INST})
        d = (j.get("data") or [{}])[0]
        for k in ("ctVal", "ctValCcy", "lotSz", "minSz", "tickSz", "lever", "ctMult"):
            print(f"   {k} = {d.get(k)}")
        spec = {"ctVal": float(d.get("ctVal") or 0), "lotSz": float(d.get("lotSz") or 0),
                "minSz": float(d.get("minSz") or 0)}
    except Exception as e:
        print("   失败", type(e).__name__, e)
        spec = {}

    print("② 梯度保证金 /public/position-tiers (isolated)")
    tiers = []
    try:
        j = c._get("/api/v5/public/position-tiers",
                   {"instType": "SWAP", "tdMode": "isolated", "instId": INST})
        tiers = j.get("data") or []
        print(f"   共 {len(tiers)} 档; 前 3 档:")
        for t in tiers[:3]:
            print(f"   maxSz={t.get('maxSz'):<12} minSz={t.get('minSz'):<8} "
                  f"imr={t.get('imr'):<8} mmr={t.get('mmr'):<8} "
                  f"maxLever={t.get('maxLever')} lever={t.get('lever')}")
    except Exception as e:
        print("   失败", type(e).__name__, e)

    print("③ 实测持仓(反推每张实际占用保证金)")
    try:
        j = c._get("/api/v5/account/positions", {"instId": INST})
        rows = [x for x in (j.get("data") or []) if float(x.get("pos") or 0) != 0]
        if not rows:
            print("   无持仓")
        for x in rows:
            pos = abs(float(x.get("pos")))
            mgn = float(x.get("margin") or 0)
            px = float(x.get("avgPx") or x.get("markPx") or 0)
            print(f"   pos={x.get('pos')} avgPx={px} margin={mgn} lever设置={x.get('lever')}")
            if pos:
                per = mgn / pos
                print(f"   >> 每张实际占用 = {per:.6f} U/张  "
                      f"(换算成有效倍率 = {(spec.get('ctVal', 0) * px) / per:.2f} 倍)")
                print(f"   >> 若目标 5U, 则张数 = {5.0 / per:.3f} 张")
    except Exception as e:
        print("   失败", type(e).__name__, e)

    if tiers and spec.get("ctVal"):
        t0 = tiers[0]
        try:
            imr = float(t0.get("imr") or 0)
        except Exception:
            imr = 0
        print(f"④ 用第1档 imr 换算(需 price): 每张 = imr × ctVal × price = "
              f"{imr} × {spec.get('ctVal')} × price")
print("完成")
