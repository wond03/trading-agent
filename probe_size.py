# 验证 A 方案: 用交易所实际"每张占用保证金"换算 5U 仓位, 打印张数/名义/实收
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
import config as C                                            # noqa: E402
from okx_client import OkxClient                              # noqa: E402
from risk import size_fixed_margin                            # noqa: E402
import main as M                                              # noqa: E402

c = OkxClient(api_key=os.environ["OKX_API_KEY"], secret=os.environ["OKX_SECRET_KEY"],
              passphrase=os.environ["OKX_PASSPHRASE"], simulated=True)

for inst in ("XAU-USDT-SWAP", "BTC-USDT-SWAP"):
    print("=" * 70)
    print("###", inst)
    try:
        t = (c._get("/api/v5/market/ticker", {"instId": inst}).get("data") or [{}])[0]
        px = float(t.get("last") or 0)
    except Exception as e:
        print("ticker失败", e)
        px = 0.0
    print(f"当前价 = {px}")
    # 原始 imr
    try:
        fam = "-".join(inst.split("-")[:2])
        j = c._get("/api/v5/public/position-tiers",
                   {"instType": "SWAP", "tdMode": "isolated", "instFamily": fam})
        d = j.get("data") or []
        print("梯度表首档原始 =", json.dumps(d[0], ensure_ascii=False) if d else "无")
        print(">> position_tier_imr() =", c.position_tier_imr(inst))
    except Exception as e:
        print("tier失败", e)
    mpc = M.real_margin_per_contract(c, inst, px, "isolated")
    size = size_fixed_margin(px, inst, leverage=C.INST_LEVER[inst], mgn_per_contract=mpc)
    print(">> 目标保证金 =", C.INST_MARGIN_USD.get(inst))
    print(">> 结算:", json.dumps(size, ensure_ascii=False))
print("完成")
