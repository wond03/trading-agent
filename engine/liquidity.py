# 流动性模块 —— 森林查尔斯课程模块B实现
# 规则依据: B1-B11 (FVG定义/CE中点/iFVG/IFVG牛熊转换/双点截取/内外部流动性)
import config as C
from structure import atr

class LiquidityEngine:
    """逐根喂K线, 维护: FVG列表(状态)/截取事件/内外部流动性目标"""
    def __init__(self):
        self.fvgs = []            # 活跃FVG: {idx, kind:'bull'/'bear', top, bottom, filled, covered, born_idx}
        self.sweeps = []          # 截取事件: (idx, dir, level, points_swept)
        self.events = []

    def process(self, candles):
        a = atr(candles)
        for i in range(2, len(candles)):
            self._detect_fvg(candles, i, a)
            self._update_fvgs(candles, i)
        self._detect_sweeps(candles)
        return self.snapshot()

    # ---- FVG (规则B1: 三根K线失衡缺口) ----
    def _detect_fvg(self, candles, i, a):
        c0, c1, c2 = candles[i-2], candles[i-1], candles[i]
        min_size = a * C.FVG_MIN_ATR
        # bull FVG: bar[i-2].high < bar[i].low (向上失衡)
        if c2.low > c0.high and (c2.low - c0.high) >= min_size:
            self.fvgs.append({"idx": i, "kind": "bull", "top": c2.low, "bottom": c0.high,
                              "filled": False, "covered": False, "born_idx": i, "entered_idx": None})
            self.events.append((i, "FVG_bull", c0.high, c2.low))
        # bear FVG: bar[i-2].low > bar[i].high (向下失衡)
        if c2.high < c0.low and (c0.low - c2.high) >= min_size:
            self.fvgs.append({"idx": i, "kind": "bear", "top": c0.low, "bottom": c2.high,
                              "filled": False, "covered": False, "born_idx": i, "entered_idx": None})
            self.events.append((i, "FVG_bear", c0.low, c2.high))

    def _update_fvgs(self, candles, i):
        """更新FVG状态 (修正版):
        - 回踩进入区间(entered): 保留! 这是入场参考(规则C6/C9), 并非失效
        - 实体收盘完全穿过(规则B3): FVG失效 → 翻转成iFVG
        - 老化: 超过100根未使用移除"""
        bar = candles[i]
        for f in self.fvgs:
            if f["filled"]:
                continue
            if f["kind"] == "bull":
                if bar.low <= f["top"] and bar.low >= f["bottom"] and f.get("entered_idx") is None:
                    f["entered_idx"] = i
                    self.events.append((i, "FVG_bull_entered", f["bottom"], f["top"]))
                if bar.close < f["bottom"]:                     # 实体完全穿过 → 失效+翻转iFVG
                    f["filled"] = True; f["covered"] = True
                    self.events.append((i, "iFVG_bear_flip", f["bottom"], f["top"]))
                    self.fvgs.append({"idx": i, "kind": "bear", "top": f["top"], "bottom": f["bottom"],
                                      "filled": False, "covered": False, "born_idx": f["born_idx"],
                                      "entered_idx": None})
            else:
                if bar.high >= f["bottom"] and bar.high <= f["top"] and f.get("entered_idx") is None:
                    f["entered_idx"] = i
                    self.events.append((i, "FVG_bear_entered", f["bottom"], f["top"]))
                if bar.close > f["top"]:
                    f["filled"] = True; f["covered"] = True
                    self.events.append((i, "iFVG_bull_flip", f["bottom"], f["top"]))
                    self.fvgs.append({"idx": i, "kind": "bull", "top": f["top"], "bottom": f["bottom"],
                                      "filled": False, "covered": False, "born_idx": f["born_idx"],
                                      "entered_idx": None})
        # 清理: 失效的 + 老化100根的
        self.fvgs = [f for f in self.fvgs if not f["filled"] and (i - f["idx"]) <= 100]

    def ifvg_bull_bear_flip(self):
        """规则B4: 下跌FVG出现后 3~8根 内被实体向上穿过(iFVG_bull_flip) → 牛熊转换信号"""
        for e in self.events:
            if e[1] != "iFVG_bull_flip":
                continue
            i = e[0]
            near = [f for f in self.events
                    if f[1] == "FVG_bear" and C.IFVG_CONFIRM_BARS[0] <= i - f[0] <= C.IFVG_CONFIRM_BARS[1]]
            if near:
                return {"signal": "bull_bear_flip", "at": i,
                        "born": near[-1][0], "bars": i - near[-1][0]}
        return None

    # ---- 流动性截取 (规则A11影线vs实体 + B5双点) ----
    def _detect_sweeps(self, candles):
        """截取 = 影线扫过「近期已确认swing点」又收回 (规则A11/B8)
        修正: 流动性位用 swing 高点/低点(结构位), 而非近50根极值 —— 符合课程"扫前高/前低"原意
        双点(B5): 单根K线扫过的 swing 点数 >= 2"""
        from structure import find_swings
        raw = []
        for i in range(10, len(candles)):
            bar = candles[i]
            swings = find_swings(candles[:i])     # 截至前一根的已确认swing
            recent = swings[-6:]                  # 最近6个swing点=待猎取的流动性池
            if not recent:
                continue
            # 上截取: 影线扫过swing高点, 收盘收回下方
            swept_up = [(si, p) for (si, k, p) in recent if k == "H" and bar.high > p and bar.close < p]
            if swept_up:
                level = max(p for _, p in swept_up)          # 扫到的最极端高点
                raw.append((i, "up", level, len(swept_up)))
            # 下截取: 影线扫过swing低点, 收盘收回上方
            swept_dn = [(si, p) for (si, k, p) in recent if k == "L" and bar.low < p and bar.close > p]
            if swept_dn:
                level = min(p for _, p in swept_dn)
                raw.append((i, "down", level, len(swept_dn)))
        # 同根同向去重(保留被扫点数最多的)
        best = {}
        for s in raw:
            k = (s[0], s[1])
            if k not in best or s[3] > best[k][3]:
                best[k] = s
        self.sweeps = sorted(best.values(), key=lambda x: x[0])[-60:]
        for s in self.sweeps:
            self.events.append((s[0], f"sweep_{s[1]}", s[2], f"points={s[3]}"))

    def double_point_valid(self, sweep):
        """规则B5: 1H级别截取须扫到>=2个点"""
        return sweep[3] >= 2 if isinstance(sweep[3], int) else True

    def snapshot(self):
        active = [f for f in self.fvgs if not f["filled"]]
        return {
            "active_fvgs": active[-6:],
            "recent_sweeps": self.sweeps[-6:],
            "ifvg_flip": self.ifvg_bull_bear_flip(),
            "events_tail": self.events[-8:],
        }
