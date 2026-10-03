# 暗夜猎手 (NightHunter) · 流动性模块
# 流动性模块 —— 森林查尔斯课程模块B实现
# 规则依据: B1-B11 (FVG定义/CE中点/iFVG/IFVG牛熊转换/双点截取/内外部流动性)
import config as C

class LiquidityEngine:
    """逐根喂K线, 维护: FVG列表(状态)/截取事件/内外部流动性目标"""
    def __init__(self):
        self.fvgs = []            # 活跃FVG: {idx, kind:'bull'/'bear', top, bottom, filled, covered, born_idx}
        self.sweeps = []          # 截取事件: (idx, dir, level, points_swept)
        self.events = []

    def process(self, candles):
        for i in range(2, len(candles)):
            self._detect_fvg(candles, i)
            self._update_fvgs(candles, i)
        self._detect_sweeps(candles)
        return self.snapshot()

    # ---- FVG (规则B1) ----
    def _detect_fvg(self, candles, i):
        """FVG = 一根K线留下的缺口
        原文 BV1w8cuzmE2N[012min]「大幅的拉升在中间产生了一个空档的区域…市场有可能会回补」
        2026-10-02 去 ATR: 原文没有任何尺寸门槛, 也不要求"三根K线"(那是市面理论, 无原文支撑)"""
        c0, c1, c2 = candles[i-2], candles[i-1], candles[i]
        # bull FVG: bar[i-2].high < bar[i].low (向上失衡)
        if c2.low > c0.high:
            self.fvgs.append({"idx": i, "kind": "bull", "top": c2.low, "bottom": c0.high,
                              "filled": False, "covered": False, "born_idx": i, "entered_idx": None})
            self.events.append((i, "FVG_bull", c0.high, c2.low))
        # bear FVG: bar[i-2].low > bar[i].high (向下失衡)
        if c2.high < c0.low:
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
    # ---------- 止损密集区 (2026-10-03 用户新口径: 影线破位 ≠ 截取, 必须扫到密集区) ----------
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
        修正: 流动性位用 swing 高点/低点(结构位), 而非近50根极值 —— 符合课程"扫前高/前低"原意
        双点(B5): 单根K线扫过的 swing 点数 >= 2
        ★性能优化(数学完全等价, 2026-10-02): 原实现每根K线重算 find_swings(candles[:i]) → 整段回放 O(n^3);
          改为「一次生成全序列原始 swing + 双指针推进 + 流式复刻相邻同类去重」。
          等价性依据: swing 点需右侧 right 根确认, 故截至第 i 根时 find_swings(candles[:i]) 可见的
          最大 swing 下标 = i-1-right; 去重是对"按时间序原始 swing 序列"的左侧折叠, 可按指针推进流式复现。
          已由 tools/_equiv_check.py 对 BTC/XAU 的 1h/4h/15m 全量逐 i 校验(每根 mismatch=0, 最终 sweeps 相同)。"""
        left, right = C.SWING_LEFT, C.SWING_RIGHT
        n = len(candles)
        # ① 一次生成全序列原始 swing(与 structure.find_swings 的原始部分完全一致: 同索引 H 先 L 后)
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
        dedup = []                              # 流式复刻 find_swings 的"同价相邻同类去重(保留更高H/更低L)"
        for i in range(10, n):
            limit = i - 1 - right               # = find_swings(candles[:i]) 中可能出现的最大的 swing 下标
            while ptr < m and raw_swings[ptr][0] <= limit:
                s = raw_swings[ptr]; ptr += 1
                if dedup and dedup[-1][1] == s[1]:
                    if (s[1] == "H" and s[2] >= dedup[-1][2]) or (s[1] == "L" and s[2] <= dedup[-1][2]):
                        dedup[-1] = s
                else:
                    dedup.append(s)
            recent = dedup[-C.ZONE_LOOKBACK:]                 # 最近6个swing点=待猎取的流动性池
            if not recent:
                continue
            bar = candles[i]
            # ★2026-10-03 新口径: 先建"止损密集区"候选, 再看影线是否扫到它并收回
            _hs = [(j, p) for (j, k, p) in recent if k == "H"]
            _ls = [(j, p) for (j, k, p) in recent if k == "L"]
            _cu, _cd = [], []
            if _hs:
                for lv, cnt in self._zones(_hs, "H", C.ZONE_TOL_PCT):
                    _cu.append((lv, cnt, "cluster" if cnt >= 2 else "swing"))
                _cu.append((max(p for _, p in _hs), len(_hs), "extreme"))      # 前高
            if _ls:
                for lv, cnt in self._zones(_ls, "L", C.ZONE_TOL_PCT):
                    _cd.append((lv, cnt, "cluster" if cnt >= 2 else "swing"))
                _cd.append((min(p for _, p in _ls), len(_ls), "extreme"))      # 前低
            _th = self._trendline(_hs, i) if _hs else None
            _tl = self._trendline(_ls, i) if _ls else None
            if _th is not None:
                _cu.append((_th, C.TRENDLINE_PTS, "trendline"))
            if _tl is not None:
                _cd.append((_tl, C.TRENDLINE_PTS, "trendline"))
            # 上截取: 影线越过密集区上沿/压制线, 收盘收回下方
            _hu = [c for c in _cu if bar.high > c[0] and bar.close < c[0]]
            if _hu:
                b = max(_hu, key=lambda c: c[1])
                raw.append((i, "up", b[0], b[1], b[2]))
            # 下截取: 影线跌破密集区下沿/支撑线, 收盘收回上方
            _hd = [c for c in _cd if bar.low < c[0] and bar.close > c[0]]
            if _hd:
                b = max(_hd, key=lambda c: c[1])
                raw.append((i, "down", b[0], b[1], b[2]))
        # 同根同向去重(保留被扫点数最多的)
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
