# 暗夜猎手 (NightHunter) · 出场管理
# 出场管理 —— 森林查尔斯课程模块D实现
# 规则依据: D1-D8 (止盈三原则/前高保本/结构位追踪止损/提前止盈)
import config as C
from structure import atr

class Position:
    def __init__(self, direction, entry, sl, tp, size=1.0, opened_bar=0):
        self.direction = direction    # 'long'/'short'
        self.entry = entry
        self.sl = sl
        self.tp = tp
        self.size = size              # 1.0 = 满仓
        self.opened_bar = opened_bar
        self.risk_free = False        # 是否已上保本
        self.tp1_hit = False
        self.history = []

    def __repr__(self):
        return (f"Position[{self.direction}] entry={self.entry:.1f} SL={self.sl:.1f} "
                f"TP={self.tp:.1f} size={self.size:.0%} risk_free={self.risk_free}")

class ExitEngine:
    """止盈三原则 (规则D1):
    ①出量(成交量>均量*2) → 上保本 (2026-10-02 用户裁定: 只上保护, 不主动减仓)
    ②趋势转换(反向CHoCH) → 立即出场, 不论盈亏
    ③到TP → 止盈
    附加: 摸前高/前低→上保本(D2); 突破结构位→SL移到被突破位(D4)"""

    def manage(self, pos, candles, se, le, i=None):
        """返回动作列表: ('EXIT'|'PARTIAL_TP'|'MOVE_SL'|'HOLD', 说明)"""
        i = i if i is not None else len(candles) - 1
        bar = candles[i]
        actions = []

        # ---- 硬性出场: SL / TP 触发 ----
        if pos.direction == "long":
            if bar.low <= pos.sl:
                actions.append(("EXIT", f"止损触发 @{pos.sl:.1f}", pos.sl))
                return actions
            if bar.high >= pos.tp:
                actions.append(("EXIT", f"止盈触发TP @{pos.tp:.1f} (规则D1-③)", pos.tp))
                return actions
        else:
            if bar.high >= pos.sl:
                actions.append(("EXIT", f"止损触发 @{pos.sl:.1f}", pos.sl))
                return actions
            if bar.low <= pos.tp:
                actions.append(("EXIT", f"止盈触发TP @{pos.tp:.1f} (规则D1-③)", pos.tp))
                return actions

        # ---- 规则D1-②: 反向CHoCH → 立即出场 ----
        recent = [e for e in se.events if 0 <= i - e[0] <= 3]
        if pos.direction == "long" and any(e[1] == "CHoCH_down" for e in recent):
            actions.append(("EXIT", "趋势转换CHoCH_down, 立即出场不论盈亏 (规则D1-②)", bar.close))
            return actions
        if pos.direction == "short" and any(e[1] == "CHoCH_up" for e in recent):
            actions.append(("EXIT", "趋势转换CHoCH_up, 立即出场不论盈亏 (规则D1-②)", bar.close))
            return actions

        # ---- 规则D1-①: 出量 → 上保本 (用户裁定2026-10-02: 改为不主动减仓) ----
        #   课程 BV1H8cuzmEe5[004min]「一旦出量就要吃」; BV1w8cuzmEFY[013min]「上保护之前你都要吃」
        #   → 口径: 出量只把止损移到成本价(上保护), 仓位不动; 出场交给 TP(D1-③) / 趋势转换(D1-②)
        vols = [c.vol for c in candles[max(0, i-20):i]]
        if vols and bar.vol > (sum(vols)/len(vols)) * C.VOLUME_SPIKE_MULT:
            if not pos.risk_free:
                pos.sl = max(pos.sl, pos.entry) if pos.direction == "long" else min(pos.sl, pos.entry)
                pos.risk_free = True
                actions.append(("MOVE_SL", f"出量(vol={bar.vol:.0f}) → 止损上移保本 (规则D1-①)"))

        # ---- 规则D2: 摸前高/前低 → 上保本 ----
        if not pos.risk_free:
            hs = [s for s in se.swings if s[1] == "H"]
            ls = [s for s in se.swings if s[1] == "L"]
            if pos.direction == "long" and hs and bar.high >= hs[-1][2] * 0.999:
                actions.append(("MOVE_SL", f"触及前高{hs[-1][2]:.1f}, 止损移至保本 (规则D2)"))
                pos.sl = max(pos.sl, pos.entry); pos.risk_free = True
            if pos.direction == "short" and ls and bar.low <= ls[-1][2] * 1.001:
                actions.append(("MOVE_SL", f"触及前低{ls[-1][2]:.1f}, 止损移至保本 (规则D2)"))
                pos.sl = min(pos.sl, pos.entry); pos.risk_free = True

        # ---- 规则D4: 突破结构位 → SL移到被突破位下方 ----
        if C.TRAIL_SL_ON_BOS:
            for e in [x for x in se.events if 0 <= i - x[0] <= 2]:
                if pos.direction == "long" and e[1] == "BOS_up":
                    new_sl = e[2] - atr(candles) * C.SL_BUFFER_ATR
                    if new_sl > pos.sl:
                        actions.append(("MOVE_SL", f"BOS_up突破位{e[2]:.1f}, SL上移 (规则D4)"))
                        pos.sl = new_sl
                if pos.direction == "short" and e[1] == "BOS_down":
                    new_sl = e[2] + atr(candles) * C.SL_BUFFER_ATR
                    if new_sl < pos.sl:
                        actions.append(("MOVE_SL", f"BOS_down突破位{e[2]:.1f}, SL下移 (规则D4)"))
                        pos.sl = new_sl

        if not actions:
            actions.append(("HOLD", "持有中"))
        pos.history.extend(actions)
        return actions
