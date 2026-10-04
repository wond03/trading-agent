# 验证 A 方案: 交易所实际"每张占用保证金" → 5U 仓位
#   ① 有持仓时: 实测反推  ② 无持仓时: 用已学"有效倍率"(开仓时的真实情形)  ③ 梯度表
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


class _NoPos:                                 # 模拟"开仓瞬间": 无持仓, 只能靠已学倍率
    def get_positions(self, *a, **k):
        return {"data": []}

    def position_tier_imr(self, *a, **k):
        return None


for inst in ("XAU-USDT-SWAP", "BTC-USDT-SWAP"):
    print("=" * 70)
    print("###", inst)
    try:
        t = (c._get("/api/v5/market/ticker", {"instId": inst}).get("data") or [{}])[0]
        px = float(t.get("last") or 0)
    except Exception as e:
        print("ticker失败", e)
        px = 0.0
    ct = C.INST_SPECS[inst]["ctVal"]
    print(f"当前价={px} 目标保证金={C.INST_MARGIN_USD.get(inst)}U")

    # ① 有持仓: 实测
    mpc = M.real_margin_per_contract(c, inst, px, "isolated")
    s1 = size_fixed_margin(px, inst, leverage=C.INST_LEVER[inst], mgn_per_contract=mpc)
    print("① 实测路径 →", json.dumps(s1, ensure_ascii=False))

    # 求本次实测 eff, 构造"已学"state
    eff = None
    try:
        for p in (c.get_positions(inst).get("data") or []):
            pos = abs(float(p.get("pos") or 0)); m = float(p.get("margin") or 0); a = float(p.get("avgPx") or 0)
            if pos > 0 and m > 0:
                eff = round(ct * a * pos / m, 4)
    except Exception:
        pass
    print(f"   本次实测有效倍率 eff={eff}")
    if eff:
        st = {"margin_eff": {inst: eff}}
        mpc2 = M.real_margin_per_contract(_NoPos(), inst, px, "isolated", st)
        s2 = size_fixed_margin(px, inst, leverage=C.INST_LEVER[inst], mgn_per_contract=mpc2)
        print("② 无持仓+已学路径 →", json.dumps(s2, ensure_ascii=False))
    else:
        print("② 跳过(当前无持仓, 学不到 eff)")
print("完成")
