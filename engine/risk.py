# 暗夜猎手 (NightHunter) · 风控与仓位
# 风控层 —— 森林查尔斯课程模块E1/F实现
# 2026-10-02 清理: 删除未接线的死代码(杠杆公式/1%风险仓位/滚仓 PyramidingManager)
#   实际下单走【固定保证金 × 固定杠杆】(用户指定), 见下方 size_fixed_margin
import config as C

class RiskManager:
    """开单前的门 (规则F1: 五条件严格AND, 缺一不做)"""

    def __init__(self, capital_usd=10000.0, risk_score=3):
        self.capital = capital_usd
        self.risk_score = max(0, min(3, risk_score))
        self.daily_trades = 0
        self.trade_log = []

    # ---------- 五条件 AND 门 (规则F1) ----------
    def check_gates(self, signal, all_conditions=None):
        """返回 (通过: bool, 明细: list[str])
        五条件: ①HTF趋势 ②截取 ③转势 ④回踩 ⑤触发 —— 严格AND"""
        detail, ok = [], True
        s = signal.steps
        cond = {
            "①HTF趋势": bool(s.get("htf_trend")),
            "②流动性截取": bool(s.get("sweep")),
            "③转势确认": bool(s.get("turn")),
            "④回踩到位": bool(s.get("retrace") and (s["retrace"].get("in_retrace") or s["retrace"].get("in_fvg"))),
            "⑤触发信号": bool(s.get("trigger")),
        }
        if all_conditions:
            cond.update(all_conditions)
        for k, v in cond.items():
            detail.append(f"{'✅' if v else '❌'}{k}")
            if not v: ok = False
        # 日内限单 (规则F2)
        if self.daily_trades >= C.DAILY_MAX_TRADES:
            detail.append(f"❌日内已开{self.daily_trades}单(上限{C.DAILY_MAX_TRADES}, 规则F2)")
            ok = False
        return ok, detail

# ========== 固定保证金模式 (用户指定: 5U × 100倍) ==========
def size_fixed_margin(price, inst_id, leverage=None):
    """固定保证金仓位: 张数 = (保证金×杠杆) / (每张面值×价格), 按步长取整, 不低于最小下单
    leverage: 实际可用杠杆(不同品种上限不同, XAU实测50), 默认取 C.LEVERAGE_FIXED"""
    spec = C.INST_SPECS.get(inst_id)
    if not spec:
        return None
    lev = leverage or C.LEVERAGE_FIXED
    notional = C.MARGIN_PER_TRADE * lev
    raw_lots = notional / (spec["ctVal"] * price)
    lot = spec["lotSz"]
    lots = max(round(raw_lots / lot) * lot, spec["minSz"])
    actual_notional = lots * spec["ctVal"] * price
    actual_margin = actual_notional / lev
    return {"lots": round(lots, 6), "notional": round(actual_notional, 2),
            "margin": round(actual_margin, 2), "leverage": lev,
            "risk_amount": round(actual_margin, 2), "stop_pct": round(100.0 / lev, 2)}

def liquidation_price(entry, direction, leverage=None):
    """爆仓价估算 (反向约1/杠杆-mmr)"""
    lev = leverage or C.LEVERAGE_FIXED
    mmr = C.MMR_ESTIMATE
    if direction == "long":
        return entry * (1 - 1.0 / lev + mmr)
    return entry * (1 + 1.0 / lev - mmr)

def liquidation_sl(entry, direction, leverage=None):
    """等效止损 = 爆仓线前 0.3% 强制平仓 (避免爆仓罚金)
    返回 (止损价, 爆仓价)"""
    liq = liquidation_price(entry, direction, leverage)
    buf = entry * C.LIQ_BUFFER_PCT
    if direction == "long":
        return liq + buf, liq      # 多单: 先于爆仓线触发
    return liq - buf, liq          # 空单
