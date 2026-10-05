# 暗夜猎手 (NightHunter) · 出场管理
# 出场管理 —— 森林查尔斯课程模块D实现
# 规则依据: D1-D8 (止盈三原则/前高保本/结构位追踪止损/提前止盈)
import config as C

class Position:
    def __init__(self, direction, entry, sl, tp, size=1.0, opened_bar=0, inst=None, lots=0):
        self.direction = direction    # 'long'/'short'
        self.entry = entry
        self.sl = sl
        self.tp = tp
        self.size = size              # 1.0 = 满仓(比例)
        self.opened_bar = opened_bar
        self.inst = inst              # 品种(算浮盈用)
        self.lots = lots              # 实际张数(算浮盈用)
        self.risk_free = False        # 是否已上保本
        self.tp1_hit = False
        self.risk0 = abs(entry - sl) if sl else 0.0   # ★2026-10-06: 开仓时的风险距离(算 1R 用)
        self.history = []

    def __repr__(self):
        return (f"Position[{self.direction}] entry={self.entry:.1f} SL={self.sl:.1f} "
                f"TP={self.tp:.1f} size={self.size:.0%} risk_free={self.risk_free}")

class ExitEngine:
    """出场规则:
    ①到 TP → 止盈 (规则D1-③)
    ②浮盈达 1 倍保证金(5U) → 上保本(止损移到成本价)
    附加: 突破结构位 → SL 移到被突破位(D4)
    说明: 原文的"出量止盈"(D1-①) 与"反向CHoCH立即出场"(D1-②), 2026-10-03 用户裁定均不做"""

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

        # ---- 规则D1-② "反向CHoCH→立即出场": 2026-10-03 用户裁定【不作为出场方式, 已移除】----

        # ---- 规则D1-① "出量止盈": 2026-10-03 用户裁定【不做】(原文只讲"出量要吃", 没给任何可量化定义) ----

        # ---- 规则D2 (★2026-10-06 用户裁定): 浮盈达【1R】→ 上保本 ----
        #   原口径"浮盈≥5U"在 25x / 125U 名义下 = 价格要涨 4% → 近乎不触发, 已删除。
        #   R = 开仓时的风险距离 |entry − sl0|, 与杠杆/保证金无关
        #   (笔记《FVG》分批止盈原文: "…并把止损移至盈亏平衡点")
        if not pos.risk_free:
            _sign = 1 if pos.direction == "long" else -1
            _risk0 = getattr(pos, "risk0", None) or abs(pos.entry - pos.sl)
            _fav = (bar.close - pos.entry) * _sign          # 有利方向的价格位移
            if _risk0 > 0 and _fav >= _risk0:
                pos.sl = max(pos.sl, pos.entry) if pos.direction == "long" else min(pos.sl, pos.entry)
                pos.risk_free = True
                actions.append(("MOVE_SL", f"浮盈 {_fav / _risk0:.2f}R ≥ 1R → 止损移到保本"))

        # ---- 规则D4: 突破结构位 → SL移到被突破位下方 ----
        if C.TRAIL_SL_ON_BOS:
            for e in [x for x in se.events if 0 <= i - x[0] <= 2]:
                if pos.direction == "long" and e[1] == "BOS_up":
                    new_sl = e[2]                       # 移到"被突破位"(原文D4; 2026-10-02 去掉ATR缓冲)
                    if new_sl > pos.sl:
                        actions.append(("MOVE_SL", f"BOS_up突破位{e[2]:.1f}, SL上移 (规则D4)"))
                        pos.sl = new_sl
                if pos.direction == "short" and e[1] == "BOS_down":
                    new_sl = e[2]                       # 移到"被突破位"(原文D4)
                    if new_sl < pos.sl:
                        actions.append(("MOVE_SL", f"BOS_down突破位{e[2]:.1f}, SL下移 (规则D4)"))
                        pos.sl = new_sl

        if not actions:
            actions.append(("HOLD", "持有中"))
        pos.history.extend(actions)
        return actions
