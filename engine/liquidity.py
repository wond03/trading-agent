# 暗夜猎手 (NightHunter) · 流动性模块
# 流动性模块 —— 森林查尔斯课程模块B实现
# 规则依据: B1-B11 (FVG定义/CE中点/iFVG/IFVG牛熊转换/双点截取/内外部流动性)
#
# ★2026-10-04 用户裁定「用别人成熟的代码」: FVG 缺口识别改用开源库
#   smartmoneyconcepts.smc.fvg() (joshyattridge, MIT)。失效口径仍按课程规则B3。
import pandas as pd
import smartmoneyconcepts as SMC

import config as C
from structure import ohlc_df


class LiquidityEngine:
    """逐根喂K线, 维护: FVG列表(状态)/截取事件/内外部流动性目标"""
    def __init__(self):
        self.fvgs = []            # 活跃FVG: {idx, kind:'bull'/'bear', top, bottom, filled, covered, born_idx}
        self.sweeps = []          # 截取事件: (idx, dir, level, points_swept, kind)
        self.events = []
        self.ifvg_events = []     # ★视频《IFVG的正确用法》: 被【反向实体收盘穿越】的FVG → IFVG 反转事件

    def process(self, candles):
        self._detect_fvg_lib(candles)
        self._detect_sweeps(candles)
        return self.snapshot()

    # ---- FVG (规则B1) —— ★缺口识别 = 开源库 smartmoneyconcepts ----
    def _detect_fvg_lib(self, candles):
        """FVG = 三根K线留下的失衡缺口
        区间(Top/Bottom)由开源库 smc.fvg() 给出; 失效仍按课程规则B3【实体收盘完全穿过】。
        (库自带的 mitigated = "被触碰", 口径过松: 一到 FVG 就判失效 → 无法作为入场参考, 故不用它)"""
        n = len(candles)
        self.fvgs = []
        self.ifvg_events = []
        if n < 3:
            return
        r = SMC.smc.fvg(ohlc_df(candles), join_consecutive=False)
        F = r["FVG"].to_numpy(); TOP = r["Top"].to_numpy(); BOT = r["Bottom"].to_numpy()
        out = []
        for i in range(n):
            if pd.isna(F[i]):
                continue
            top, bot = float(TOP[i]), float(BOT[i])
            filled = False
            flip_idx = None                               # ★IFVG: 触发"反向实体收盘穿越"的那根K线(反转蜡烛)
            body_entered = None                           # ★视频#2: 首个"实体进入缺口"的K线(非纯影线穿刺)
            for j in range(i + 1, n):                     # 规则B3: 实体收盘完全穿过 → 失效
                _b = candles[j]
                if body_entered is None and j >= i + 2:   # i+1 是形成缺口的第3根, 从 i+2 起才算"回踩进入"
                    _blo, _bhi = (_b.open, _b.close) if _b.open <= _b.close else (_b.close, _b.open)
                    if _bhi >= bot and _blo <= top:       # 实体(开收区间)与缺口重叠 = 实体进入
                        body_entered = j
                if F[i] == 1 and _b.close < bot:
                    filled = True; flip_idx = j; break
                if F[i] == -1 and _b.close > top:
                    filled = True; flip_idx = j; break
            out.append({"idx": i, "kind": "bull" if F[i] == 1 else "bear",
                        "top": top, "bottom": bot, "filled": filled, "covered": filled,
                        "born_idx": i, "entered_idx": None, "body_entered_idx": body_entered})
            self.events.append((i, "FVG_bull" if F[i] == 1 else "FVG_bear", bot, top))
            if flip_idx is not None:
                # ★2026-10-06 视频《IFVG的正确用法》: "被实体收盘穿越"不是销毁, 而是【角色反转成反向入场区】
                _fd = "bear" if F[i] == 1 else "bull"     # 多头缺口被向下穿过 → 反转方向=看空
                self.ifvg_events.append({"src_idx": i, "src_kind": "bull" if F[i] == 1 else "bear",
                                         "top": top, "bottom": bot, "ce": (top + bot) / 2.0,
                                         "flip_idx": flip_idx, "dir": _fd})
                self.events.append((flip_idx, f"iFVG_{_fd}_flip", bot, top))
        self.ifvg_events = self.ifvg_events[-200:]
        self.fvgs = [f for f in out if not f["filled"] and (n - 1 - f["idx"]) <= 100]

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
    def _zones(self, pts, kind, tol):
        """同向 swing 点按价格聚簇: 价差 <= tol 视为同一"止损密集区"(双顶/双底/等高)
        返回 [(level, count)] ; level = 簇内最极端价 (H 取最高 / L 取最低)"""
        cl = []
        for j, p in sorted(pts, key=lambda x: x[1]):
            if cl and abs(p - cl[-1][-1][1]) / max(abs(p), 1e-9) <= tol:
                cl[-1].append((j, p))
            else:
                cl.append([(j, p)])
        out = []
        for c in cl:
            lv = max(m[1] for m in c) if kind == "H" else min(m[1] for m in c)
            out.append((lv, len(c)))
        return out

    def _trendline(self, pts, i):
        """最近 3 个同向 swing 点连线(须单调: 低点递升=支撑线 / 高点递降=压制线)
        返回该线在第 i 根处的值(用最近两点斜率外推); 不成线返回 None"""
        if len(pts) < 3:
            return None
        (j1, p1), (j2, p2), (j3, p3) = sorted(pts, key=lambda x: x[0])[-3:]
        if j3 == j2 or j2 == j1:
            return None
        if not (p1 < p2 < p3 or p1 > p2 > p3):
            return None
        slope = (p3 - p2) / (j3 - j2)
        return p3 + slope * (i - j3)

    def _detect_sweeps(self, candles):
        """截取 = 影线扫过「近期已确认swing点」又收回 (规则A11/B8)
        流动性位用 swing 高点/低点(结构位); 双点(B5): 单根K线扫过的 swing 点数 >= 2
        ★性能优化(2026-10-02): 由 tools/_equiv_check.py 校验与逐根 find_swings 完全等价。"""
        left, right = C.SWING_LEFT, C.SWING_RIGHT
        n = len(candles)
        raw_swings = []
        for j in range(left, n - right):
            win = candles[j - left:j + right + 1]
            bar = candles[j]
            if bar.high == max(b.high for b in win):
                raw_swings.append((j, "H", bar.high))
            if bar.low == min(b.low for b in win):
                raw_swings.append((j, "L", bar.low))
        raw = []
        m = len(raw_swings)
        ptr = 0
        dedup = []
        for i in range(10, n):
            limit = i - 1 - right
            while ptr < m and raw_swings[ptr][0] <= limit:
                s = raw_swings[ptr]; ptr += 1
                if dedup and dedup[-1][1] == s[1]:
                    if (s[1] == "H" and s[2] >= dedup[-1][2]) or (s[1] == "L" and s[2] <= dedup[-1][2]):
                        dedup[-1] = s
                else:
                    dedup.append(s)
            recent = dedup[-C.ZONE_LOOKBACK:]
            if not recent:
                continue
            bar = candles[i]
            _hs = [(j, p) for (j, k, p) in recent if k == "H"]
            _ls = [(j, p) for (j, k, p) in recent if k == "L"]
            _cu, _cd = [], []
            if _hs:
                for lv, cnt in self._zones(_hs, "H", C.ZONE_TOL_PCT):
                    _cu.append((lv, cnt, "cluster" if cnt >= 2 else "swing"))
                _cu.append((max(p for _, p in _hs), len(_hs), "extreme"))
            if _ls:
                for lv, cnt in self._zones(_ls, "L", C.ZONE_TOL_PCT):
                    _cd.append((lv, cnt, "cluster" if cnt >= 2 else "swing"))
                _cd.append((min(p for _, p in _ls), len(_ls), "extreme"))
            _th = self._trendline(_hs, i) if _hs else None
            _tl = self._trendline(_ls, i) if _ls else None
            if _th is not None:
                _cu.append((_th, C.TRENDLINE_PTS, "trendline"))
            if _tl is not None:
                _cd.append((_tl, C.TRENDLINE_PTS, "trendline"))
            _hu = [c for c in _cu if bar.high > c[0] and bar.close < c[0]]
            if _hu:
                b = max(_hu, key=lambda c: c[1])
                raw.append((i, "up", b[0], b[1], b[2]))
            _hd = [c for c in _cd if bar.low < c[0] and bar.close > c[0]]
            if _hd:
                b = max(_hd, key=lambda c: c[1])
                raw.append((i, "down", b[0], b[1], b[2]))
        best = {}
        for s in raw:
            k = (s[0], s[1])
            if k not in best or s[3] > best[k][3]:
                best[k] = s
        self.sweeps = sorted(best.values(), key=lambda x: x[0])[-60:]
        for s in self.sweeps:
            self.events.append((s[0], f"sweep_{s[1]}", s[2],
                                f"points={s[3]} kind={s[4] if len(s) > 4 else '-'}"))

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
