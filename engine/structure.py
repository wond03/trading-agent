# 暗夜猎手 (NightHunter) · 结构引擎
# 结构引擎 —— 森林查尔斯课程模块A实现
# 规则依据: A1-A13 (BOS实体确认/CHoCH/盘整屏蔽/极值取法绿bar原则/周期只推一级)
import config as C

class Candle:
    __slots__ = ("ts", "open", "high", "low", "close", "vol")
    def __init__(self, ts, o, h, l, c, v):
        self.ts, self.open, self.high, self.low, self.close, self.vol = ts, o, h, l, c, v

def atr(candles, period=14):
    """⚠️ ATR 属【体系外指标】—— 课程明确否定技术指标
    (BV1w8cuzmEcp[011min]「什么 m a c d、布林带 这些都是废的」; BV1w8cuzmEDA[010min]「指标…没有用」)
    2026-10-02 交易逻辑中的 ATR 用法已全部移除; 此函数仅为历史诊断脚本保留, 新代码请勿使用"""
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

# ★语义口径(2026-10-03 用户裁定):
#   BOS   = 实体收盘越过前高/前低 → 结构【延续】(顺势)
#   CHoCH = 实体收盘打穿反向极值   → 结构【反转预警】(逆势; 只是"可能"反转, 不是一定反转)
#   ★当前实现: CHoCH 仍即时翻转 self.trend(是否改为"预警+等反向BOS确认"待用户看回测后决定)
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
    def process(self, candles):
        """批量处理历史K线(增量也可, 内部按序逐根)"""
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
        self.in_consolidation = self._check_consolidation(hs, ls)   # ★仅作日志/诊断参考, 不再参与结构确认(2026-10-03 取消盘整屏蔽)
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
        # ★2026-10-03 用户裁定: **取消「盘整屏蔽」**, 回归课程的二元口径。
        #   原文 BV1w8cuzmEcp[029min]「开个大级别看它是实体还是引线, 只要是引线它就是假的」
        #                        「根本不用分析…也不用我煞费苦心地去看我 BOS 的定义了」
        #   → 实体经济收过 = 真突破 (BOS/CHoCH); 影线刺破 = 假突破 (截取流动性)。
        #   原「盘整区内突破不确认结构」(consolidation_break_ignored) 会把**实体**突破也否掉,
        #   与原文冲突(实测: 10-02 01:00 收盘 84,908 越过 84,093 被吞掉, 结构转多迟到约10小时), 已删除。
        #   ★注: 这里的"实体收过"= BOS(顺势延续) ; 逆势的实体收过 = CHoCH = 反转预警(非确认)。
        if broke_up_close:
            if self.trend == "down":
                self.events.append((i, "CHoCH_up", sh_p))       # 规则A2: 收过最后高点(反转预警↑)
                self.trend = "up"
            else:
                self.events.append((i, "BOS_up", sh_p))          # 规则A1
                if self.trend is None: self.trend = "up"
            self.last_swing_high = None  # 突破后锁定, 等新swing确认(规则A5/BOS后重算)
            self._sh_locked = True
            self._locked_sh_idx = i
        elif broke_up_wick:
            self.events.append((i, "sweep_up_liquidity", sh_p))      # 影线扫高 = 上方流动性截取(假突破)
        if broke_dn_close:
            if self.trend == "up":
                self.events.append((i, "CHoCH_down", sl_p))      # 规则A2: 收破最后低点(反转预警↓)
                self.trend = "down"
            else:
                self.events.append((i, "BOS_down", sl_p))
                if self.trend is None: self.trend = "down"
            self.last_swing_low = None
            self._sl_locked = True
            self._locked_sl_idx = i
        elif broke_dn_wick:
            self.events.append((i, "sweep_down_liquidity", sl_p))    # 影线扫低 = 下方流动性截取(假突破)

    def _check_consolidation(self, hs, ls):
        """规则A4: 盘整 = "看不到结构"
        原文 BV1w8cuzmEmx[016min]「有棱有角的地方才叫结构…狗屎盘面在这盘整的它就不能称之为是结构」
        2026-10-02 去掉 ATR(体系外指标): 改为【定性】判定 ——
        最近的高低点既没有"高点抬高+低点抬高"(上涨结构)也没有"高点降低+低点降低"(下跌结构)
        → 没有结构递进 → 盘整"""
        if len(hs) < 2 or len(ls) < 2:
            return False
        h1, h2 = hs[-2][2], hs[-1][2]
        l1, l2 = ls[-2][2], ls[-1][2]
        up_struct = (h2 > h1) and (l2 > l1)     # 高点抬高 + 低点抬高
        dn_struct = (h2 < h1) and (l2 < l1)     # 高点降低 + 低点降低
        return not (up_struct or dn_struct)

    # ★2026-10-03 用户裁定: 已删除 _blocked_by_consolidation() ——「盘整屏蔽」取消,
    #   不再用"盘整"去否决实体突破。结构只按课程二元口径: 实体收过=真突破 / 影线刺破=假突破。

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
