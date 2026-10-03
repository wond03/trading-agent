# 一次性诊断④: 查清 OKX 这笔黄金单的「保证金/杠杆/合约规格/全部成交流水」
#   ① 账户对该合约的杠杆设置(是不是 50 倍)
#   ② 合约规格 ctVal/lotSz/minSz (换算名义价值)
#   ③ 持仓明细 margin/imr/mmr/notionalUsd/liqPx/lever  → 核对 6.31U 怎么来的
#   ④ 全部成交流水 → 证明有没有加仓(同一仓位被多次同向成交)
# 只在 GitHub Actions 上跑
import os
import sys
import json
import datetime
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

CST = datetime.timezone(datetime.timedelta(hours=8))


def T(ts):
    v = float(ts or 0)
    if v > 1_000_000_000_000:
        v /= 1000.0
    return datetime.datetime.fromtimestamp(v, CST).strftime("%m-%d %H:%M:%S")


INST = "XAU-USDT-SWAP"
c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

print("=" * 76)
print("① 账户杠杆设置 (isolated)")
try:
    j = c._get("/api/v5/account/leverage-info", {"instId": INST, "mgnMode": "isolated"})
    print("  ", json.dumps(j, ensure_ascii=False)[:400])
except Exception as e:
    print("  失败", type(e).__name__, e)

print("=" * 76)
print("② 合约规格 (公开)")
try:
    d = requests.get("https://www.okx.com/api/v5/public/instruments",
                     params={"instType": "SWAP", "instId": INST}, timeout=30).json()["data"][0]
    for k in ("instId", "ctVal", "ctValCcy", "ctMult", "lotSz", "minSz", "tickSz", "lever", "maxLmtSz"):
        print(f"   {k} = {d.get(k)}")
except Exception as e:
    print("  失败", type(e).__name__, e)

print("=" * 76)
print("③ 持仓明细 (保证金/名义/爆仓价)")
try:
    j = c._get("/api/v5/account/positions", {"instId": INST})
    for x in (j.get("data") or []):
        if float(x.get("pos") or 0) == 0:
            continue
        for k in ("posSide", "pos", "avgPx", "lever", "mgnMode", "margin", "imr", "mmr",
                  "notionalUsd", "liqPx", "markPx", "upl", "uplRatio", "cTime", "uTime", "posId"):
            print(f"   {k} = {x.get(k)}")
        print(f"   --- 换算: 张数×ctVal×均价 = {float(x.get('pos'))}×ctVal×{x.get('avgPx')}")
except Exception as e:
    print("  失败", type(e).__name__, e)

print("=" * 76)
print("④ 全部成交流水 (最近 100 笔)")
try:
    j = c._get("/api/v5/trade/fills-history", {"instType": "SWAP", "instId": INST, "limit": "100"})
    rows = j.get("data") or []
    print(f"   共 {len(rows)} 笔")
    for x in rows:
        print(f"   {T(x.get('ts'))}  {x.get('side'):<5} 价={x.get('fillPx'):<9} 张={x.get('fillSz'):<5} "
              f"盈亏={x.get('fillPnl') or '-':<9} 单号={x.get('ordId')} posSide={x.get('posSide')}")
except Exception as e:
    print("  失败", type(e).__name__, e)
print("=" * 76)
print("完成")
