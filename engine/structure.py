# 暗夜猎手 (NightHunter) · 结构引擎
# 结构引擎 —— 森林查尔斯课程模块A实现
#
# ★★2026-10-04 用户裁定: 「用别人成熟的代码」—— 本文件的 BOS/CHoCH 与 swing 判定
#    **直接调用开源库 smartmoneyconcepts (joshyattridge, MIT, ⭐2k+)**，不再手搓移植:
#      · SMC.smc.swing_highs_lows(ohlc, swing_length=s)   → swing 高/低
#      · SMC.smc.bos_choch(ohlc, shl, close_break=True)   → BOS / CHoCH
#    · 对外接口不变(StructureEngine 的 trend/events/swings/last_swing_high/low)
#    · 仅保留一处【无未来函数守卫】(开源库原版允许 break 早于 swing 确认 → 回测偷看未来)
#  周期: 1H(背景/趋势) + 15m(入场), 见 config.STRATEGY_PROFILES
#
#   · BOS   = 结构【延续】(顺势)      · CHoCH = 结构【变盘】(逆势)
#   · 影线永不参与结构判定(影线破位 = 假突破/截取, 归 LiquidityEngine)
import pandas as pd
import smartmoneyconcepts as SMC

import config as C

# 依赖: pandas, smartmoneyconcepts  (见 requirements.txt / watch.yml 的 pip install)


class Candle:
    __slots__ = ("ts", "open", "high", "low", "close", "vol")

    def __init__(self, ts, o, h, l, c, v):
        self.ts, self.open, self.high, self.low, self.close, self.vol = ts, o, h, l, c, v


def ohlc_df(candles):
    """Candle 列表 → smartmoneyconcepts 需要的 DataFrame(列名小写 open/high/low/close/volume)"""
    df = pd.DataFrame({
        "open": [c.open for c in candles],
        "high": [c.high for c in candles],
        "low": [c.low for c in candles],
        "close": [c.close for c in candles],
        "volume": [c.vol for c in candles],
    })
    df.index = pd.RangeIndex(len(candles))
    return df


def atr(candles, period=14):
    """⚠️ ATR 属【体系外指标】—— 课程明确否定技术指标
    (BV1w8cuzmEcp[011min]「什么 ma cdb、布林带 这些都是废的」; BV1w8cuzmEDA[010min]「指标…没有用」)
    2026-10-02 交易逻辑中的 ATR 用法已全部移除; 此函数仅为历史诊断脚本保留, 新代码请勿使用"""
    if len(candles) < period + 1:
        return 0
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]; p = candles[i - 1]
        trs.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))
    trs = trs[-(period * 3):]
    return sum(trs[:period]) / period


def find_swings(candles, left=None, right=None):
    """swing识别: 高/低点高于(低于)左右各N根 (基础窗口法)
    ⚠️ 仅为 liquidity.py / diag_pipeline.py 的诊断用途保留;
       结构引擎(BOS/CHoCH)已改用开源库 smartmoneyconcepts 的 swing_highs_lows()
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
#  结构状态机 (底层判定 = 开源库 smartmoneyconcepts)
# ============================================================================
class StructureEngine:
    """结构状态机 —— BOS/CHoCH 由开源库 smartmoneyconcepts 直接给出
    对外字段(与旧版一致, 上层无感):
      trend            'up'/'down'/None  = 最后一个结构事件的方向
      events           [(break_idx, 'BOS_up'|'BOS_down'|'CHoCH_up'|'CHoCH_down', level)]
      swings           [(idx, 'H'|'L', price)]
      last_swing_high / last_swing_low   = 最近【已确认】swing 高/低
      seg_high / seg_low                 = 同上(兼容旧调用)
    """

    def __init__(self):
        self.swings = []
        self.trend = None
        self.trend_warn = None      # ★2026-10-05: CHoCH 只看作预警(等反向 BOS 确认) → 记在这里
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
        s = max(1, C.SWING_LEFT)
        df = ohlc_df(candles)

        # ---- swing 高/低 (开源库) ----
        shl = SMC.smc.swing_highs_lows(df, swing_length=s)
        hl = shl["HighLow"].to_numpy()
        lv = shl["Level"].to_numpy()
        self.swings = [(i, "H" if hl[i] == 1 else "L", float(lv[i]))
                       for i in range(n) if not pd.isna(hl[i])]

        # ---- BOS / CHoCH (开源库, 收盘判定) ----
        bc = SMC.smc.bos_choch(df, shl, close_break=True)
        B = bc["BOS"].to_numpy()
        H = bc["CHOCH"].to_numpy()
        L = bc["Level"].to_numpy()
        BI = bc["BrokenIndex"].to_numpy()
        strict = getattr(C, "SMC_STRICT_CAUSAL", True)
        ev = []
        for i in range(n):
            if pd.isna(B[i]) and pd.isna(H[i]):
                continue
            if pd.isna(BI[i]):
                continue
            bi = int(BI[i])
            # ★无未来函数守卫: 突破必须发生在 swing 确认(i+s)之后
            #   (开源库原版允许 break 最早在 i+2, 而 swing 要到 i+s 才确认 → 回测偷看未来)
            if strict and bi < i + s:
                continue
            kind = "BOS" if not pd.isna(B[i]) else "CHoCH"
            sgn = 1 if float(B[i] if not pd.isna(B[i]) else H[i]) > 0 else -1
            ev.append((bi, f"{kind}_{'up' if sgn > 0 else 'down'}", float(L[i])))
        self.events = sorted(ev, key=lambda x: x[0])
        # ★★2026-10-05 按用户笔记《BOS和CHOCH概念》修正趋势判定:
        #   笔记: "CHoCH 只是预警, 不一定马上反转, 最好等后续 BOS 确认新趋势"
        #   → 趋势 = 最近一个【BOS】的方向; CHoCH 不翻转趋势, 只记入 trend_warn(预警)。
        #   开关 C.CHOCH_IS_WARNING_ONLY=True(新口径) / False(旧口径: 最后一个事件即翻转)
        self.trend = None
        self.trend_warn = None
        if getattr(C, "CHOCH_IS_WARNING_ONLY", True):
            _bi, _bd, _ci, _cd = -1, None, -1, None
            for (_b, nm, _lv) in self.events:
                if nm.startswith("BOS"):
                    _bi, _bd = _b, ("up" if nm.endswith("up") else "down")
                else:
                    _ci, _cd = _b, ("up" if nm.endswith("up") else "down")
            self.trend = _bd
            if _ci > _bi and _cd != _bd:
                self.trend_warn = _cd          # 有未确认的反转预警
        else:
            for (_b, nm, _lv) in self.events:
                self.trend = "up" if nm.endswith("up") else "down"

        # 最近【已确认】swing(第 s 根之后才确认, 末 s 根不作数)
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
            "trend_warn": self.trend_warn,
            "in_consolidation": self.in_consolidation,
            "recent_swings_high": hs,
            "recent_swings_low": ls,
            "events_tail": self.events[-8:],
        }
