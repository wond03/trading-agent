# 暗夜猎手 (NightHunter) · 结构引擎
# 结构引擎 —— 森林查尔斯课程模块A实现
#
# ★★2026-10-04 用户裁定: 「改的地方用开源库的 bos 和 choch, 周期 1+15」
#    本文件内 BOS/CHoCH 为 **开源库 smartmoneyconcepts(joshyattridge ⭐2043) 的逐字移植**:
#      · _swing_hl()      ← smc.swing_highs_lows()   (左右各 S 根的窗口极值 + 连续同类合并)
#      · _bos_choch()     ← smc.bos_choch()          (最近4个swing点的单调结构 → BOS/CHoCH, 按收盘判定)
#    移植而非 import: 线上不新增依赖; 且可加"无未来函数"守卫(见 C.SMC_STRICT_CAUSAL)
#    ★守卫原因: 原库允许"break 发生在 swing 确认之前"(break 最早在 pivot+2, 而 swing 要 pivot+S 才确认)
#      → 回测会偷看未来。开启守卫后 break 只在 pivot+S 之后才认。
#    周期: 1H(背景/趋势) + 15m(入场), 见 config.STRATEGY_PROFILES
#
#   · BOS   = 结构【延续】(顺势)      · CHoCH = 结构【变盘】(逆势)
#   · 斐波腿 = 最近确认 swing 低 ↔ 最近确认 swing 高
#   · 影线永不参与结构判定(影线破位 = 假突破/截取, 归 LiquidityEngine)
import config as C
from collections import deque


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
    ⚠️ 仅为 liquidity.py / diag_pipeline.py 的诊断用途保留;
       结构引擎(BOS/CHoCH)已改用 _swing_hl()(开源库口径, 高优先于低 + 内置合并)
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


# ============================================================================
#  开源库移植区 (smartmoneyconcepts · joshyattridge, MIT)
# ============================================================================
def _swing_hl(highs, lows, s):
    """← smc.swing_highs_lows(ohlc, swing_length=s)
    swing 高 = 该根最高价 == 窗口 highs[i-s+1 : i+s+1] 的最大值;
    swing 低 = 该根最低价 == 同窗口最小值; 高优先(同一根既是最高又是最低 → 记高)。
    再做"连续同类合并"(保留更高的高/更低的低), 最后把首尾两根设为反向标记。
    返回 hl[i] ∈ {0(无), 1(swing高), -1(swing低)}"""
    n = len(highs)
    hl = [0] * n
    if n < s + 1 or s < 1:
        return hl
    dq_mx, dq_mn = deque(), deque()
    for j in range(n):
        while dq_mx and highs[dq_mx[-1]] <= highs[j]:
            dq_mx.pop()
        dq_mx.append(j)
        while dq_mn and lows[dq_mn[-1]] >= lows[j]:
            dq_mn.pop()
        dq_mn.append(j)
        start = j - 2 * s + 1
        while dq_mx and dq_mx[0] < start:
            dq_mx.popleft()
        while dq_mn and dq_mn[0] < start:
            dq_mn.popleft()
        if j >= 3 * s - 1:                     # ★与 pandas rolling(2s) 的位置计数等价(不是 2s-1)
            i = j - s
            if highs[i] == highs[dq_mx[0]]:
                hl[i] = 1
            elif lows[i] == lows[dq_mn[0]]:
                hl[i] = -1
    # 连续同类合并: 相邻同类型只留更极端的那个
    while True:
        pos = [i for i in range(n) if hl[i] != 0]
        if len(pos) < 2:
            break
        rem = set()
        for a in range(len(pos) - 1):
            p, q = pos[a], pos[a + 1]
            if hl[p] == 1 and hl[q] == 1:
                rem.add(p if highs[p] < highs[q] else q)
            elif hl[p] == -1 and hl[q] == -1:
                rem.add(p if lows[p] > lows[q] else q)
        if not rem:
            break
        for p in rem:
            hl[p] = 0
    # 首尾设为反向标记(原库行为): 保证 swing 序列从两端都能闭合
    pos = [i for i in range(n) if hl[i] != 0]
    if pos:
        if hl[pos[0]] == 1:
            hl[0] = -1
        if hl[pos[0]] == -1:
            hl[0] = 1
        if hl[pos[-1]] == -1:
            hl[-1] = 1
        if hl[pos[-1]] == 1:
            hl[-1] = -1
    return hl


