# 结构引擎 —— 森林查尔斯课程模块A实现
# 规则依据: A1-A13 (BOS实体确认/CHoCH/盘整屏蔽/极值取法绿bar原则/周期只推一级)
import config as C

class Candle:
    __slots__ = ("ts", "open", "high", "low", "close", "vol")
    def __init__(self, ts, o, h, l, c, v):
        self.ts, self.open, self.high, self.low, self.close, self.vol = ts, o, h, l, c, v

def atr(candles, period=14):
    """ATR(14), 用于盘整判定/止损缓冲/FVG过滤"""
    if len(candles) < period + 1:
        return 0
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]; p = candles[i-1]
        trs.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))
    trs = trs[-(period * 3):]
    return sum(trs[:period]) / period

def find_swings(candles, left=None, right=None):
    """swing识别: 高/低点高于(低于)左右各N根 (基础窗口法)
    返回: swings = [(idx, 'H'|'L', price)], 已按时间排序"""
    left = left or C.SWING_LEFT
    right = right or C.SWING_RIGHT
    swings = []
    for i in range(left, len(candles) - right):
        win = candles[i - left: i + right + 1]
        bar = candles[i]
        if bar.high == max(b.high for b in win):
            swings.append((i, "H", bar.high))
        if bar.low == min(b.low for b in win):
            swings.append((i, "L", bar.low))
    # 同价相邻同类去重(保留更高H/更低L)
    dedup = []
    for s in swings:
        if dedup and dedup[-1][1] == s[1]:
            if (s[1] == "H" and s[2] >= dedup[-1][2]) or (s[1] == "L" and s[2] <= dedup[-1][2]):
                dedup[-1] = s
        else:
            dedup.append(s)
    return dedup

class StructureEngine:
    """结构状态机: 逐根喂K线, 输出事件(BOS/CHoCH/MSS)与当前趋势
    核心二元判定(规则A11): 影线刺破=流动性截取(不确认结构); 实体收盘越过=真突破(确认结构)"""
    def __init__(self):
        self.swings = []          # [(idx, 'H'/'L', price)]
        self.trend = None         # 'up' / 'down' / None
        self.events = []          # 事件流
        self.last_swing_high = None   # (idx, price)
        self.last_swing_low = None
        self.range_high = None    # 盘整区(规则A4)
        self.range_low = None
        self.in_consolidation = False
        self._i = -1
        self._sh_locked = False   # 突破后参考点锁定
        self._sl_locked = False
        self._locked_sh_idx = -1
        self._locked_sl_idx = -1
        self._last_atr = None

    def _is_consolidation(self, swings):
        """规则A4: 最近一次swing high与swing low间距 < ATR*1.5 → 盘整"""
        hs = [s for s in swings if s[1] == "H"]
        ls = [s for s in swings if s[1] == "L"]
        if not hs or not ls:
            return False
        rng = hs[-1][2] - ls[-1][2]
        return rng < self._last_atr * C.CONSOLIDATION_ATR

    def process(self, candles):
        """批量处理历史K线(增量也可, 内部按序逐根)"""
        self._last_atr = atr(candles)
        for i in range(self._i + 1, len(candles)):
            self._step(candles, i)
        self._i = len(candles) - 1
        return self.snapshot()

    def _step(self, candles, i):
        bar = candles[i]
        # 1) 全量重算swing(确定性), 取已确认部分(索引<=i-SWING_RIGHT)
        confirmed = find_swings(candles[: i + 1])
        self.swings = [s for s in confirmed if s[0] <= i - C.SWING_RIGHT]
        hs = [s for s in self.swings if s[1] == "H"]
        if hs and (not self._sh_locked or hs[-1][0] > self._locked_sh_idx):
            self.last_swing_high = hs[-1]
            self._sh_locked = False
        ls = [s for s in self.swings if s[1] == "L"]
        if ls and (not self._sl_locked or ls[-1][0] > self._locked_sl_idx):
            self.last_swing_low = ls[-1]
            self._sl_locked = False
        self.in_consolidation = self._check_consolidation(hs, ls)
        if self.last_swing_high is None or self.last_swing_low is None:
            return
        sh_p = self.last_swing_high[2]
        sl_p = self.last_swing_low[2]
        # 2) 核心二元判定: 实体收过 vs 影线刺破 (规则A11)
        broke_up_close = bar.close > sh_p
        broke_up_wick = bar.high > sh_p and not broke_up_close
        broke_dn_close = bar.close < sl_p
        broke_dn_wick = bar.low < sl_p and not broke_dn_close
        # 3) 事件判定
        if broke_up_close:
            if self._blocked_by_consolidation("up"):
                self.events.append((i, "consolidation_break_ignored", sh_p))
            else:
                if self.trend == "down":
                    self.events.append((i, "CHoCH_up", sh_p))       # 规则A2: 下降趋势中收过最后低点上方→此处为收过高点→由降转升
                    self.trend = "up"
                else:
                    self.events.append((i, "BOS_up", sh_p))          # 规则A1
                    if self.trend is None: self.trend = "up"
                self.last_swing_high = None  # 突破后锁定, 等新swing确认(规则A5/BOS后重算)
                self._sh_locked = True
                self._locked_sh_idx = i
        elif broke_up_wick:
            self.events.append((i, "sweep_up_liquidity", sh_p))      # 影线扫高=上方流动性截取
        if broke_dn_close:
            if self._blocked_by_consolidation("down"):
                self.events.append((i, "consolidation_break_ignored", sl_p))
            else:
                if self.trend == "up":
                    self.events.append((i, "CHoCH_down", sl_p))      # 规则A2: 转空
                    self.trend = "down"
                else:
                    self.events.append((i, "BOS_down", sl_p))
                    if self.trend is None: self.trend = "down"
                self.last_swing_low = None
                self._sl_locked = True
                self._locked_sl_idx = i
        elif broke_dn_wick:
            self.events.append((i, "sweep_down_liquidity", sl_p))    # 影线扫低=下方流动性截取

    def _check_consolidation(self, hs, ls):
        """规则A4: 区间宽度 < ATR*CONSOLIDATION_ATR → 盘整"""
        if not hs or not ls or len(hs) < 1 or len(ls) < 1:
            return False
        a = self._last_atr
        if not a:
            return False
        rng = abs(hs[-1][2] - ls[-1][2])
        return rng < a * C.CONSOLIDATION_ATR

    _last_atr = None
    def _blocked_by_consolidation(self, direction):
        """规则A4: 盘整区内突破不确认结构"""
        return self.in_consolidation

    def snapshot(self):
        hs = [s for s in self.swings if s[1] == "H"][-2:]
        ls = [s for s in self.swings if s[1] == "L"][-2:]
        return {
            "trend": self.trend,
            "in_consolidation": self.in_consolidation,
            "recent_swings_high": hs,
            "recent_swings_low": ls,
            "events_tail": self.events[-8:],
        }
