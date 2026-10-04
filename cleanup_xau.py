# 清理: 黄金重复的 TP/SL 挂单(保留最新一对), 并列出所有在挂单(看那笔平半仓限价单还在不在)
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from okx_client import OkxClient                              # noqa: E402

INST = "XAU-USDT-SWAP"
KEEP = {"3978869292988219392", "3978869286914867200"}          # 保留(最新, 10:45:45 引擎补挂的)

c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

print("① 普通挂单(未成交订单)")
try:
    for x in (c.get_pending_orders(inst_type="SWAP").get("data") or []):
        print(f"   {x.get('instId')} ordId={x.get('ordId')} {x.get('side')}/{x.get('posSide')} "
              f"类型={x.get('ordType')} 张={x.get('sz')} 价={x.get('px')} 已成交={x.get('accFillSz')} "
              f"状态={x.get('state')} 创建={x.get('cTime')}")
except Exception as e:
    print("   失败", e)

print("② 条件单(止盈/止损)")
algos = c.get_algo_pending(inst_type="SWAP", inst_id=INST).get("data") or []
for a in algos:
    print(f"   algoId={a.get('algoId')} 张={a.get('sz')} 止盈={a.get('tpTriggerPx')} 止损={a.get('slTriggerPx')} "
          f"创建={a.get('cTime')} {'<- 保留' if a.get('algoId') in KEEP else '<- 重复, 撤掉'}")

print("③ 撤掉重复的条件单")
for a in algos:
    aid = a.get("algoId")
    if aid in KEEP:
        continue
    r = c.cancel_algo(INST, aid)
    print(f"   cancel {aid} -> code={r.get('code')} sCode={((r.get('data') or [{}])[0] or {}).get('sCode')} {r.get('msg')}")

print("④ 复核")
for a in (c.get_algo_pending(inst_type="SWAP", inst_id=INST).get("data") or []):
    print(f"   剩余 algoId={a.get('algoId')} 张={a.get('sz')} 止盈={a.get('tpTriggerPx')} 止损={a.get('slTriggerPx')}")
row = [x for x in (c.get_positions(inst_id=INST).get("data") or []) if float(x.get("pos") or 0) != 0]
for x in row:
    print(f"   持仓 {x['posSide']} {x['pos']}张 @{x['avgPx']} 保证金={x.get('margin')} 名义={x.get('notionalUsd')}")
print("完成")
