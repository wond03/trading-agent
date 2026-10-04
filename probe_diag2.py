# 一次性诊断⑤: 同时查两个品种的真实持仓/保证金/杠杆/交易所挂单/成交流水
#   问题1: XAU 保证金为什么是 10U(而不是 5U 或 6.31U)?
#   问题2: BTC 止盈为什么这么近?
# 只在 GitHub Actions 上跑(需要 OKX 密钥)
import os
import sys
import json
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

CST = datetime.timezone(datetime.timedelta(hours=8))


def T(ts):
    v = float(ts or 0)
    if v > 1_000_000_000_000:
        v /= 1000.0
    return datetime.datetime.fromtimestamp(v, CST).strftime("%m-%d %H:%M:%S")


c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

for INST in ("XAU-USDT-SWAP", "BTC-USDT-SWAP"):
    print("#" * 78)
    print(f"### {INST}")
    print("#" * 78)
    print("① 持仓明细")
    try:
        j = c._get("/api/v5/account/positions", {"instId": INST})
        rows = [x for x in (j.get("data") or []) if float(x.get("pos") or 0) != 0]
        if not rows:
            print("   无持仓")
        for x in rows:
            for k in ("posSide", "pos", "avgPx", "lever", "mgnMode", "margin", "imr", "mmr",
                      "notionalUsd", "liqPx", "markPx", "last", "upl", "uplRatio",
                      "cTime", "uTime", "posId", "adl"):
                print(f"   {k} = {x.get(k)}")
            try:
                _ct = 0.001 if INST.startswith("XAU") else 0.01
                print(f"   [换算] pos×ctVal×avgPx ≈ {float(x.get('pos'))*_ct*float(x.get('avgPx')):.2f} U")
            except Exception:
                pass
    except Exception as e:
        print("   失败", type(e).__name__, e)

    print("② 账户对该合约的杠杆设置(isolated)")
    try:
        j = c._get("/api/v5/account/leverage-info", {"instId": INST, "mgnMode": "isolated"})
        print("   ", json.dumps(j, ensure_ascii=False)[:400])
    except Exception as e:
        print("   失败", type(e).__name__, e)

    print("③ 交易所条件单(止盈/止损)在挂")
    try:
        j = c.get_algo_pending(inst_type="SWAP", inst_id=INST)
        rows = j.get("data") or []
        if not rows:
            print("   无")
        for x in rows:
            print(f"   algoId={x.get('algoId')} 类型={x.get('ordType')} 方向={x.get('side')} "
                  f"posSide={x.get('posSide')} 张={x.get('sz')} 止盈触发={x.get('tpTriggerPx')} "
                  f"止损触发={x.get('slTriggerPx')} 状态={x.get('state')} 创建={T(x.get('cTime'))}")
    except Exception as e:
        print("   失败", type(e).__name__, e)

    print("④ 最近成交流水(20)")
    try:
        j = c.get_fills(inst_type="SWAP", inst_id=INST, limit=20)
        for x in (j.get("data") or []):
            print(f"   {T(x.get('ts'))} {x.get('side'):<5} 价={x.get('fillPx'):<10} 张={x.get('fillSz'):<6} "
                  f"盈亏={x.get('fillPnl') or '-':<9} posSide={x.get('posSide')} 类型={x.get('ordType')}")
    except Exception as e:
        print("   失败", type(e).__name__, e)

print("#" * 78)
print("### 账户余额")
try:
    print("   ", json.dumps((c.get_balance().get("data") or [{}])[0], ensure_ascii=False)[:500])
except Exception as e:
    print("   失败", e)
print("完成")
