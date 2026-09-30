# 暗夜猎手 (NightHunter) · 风控与仓位
# 风控层 —— 森林查尔斯课程模块E1/F实现
# 规则依据: E1单笔1%风险/E3杠杆公式/E4上限/E5组合/F1五条件AND/F2日内限单/F9周末减仓
import config as C

class RiskManager:
    """所有开单必须过此门 (规则F1: 五条件严格AND, 缺一不做)"""

    def __init__(self, capital_usd=10000.0, risk_score=3):
        """capital_usd: 账户资金; risk_score: 风险承受评分0-3
        (规则E1减分制: 满3分=有存款+无贷款+有稳定工作; 无存款/有贷款/无稳定工作各减1分)"""
        self.capital = capital_usd
        self.risk_score = max(0, min(3, risk_score))
        self.daily_trades = 0
        self.trade_log = []

    # ---------- 仓位与杠杆 (规则E1/E3/E4) ----------
    def risk_pct(self):
        """风险评分越低, 单笔风险越小 (减1分风险降0.25%)"""
        base = C.RISK_PER_TRADE
        return max(0.0025, base - (3 - self.risk_score) * 0.0025)

    def leverage_for_stop(self, stop_pct):
        """规则E3: 杠杆 = 100 ÷ 止损幅度% - 1档(留手续费缓冲)
        例: 止损10% -> 理论10倍 -> 实开8倍; 止损20% -> 理论5倍 -> 4倍"""
        theo = 100.0 / max(stop_pct, 0.01)
        practical = max(1, int(theo) - 1)
        return min(practical, C.MAX_LEVERAGE_CAP)   # 规则E4: 上限20倍

    def position_size(self, entry, sl, direction):
        """规则E1: 单笔最大亏损 = 资金 × 风险% -> 反推仓位
        返回: {qty, notional, margin, leverage, risk_amount}"""
        per_unit_risk = abs(entry - sl)
        if per_unit_risk <= 0:
            return None
        risk_amount = self.capital * self.risk_pct()
        qty = risk_amount / per_unit_risk
        stop_pct = per_unit_risk / entry * 100
        lev = self.leverage_for_stop(stop_pct)
        notional = qty * entry
        margin = notional / lev
        # 保证金不得超过资金的一半(防单笔占用过重)
        if margin > self.capital * 0.5:
            scale = (self.capital * 0.5) / margin
            qty *= scale; notional *= scale; margin *= scale
        return {"qty": round(qty, 6), "notional": round(notional, 2), "margin": round(margin, 2),
                "leverage": lev, "risk_amount": round(risk_amount, 2), "stop_pct": round(stop_pct, 2)}

    # ---------- 五条件 AND 门 (规则F1) ----------
    def check_gates(self, signal, all_conditions=None, is_weekend=False):
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
        # 周末减仓 (规则F9)
        if is_weekend:
            detail.append(f"⚠️周末流动性差, 仓位×{C.WEEKEND_POSITION_FACTOR} (规则F9)")
        return ok, detail

    def register_trade(self, signal, size_info):
        self.daily_trades += 1
        self.trade_log.append({"bar": getattr(signal, "reason", ""), "size": size_info})

    def reset_daily(self):
        self.daily_trades = 0

# ========== 固定保证金模式 (用户指定: 5U × 100倍) ==========
def size_fixed_margin(price, inst_id):
    """固定保证金仓位: 张数 = (保证金×杠杆) / (每张面值×价格), 按步长取整, 不低于最小下单"""
    spec = C.INST_SPECS.get(inst_id)
    if not spec:
        return None
    notional = C.MARGIN_PER_TRADE * C.LEVERAGE_FIXED
    raw_lots = notional / (spec["ctVal"] * price)
    lot = spec["lotSz"]
    lots = max(round(raw_lots / lot) * lot, spec["minSz"])
    actual_notional = lots * spec["ctVal"] * price
    actual_margin = actual_notional / C.LEVERAGE_FIXED
    return {"lots": round(lots, 6), "notional": round(actual_notional, 2),
            "margin": round(actual_margin, 2), "leverage": C.LEVERAGE_FIXED,
            "risk_amount": round(actual_margin, 2), "stop_pct": round(100.0 / C.LEVERAGE_FIXED, 2)}

def liquidation_price(entry, direction):
    """爆仓价估算 (100倍: 反向约1/杠杆-mmr)"""
    mmr = C.MMR_ESTIMATE
    if direction == "long":
        return entry * (1 - 1.0 / C.LEVERAGE_FIXED + mmr)
    return entry * (1 + 1.0 / C.LEVERAGE_FIXED - mmr)

def liquidation_sl(entry, direction):
    """等效止损 = 爆仓线前 0.3% 强制平仓 (避免爆仓罚金, 用户指定'爆仓按你的来')
    返回 (止损价, 爆仓价)"""
    liq = liquidation_price(entry, direction)
    buf = entry * C.LIQ_BUFFER_PCT
    if direction == "long":
        return liq + buf, liq      # 多单: 先于爆仓线触发
    return liq - buf, liq          # 空单

class PyramidingManager:
    """滚仓仓位管理 (规则E7/E8/E10)"""

    def __init__(self):
        self.bound_positions = []   # 绑定单(最多2张, 规则E7)

    def should_add(self, base_margin, unrealized_pnl, current_legs):
        """规则E7: 浮盈达保证金2倍才加仓; 加仓保证金=利润部分;
        主升浪最多2张绑定单; 第2张爆仓则两张同平"""
        if current_legs >= C.MAX_BOUND_POSITIONS:
            return False, f"已达{current_legs}张绑定单上限(规则E7)"
        if unrealized_pnl < base_margin * C.PYRAMID_TRIGGER_PROFIT:
            return False, f"浮盈{unrealized_pnl:.0f}未达保证金2倍({base_margin*2:.0f}), 不加仓(规则E7)"
        add_margin = min(unrealized_pnl, base_margin)   # 只用利润加仓, 绝不超额
        return True, f"浮盈达标, 用利润加仓{add_margin:.0f} (规则E7)"

    def pyramid_spot_add(self, total_position, drop_pct):
        """规则E10倒金字塔: 越跌越加、比重递增、位置越来越好
        返回加仓比例建议 [15%, 20%, 25%, 30%...]"""
        levels = [0.10, 0.15, 0.20, 0.25, 0.30]   # 规则E9现货金字塔
        if drop_pct < 5:
            return 0, "回撤不足, 暂不加"
        idx = min(int(drop_pct // 5) - 1, len(levels) - 1)
        return levels[idx], f"回撤{drop_pct:.0f}%, 按倒金字塔加{levels[idx]:.0%} (规则E10)"

    def portfolio_split(self):
        """规则E5: 80%现货 + 20%合约"""
        return {"spot_pct": C.SPOT_PERP_SPLIT[0], "perp_pct": C.SPOT_PERP_SPLIT[1]}