def _bos_choch(closes, highs, lows, hl, s, strict_causal=None):
    """← smc.bos_choch(ohlc, swing_highs_lows, close_break=True)
    取最近 4 个 swing 点 (o4=类型序, l4=价位序), 判单调结构:
      BOS   多: [低,高,低,高] 且 l1<l2<l3<l4   / BOS   空: [高,低,高,低] 且 l1>l2>l3>l4
      CHoCH 多: [低,高,低,高] 且 l4>l2>l1>l3   / CHoCH 空: [高,低,高,低] 且 l4<l2<l1<l3
    事件落在"倒数第2个swing点", 价位 = 其 own level; 再由【收盘】穿越该价位定 BrokenIndex。
    未被突破的事件丢弃; 被后续事件"覆盖"的早期事件也丢弃(原库 overrun 规则)。
    ★strict_causal: True 时要求 break 发生在 swing 确认(pivot+s)之后 → 无未来函数。
    返回 [(pivot_i, 'BOS'|'CHoCH', +1/-1, level, broken_i), ...]"""
    if strict_causal is None:
        strict_causal = getattr(C, "SMC_STRICT_CAUSAL", True)
    n = len(closes)
    bos = [0] * n
    choch = [0] * n
    lvl = [0.0] * n
    lv_order, o_order, last_pos = [], [], []
    for i in range(n):
        if hl[i] == 0:
            continue
        lv_order.append(highs[i] if hl[i] == 1 else lows[i])
        o_order.append(hl[i])
        if len(lv_order) >= 4:
            lp = last_pos[-2]
            l1, l2, l3, l4 = lv_order[-4], lv_order[-3], lv_order[-2], lv_order[-1]
            o4 = o_order[-4:]
            bos[lp] = 1 if (o4 == [-1, 1, -1, 1] and l1 < l3 < l2 < l4) else 0
            if bos[lp] != 0:
                lvl[lp] = l2
            bos[lp] = -1 if (o4 == [1, -1, 1, -1] and l1 > l3 > l2 > l4) else bos[lp]
            if bos[lp] != 0:
                lvl[lp] = l2
            choch[lp] = 1 if (o4 == [-1, 1, -1, 1] and l4 > l2 > l1 > l3) else 0
            if choch[lp] != 0:
                lvl[lp] = l2
            choch[lp] = -1 if (o4 == [1, -1, 1, -1] and l4 < l2 < l1 < l3) else choch[lp]
            if choch[lp] != 0:
                lvl[lp] = l2
        last_pos.append(i)
    # 突破确认(收盘穿越) + overrun 清理
    broken = [0] * n
    for i in range(n):
        if bos[i] == 0 and choch[i] == 0:
            continue
        sgn = bos[i] if bos[i] != 0 else choch[i]
        m0 = max(i + 2, i + s) if strict_causal else i + 2
        j = 0
        for m in range(m0, n):
            if sgn > 0 and closes[m] > lvl[i]:
                j = m
                break
            if sgn < 0 and closes[m] < lvl[i]:
                j = m
                break
        if j:
            broken[i] = j
            for k in range(i):
                if (bos[k] != 0 or choch[k] != 0) and broken[k] >= j:
                    bos[k] = choch[k] = 0
                    lvl[k] = 0
                    broken[k] = 0
    out = []
    for i in range(n):
        if (bos[i] != 0 or choch[i] != 0) and broken[i] != 0:
            kind = "BOS" if bos[i] != 0 else "CHoCH"
            sgn = bos[i] if bos[i] != 0 else choch[i]
            out.append((i, kind, sgn, lvl[i], broken[i]))
    return out


# ============================================================================
#  结构状态机
# ============================================================================
class StructureEngine:
    """结构状态机 —— BOS/CHoCH 由 _bos_choch() 给出(开源库口径)
    对外字段(与旧版一致, 上层无感):
      trend            'up'/'down'/None  = 最后一个结构事件的方向
      events           [(break_idx, 'BOS_up'|'BOS_down'|'CHoCH_up'|'CHoCH_down', level)]
      swings           [(idx, 'H'|'L', price)]
      last_swing_high / last_swing_low   = 最近【已确认】swing 高/低 (斐波腿)
      seg_high / seg_low                 = 同上(兼容旧调用)
    """
    def __init__(self):
        self.swings = []
        self.trend = None
        self.events = []
        self.last_swing_high = None
        self.last_swing_low = None
        self.seg_high = None
        self.seg_low = None
        self.range_high = None
        self.range_low = None
        self.in_consolidation = False
        self.last_idx = -1

    def process(self, candles):
        """批量计算(引擎每次用完整窗口调用; 结果只依赖已收盘K线 → 无未来函数)"""
        n = len(candles)
        self.last_idx = n - 1
        if n < 3:
            self.events, self.swings = [], []
            return self.snapshot()
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        s = max(1, C.SWING_LEFT)
        hl = _swing_hl(highs, lows, s)
        self.swings = [(i, "H" if hl[i] == 1 else "L", highs[i] if hl[i] == 1 else lows[i])
                       for i in range(n) if hl[i] != 0]
        raw = _bos_choch(closes, highs, lows, hl, s)
        self.events = sorted(
            [(b, f"{k}_{'up' if sgn > 0 else 'down'}", lv) for (_p, k, sgn, lv, b) in raw],
            key=lambda x: x[0])
        self.trend = None
        for (_b, nm, _lv) in self.events:
            self.trend = "up" if nm.endswith("up") else "down"
        # 斐波腿: 最近【已确认】swing(第 s 根之后才确认, 末 s 根不作数)
        lim = n - 1 - s
        hs = [x for x in self.swings if x[1] == "H" and x[0] <= lim]
        ls = [x for x in self.swings if x[1] == "L" and x[0] <= lim]
        self.last_swing_high = self.seg_high = hs[-1] if hs else None
        self.last_swing_low = self.seg_low = ls[-1] if ls else None
        return self.snapshot()

    def _check_consolidation(self, hs, ls):
        """规则A4: 盘整 = "看不到结构"(原文 BV1w8cuzmEmx[016min]) —— 当前未启用"""
        if len(hs) < 2 or len(ls) < 2:
            return False
        h1, h2 = hs[-2][2], hs[-1][2]
        l1, l2 = ls[-2][2], ls[-1][2]
        return not (((h2 > h1) and (l2 > l1)) or ((h2 < h1) and (l2 < l1)))

    def snapshot(self):
        hs = [x for x in self.swings if x[1] == "H"][-2:]
        ls = [x for x in self.swings if x[1] == "L"][-2:]
        return {
            "trend": self.trend,
            "in_consolidation": self.in_consolidation,
            "recent_swings_high": hs,
            "recent_swings_low": ls,
            "events_tail": self.events[-8:],
        }
