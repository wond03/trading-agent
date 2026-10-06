# 暗夜猎手 (NightHunter) · 入场模板
# 入场模板 —— 森林查尔斯课程模块C实现
# 规则依据: C1-C20 (五步流程/双蜡烛真假突破/MSS双仓/斐波分批/等待序列/时段过滤)
import config as C


def _pen(b, f):
    """价格真正『探进』缺口(严格越过近沿) —— 口径B: 缺口形成即视为挂单区, 价格探进就提示"""
    return (b.low < f["top"] - 1e-9) and (b.high > f["bottom"] + 1e-9)

class EntrySignal:
    def __init__(self, direction, entry, sl, tp, reason, steps, confidence="normal", sweep_pts=1):
        self.direction = direction   # 'long' / 'short'
        self.entry = entry
        self.sl = sl
        self.tp = tp
        self.reason = reason
        self.steps = steps           # 五步通过明细
        self.confidence = confidence # normal / high(多周期共振)
        self.sweep_pts = sweep_pts   # 截取扫过的点数

    def __repr__(self):
        rr = abs(self.tp - self.entry) / max(abs(self.entry - self.sl), 1e-9)
        return (f"[{self.direction.upper()}] entry={self.entry:.1f} SL={self.sl:.1f} TP={self.tp:.1f} "
                f"RR=1:{rr:.1f} | {self.reason}")

class EntryEngine:
    """五步流程状态机 (规则C1):
    ①大级别定趋势 ②下推一级找截取 ③切小级别看反转预警(CHoCH) ④等回踩FVG ⑤触发 → 开单
    总开关(规则C2): 无截取或无转 = 不开单"""

    def __init__(self):
        self.last_signal_bar = -99

    def evaluate(self, candles, se, le, htf_trend, bar_i=None, ltf_se=None, ltf_le=None, ltf_candles=None):
        """入口分发(★2026-10-06): 按 C.IFVG_MODE 选择模型
           "off"  = 仅 FVG 回踩模型(现行)
           "add"  = FVG 无信号时, 再用 IFVG 反转模型补一个信号(增量, 不改现有信号)
           "only" = 只用 IFVG 反转模型
        ★2026-10-06: 方向来源由 C.ENTRY_DIR_SOURCE 决定("1h"=现行 / "15m"=只看15m)
        """
        if str(getattr(C, "ENTRY_DIR_SOURCE", "1h")).lower() in ("15m", "ltf"):
            _t = getattr(ltf_se, "trend", None)
            if _t in ("up", "down"):
                htf_trend = _t
        if str(getattr(C, "SIGNAL_MODE", "chain")).lower() == "fvg_touch":
            steps = {}
            self.last_steps = steps
            return self._fvg_touch_signal(se, le, ltf_se, ltf_le, ltf_candles, htf_trend, steps)
        if str(getattr(C, "SIGNAL_MODE", "chain")).lower() == "fvg_handover":
            steps = {}
            self.last_steps = steps
            return self._fvg_handover_signal(se, le, ltf_se, ltf_le, ltf_candles, steps)
        if str(getattr(C, "SIGNAL_MODE", "chain")).lower() == "fvg_both":
            steps = {}
            self.last_steps = steps
            return self._fvg_both_signal(se, le, ltf_se, ltf_le, ltf_candles, steps)
        _mode = str(getattr(C, "IFVG_MODE", "off")).lower()
        _cm = str(getattr(C, "FVG_COUNTER_MODE", "off")).lower()
        if _mode == "only":
            steps = {}
            self.last_steps = steps
            return self._ifvg_signal(se, le, ltf_se, ltf_le, ltf_candles, htf_trend, steps)
        if _cm == "only":
            steps = {}
            self.last_steps = steps
            return self._counter_fvg_signal(se, le, ltf_se, ltf_le, ltf_candles, htf_trend, steps)
        sig = self._evaluate_fvg(candles, se, le, htf_trend, bar_i, ltf_se, ltf_le, ltf_candles)
        if sig is None and _cm == "add":
            steps = {}
            _s = self._counter_fvg_signal(se, le, ltf_se, ltf_le, ltf_candles, htf_trend, steps)
            if _s is not None:
                self.last_steps = steps
                return _s
        if sig is None and _mode == "add":
            steps = {}
            _s2 = self._ifvg_signal(se, le, ltf_se, ltf_le, ltf_candles, htf_trend, steps)
            if _s2 is not None:
                self.last_steps = steps
                return _s2
        return sig

    def _fvg_touch_signal(self, se, le, ltf_se, ltf_le, ltf_candles, htf_trend, steps):
        """★2026-10-07 用户裁定「可以」: 【15m FVG 回踩提示】(方案2)
           触发 = 最新一根 15m 新回踩进一个未回填的 15m FVG(上一根不在其中 = 新触及);
           方向 = FVG 方向(bull→做多 / bear→做空);
           背书 = 最近 N 根内出现过 BOS/CHoCH(仅作筛子, 不是四步门槛链);
           止损 = FVG 左侧那根K线极值外侧; 止盈 = 全局 TP_MODE。
        """
        _le = ltf_le if ltf_le is not None else le
        _se = ltf_se if ltf_se is not None else se
        _cd = ltf_candles
        if _le is None or not _cd or len(_cd) < 6:
            steps["fvgt"] = "无15m数据"; return None
        n = len(_cd)
        bar, prev = _cd[n - 1], _cd[n - 2]
        cands = []
        for f in (getattr(_le, "fvgs", []) or []):
            if f.get("filled") or f.get("idx") is None:
                continue
            if not (bar.low <= f["top"] and bar.high >= f["bottom"]):
                continue                                    # 本根未触及
            if prev.low <= f["top"] and prev.high >= f["bottom"]:
                continue                                    # 上一根已在缺口里 → 非"新回踩"
            cands.append(f)
        cands = sorted(cands, key=lambda x: int(x["idx"]))[-int(getattr(C, "FVGT_MAX_CAND", 4)):]
        steps["fvgt_n"] = len(cands)
        if not cands:
            steps["fvgt"] = "本根未新回踩进FVG"; return None
        if getattr(C, "FVGT_REQUIRE_STRUCT", True):         # 结构背书(方案2)
            _W = int(getattr(C, "FVGT_STRUCT_WINDOW", 8))
            _evs = [e for e in (getattr(_se, "events", []) or [])
                    if 0 <= n - 1 - int(e[0]) <= _W]
            if not _evs:
                steps["fvgt"] = f"最近{_W}根内无BOS/CHoCH结构(无背书)"; return None
            steps["fvgt_evt"] = [e[1] for e in _evs[-2:]]
        f = cands[-1]                                       # 取最近生成的那根
        d = "long" if f["kind"] == "bull" else "short"
        px = bar.close
        _li = int(f["idx"]) - 1
        lc = _cd[_li] if 0 <= _li < n else None
        if lc is None:
            steps["fvgt"] = "缺FVG左根K线"; return None
        if d == "long":
            sl = lc.low * (1 - C.SL_BUFFER_PCT); risk = px - sl
        else:
            sl = lc.high * (1 + C.SL_BUFFER_PCT); risk = sl - px
        if risk <= 0:
            steps["fvgt"] = "几何无效(price已在缺口外)"; return None
        tp, _src = self._resolve_tp(d, px, risk, _se)
        rr = abs(tp - px) / max(risk, 1e-9)
        _ev = (" · 近结构 " + "/".join(steps.get("fvgt_evt") or [])) if steps.get("fvgt_evt") else ""
        steps["fvgt"] = {"dir": d, "fvg": (round(float(f["bottom"]), 2), round(float(f["top"]), 2)),
                         "sl": round(sl, 2), "tp": round(tp, 2), "tp_src": _src, "RR": round(rr, 2)}
        _rz = (f"{'▲ 看涨' if d == 'long' else '▼ 看跌'}FVG回踩(15m) · 缺口 "
               f"{f['bottom']:.1f}~{f['top']:.1f}{_ev}")
        return EntrySignal(d, px, sl, tp, _rz, steps, "normal", 1)

    def _resolve_tp(self, d, px, risk, ltf_se):
        """止盈口径统一出口(★2026-10-07 用户要求: 止盈改"打结构位")
           "pct"    = 固定百分比(±TP_PCT%)
           "struct" = 结构位: 多单打到【上方最近的已确认摆动高点】, 空单打到【下方最近的摆动低点】;
                      距入场不足 TP_STRUCT_MIN_PCT% 的摆动点跳过(避免贴脸)，没有可用目标则退回 pct
           "rr"     = 按 R 倍数
        """
        mode = str(getattr(C, "TP_MODE", "pct")).lower()
        _pp = float(getattr(C, "TP_PCT", 1.0)) / 100.0
        if mode == "struct":
            _mp = float(getattr(C, "TP_STRUCT_MIN_PCT", 0.5)) / 100.0
            sw = getattr(ltf_se, "swings", []) or []
            if d == "long":
                _c = [x[2] for x in sw if x[1] == "H" and x[2] > px * (1 + _mp)]
                if _c:
                    return min(_c), "struct"
            else:
                _c = [x[2] for x in sw if x[1] == "L" and x[2] < px * (1 - _mp)]
                if _c:
                    return max(_c), "struct"
            return (px * (1 + _pp) if d == "long" else px * (1 - _pp)), "pct(退回)"
        if mode == "rr":
            _rr = float(C.TP_RR)
            return (px + _rr * risk if d == "long" else px - _rr * risk), "rr"
        return (px * (1 + _pp) if d == "long" else px * (1 - _pp)), "pct"

    def _fvg_handover_signal(self, se, le, ltf_se, ltf_le, ltf_candles, steps):
        """★2026-10-07 用户读图口径: 【缺口交接 → 回踩顺势缺口】
           ① 交接: 某个反向缺口被【实体收盘】打掉(liquidity.ifvg_events) → 方向 = 赢家一侧;
           ② 顺势缺口: 交接后 N 根内新生成、且尚未回填的同向缺口;
           ③ 触发: 本根【新回踩】进该顺势缺口(上一根不在其中);
           止损 = 该缺口左根K线极值外侧; 止盈 = 全局 TP_MODE。
        """
        _le = ltf_le if ltf_le is not None else le
        _se = ltf_se if ltf_se is not None else se
        _cd = ltf_candles
        if _le is None or not _cd or len(_cd) < 6:
            steps["fvgh"] = "无15m数据"; return None
        n = len(_cd)
        bar = _cd[n - 1]
        _age = int(getattr(C, "FVGH_MAX_AGE_BARS", 12))
        # ---- 交接事件: 两个来源 ----
        #  ①反向缺口被【实体收盘】打掉(liquidity.ifvg_events)
        #  ②★用户口径B: 缺口【接管】—— 后生成的反向缺口覆盖/重叠了同区域的前一个缺口
        _fvgs = [f for f in (getattr(_le, "fvgs", []) or [])
                 if f.get("idx") is not None and not f.get("filled")]
        ev = None
        for e in reversed(getattr(_le, "ifvg_events", []) or []):
            if 0 <= n - 1 - int(e["flip_idx"]) <= _age:
                ev = {"dir": e["dir"], "t": int(e["flip_idx"]),
                      "why": ("空" if e["src_kind"] == "bear" else "多") + "缺口被实体收盘打掉"}
                break
        if getattr(C, "FVGH_TAKEOVER", True):
            _best = None
            for f1 in _fvgs:
                for f0 in _fvgs:
                    if f0["kind"] == f1["kind"] or int(f1["idx"]) <= int(f0["idx"]):
                        continue
                    _lo = max(float(f0["bottom"]), float(f1["bottom"]))
                    _hi = min(float(f0["top"]), float(f1["top"]))
                    if _hi - _lo <= 0:                       # 不重叠 → 谈不上接管
                        continue
                    if _best is None or int(f1["idx"]) > _best["t"]:
                        _best = {"dir": "bear" if f1["kind"] == "bear" else "bull", "t": int(f1["idx"]),
                                 "why": ("空" if f1["kind"] == "bear" else "多") + "缺口接管了同区域的反向缺口"}
            if _best is not None and 0 <= n - 1 - _best["t"] <= _age:
                if ev is None:       # ★补位式(用户裁定B): 只在原口径(实体收盘打掉)取不到时, 才启用"接管"
                    ev = _best
        if ev is None:
            steps["fvgh"] = f"最近{_age}根内无缺口交接"; return None
        want = "bull" if ev["dir"] == "bull" else "bear"
        d = "long" if want == "bull" else "short"
        t_inv = int(ev["t"])
        if getattr(C, "FVGH_REQUIRE_CHOCH", False):
            _W = int(getattr(C, "FVGH_CHOCH_WINDOW", 12))
            _evs = [e for e in (getattr(_se, "events", []) or [])
                    if 0 <= n - 1 - int(e[0]) <= _W and str(e[1]).startswith("CHoCH")]
            if not _evs:
                steps["fvgh"] = f"最近{_W}根内无CHoCH"; return None
        _after = int(getattr(C, "FVGH_MAX_BARS_AFTER", 8))
        cands = [f for f in (getattr(_le, "fvgs", []) or [])
                 if f.get("kind") == want and not f.get("filled") and f.get("idx") is not None
                 and t_inv <= int(f["idx"]) <= t_inv + _after]
        steps["fvgh_n"] = len(cands)
        if not cands:
            steps["fvgh"] = "交接后无顺势缺口"; return None
        hit = []
        for f in cands:
            _fi = int(f["idx"])
            if (n - 1) < _fi + 1:
                continue                                  # 缺口尚未形成
            if not _pen(bar, f):
                continue                                  # 本根未探进缺口
            if any(_pen(_cd[k], f) for k in range(_fi + 1, n - 1)):
                continue                                  # 之前已探进过 → 非"首次回踩"
            hit.append(f)
        if not hit:
            steps["fvgh"] = "本根未新回踩进顺势缺口"; return None
        f = sorted(hit, key=lambda x: int(x["idx"]))[-1]
        px = bar.close
        _li = int(f["idx"]) - 1
        lc = _cd[_li] if 0 <= _li < n else None
        if lc is None:
            steps["fvgh"] = "缺FVG左根K线"; return None
        if d == "long":
            sl = lc.low * (1 - C.SL_BUFFER_PCT); risk = px - sl
        else:
            sl = lc.high * (1 + C.SL_BUFFER_PCT); risk = sl - px
        if risk <= 0:
            steps["fvgh"] = "几何无效(price已在缺口外)"; return None
        tp, _src = self._resolve_tp(d, px, risk, _se)
        rr = abs(tp - px) / max(risk, 1e-9)
        steps["fvgh"] = {"dir": d, "fvg": (round(float(f["bottom"]), 2), round(float(f["top"]), 2)),
                         "handover": ev["why"],
                         "sl": round(sl, 2), "tp": round(tp, 2), "tp_src": _src, "RR": round(rr, 2)}
        _rz = (f"{'▲ 看涨' if d == 'long' else '▼ 看跌'}缺口交接 · "
               f"{ev['why']} → 回踩顺势缺口 "
               f"{f['bottom']:.1f}~{f['top']:.1f}")
        return EntrySignal(d, px, sl, tp, _rz, steps, "normal", 1)

    def _fvg_both_signal(self, se, le, ltf_se, ltf_le, ltf_candles, steps):
        """★2026-10-07 用户裁定【两侧独立】（SIGNAL_MODE="fvg_both"）:
        多/空各自维护 —— 只要某一侧的缺口【没被反向缺口接管】(还"活着"), 价格首次探进它,
        就按【该缺口自己的方向】提示; 不再让"最近一次交接"把方向整个盖掉。
        （用户原话: "让它同时维护多、空两侧——只要某一侧的缺口还活着、价格回踩进去就提示"）
        止损 = 缺口左根K线极值外侧; 止盈 = 全局 TP_MODE。
        """
        _le = ltf_le if ltf_le is not None else le
        _se = ltf_se if ltf_se is not None else se
        _cd = ltf_candles
        if _le is None or not _cd or len(_cd) < 6:
            steps["fvgb"] = "无15m数据"; return None
        n = len(_cd)
        bar = _cd[n - 1]
        _fvgs = [f for f in (getattr(_le, "fvgs", []) or [])
                 if f.get("idx") is not None and not f.get("filled")]

        def _taken_over(f):
            """该缺口是否已被【后生成的反向缺口】接管(区间重叠) → 这一侧在该处失效"""
            for g in _fvgs:
                if g["kind"] == f["kind"] or int(g["idx"]) <= int(f["idx"]):
                    continue
                if min(float(f["top"]), float(g["top"])) - max(float(f["bottom"]), float(g["bottom"])) > 0:
                    return True
            return False

        hit = []
        for f in _fvgs:
            if _taken_over(f):
                continue                                          # 已被反向缺口接管
            _fi = int(f["idx"])
            if (n - 1) < _fi + 1:
                continue                                          # 缺口尚未形成
            if not _pen(bar, f):
                continue                                          # 本根未探进缺口
            if any(_pen(_cd[k], f) for k in range(_fi + 1, n - 1)):
                continue                                          # 之前已探进过 → 非"首次回踩"
            # ★用户理由②: 回踩必须是【影线】探进缺口, 实体压进缺口 = 真卖/买压 → 不做
            if getattr(C, "FVGB_WICK_ONLY", True):
                _bl, _bh = min(bar.open, bar.close), max(bar.open, bar.close)
                if f["kind"] == "bull" and _bl <= float(f["top"]):
                    continue
                if f["kind"] == "bear" and _bh >= float(f["bottom"]):
                    continue
            # ★用户理由①: 入场前出现"长上影"(多)/"长下影"(空) = 被拒绝 → 不做
            if getattr(C, "FVGB_REJECT_LONG_WICK", True):
                _r = float(getattr(C, "FVGB_WICK_RATIO", 1.5))
                _mp = float(getattr(C, "FVGB_WICK_MIN_PCT", 0.08)) / 100.0
                _bad = False
                for k in range(_fi + 1, n):
                    b = _cd[k]
                    _th = max(_r * abs(b.close - b.open), _mp * b.close)
                    if f["kind"] == "bull" and (b.high - max(b.open, b.close)) >= _th:
                        _bad = True; break
                    if f["kind"] == "bear" and (min(b.open, b.close) - b.low) >= _th:
                        _bad = True; break
                if _bad:
                    continue
            hit.append(f)
        steps["fvgb_n"] = len(hit)
        if not hit:
            steps["fvgb"] = "两侧均无新回踩(无既活着又被探进的缺口)"; return None
        f = sorted(hit, key=lambda x: int(x["idx"]))[-1]
        d = "long" if f["kind"] == "bull" else "short"
        px = bar.close
        _stop_src = "缺口左根K线极值"
        if str(getattr(C, "STOP_MODE", "fvg_left")).lower() == "key":
            _ks, _stop_src = self._key_stop(d, px, _se, _cd, _le)
            if _ks is None:                                  # ★口径③: 找不到合格止损位 → 这笔不做
                steps["fvgb"] = f"止损无可靠位 → 不做（{_stop_src}）"; return None
            sl = _ks * (1 - C.SL_BUFFER_PCT) if d == "long" else _ks * (1 + C.SL_BUFFER_PCT)
        else:
            _li = int(f["idx"]) - 1
            lc = _cd[_li] if 0 <= _li < n else None
            if lc is None:
                steps["fvgb"] = "缺FVG左根K线"; return None
            sl = lc.low * (1 - C.SL_BUFFER_PCT) if d == "long" else lc.high * (1 + C.SL_BUFFER_PCT)
        risk = (px - sl) if d == "long" else (sl - px)
        if risk <= 0:
            steps["fvgb"] = "几何无效(price已在缺口外)"; return None
        tp, _src = self._resolve_tp(d, px, risk, _se)
        rr = abs(tp - px) / max(risk, 1e-9)
        steps["fvgb"] = {"dir": d, "fvg": (round(float(f["bottom"]), 2), round(float(f["top"]), 2)),
                         "mode": "两侧独立(缺口未被反向接管)", "stop_src": _stop_src,
                         "sl": round(sl, 2), "tp": round(tp, 2), "tp_src": _src, "RR": round(rr, 2)}
        _rz = (f"{'▲ 看涨' if d == 'long' else '▼ 看跌'}缺口回踩(两侧独立) "
               f"{f['bottom']:.1f}~{f['top']:.1f}")
        return EntrySignal(d, px, sl, tp, _rz, steps, "normal", 1)

    def _key_stop(self, d, px, ltf_se, cd, le):
        """★2026-10-07 用户口径③: 止损 = 【本段关键极值】—— 且该位必须还"有效"。
        规则(按用户 03:15 那笔的三条否决理由):
          ①候选 = 最近【未被再测过】的摆动极值(多=L / 空=H);
          ②距离必须 ∈ [STOP_MIN_PCT, STOP_MAX_PCT](太近/太远都不做);
          ③该位附近若存在【已被回踩过】的缺口(±STOP_SPENT_ZONE_PCT) → "撑不住", 不认;
          ④无合格位 → 返回 None ⇒ 这笔直接不提示。
        返回 (止损价, 说明) 或 (None, 原因)
        """
        n = len(cd)
        _smin = float(getattr(C, "STOP_MIN_PCT", 0.2)) / 100.0
        _smax = float(getattr(C, "STOP_MAX_PCT", 0.65)) / 100.0
        if d == "long":
            _lo, _hi = px * (1 - _smax), px * (1 - _smin)
        else:
            _lo, _hi = px * (1 + _smin), px * (1 + _smax)
        # ★用户口径(终版): 只有【还没被回踩过】的缺口才有"否决权"——
        #   缺口一旦被价格回踩过一次就【退役】, 不再拿它去否决别的位(用户: "16:30的fvg被18:15的k线回踩过了")。
        _gaps = []
        for ev in (getattr(le, "events", []) or []):
            if not str(ev[1]).startswith("FVG"):
                continue
            gi = int(ev[0]); gb = min(float(ev[2]), float(ev[3])); gt = max(float(ev[2]), float(ev[3]))
            if gi >= n - 1:
                continue
            if any(cd[k].low <= gt and cd[k].high >= gb for k in range(gi + 2, n)):
                continue                                    # 已被回踩过 → 退役, 无否决权
            _gaps.append((gb, gt))
        out = []
        for idx, kind, lvl in (getattr(ltf_se, "swings", []) or []):
            if (d == "long" and kind != "L") or (d == "short" and kind != "H"):
                continue
            if idx >= n - 1 or (n - 1 - idx) > int(getattr(C, "STOP_SWING_N", 60)):
                continue
            if not (_lo <= lvl <= _hi):
                continue
            _tol = 0.0005
            if any((d == "long" and cd[k].low <= lvl * (1 + _tol)) or
                   (d == "short" and cd[k].high >= lvl * (1 - _tol)) for k in range(idx + 1, n)):
                continue                          # 已经被再测过 → 这个位不算数
            if any(gb <= lvl <= gt for gb, gt in _gaps):
                continue                          # 该位是"回踩缺口"留下的 → 不算干净的结构位
            out.append(lvl)
        if not out:
            return None, "没有'未被再测、周围也没被缺口消费过'的关键位"
        return max(out, key=lambda x: abs(x - px)), "本段结构极值(未被再测)"   # ★用户: 止损放"这一段的结构极值"(最外侧的合格位)

    def _counter_fvg_signal(self, se, le, ltf_se, ltf_le, ltf_candles, htf_trend, steps):
        """★2026-10-06 用户想法: 【反向 FVG】入场 —— "BOS 产生的 FVG 不只顺势那根有效"
           A) 有逆势 CHoCH 锚定: 15m 出现【与背景方向相反】的 CHoCH(结构反转) → 取该【反转方向】的 FVG → 回踩入场
           B) 无锚定(CFVG_REQUIRE_CHOCH=False): 只要出现【与背景方向相反的 FVG】→ 回踩入场
           方向 = 反转方向(与 1H 相反); 止损 = FVG 左根K线极值外侧; 止盈 = 全局 TP_MODE
        """
        _le = ltf_le if ltf_le is not None else le
        _se = ltf_se if ltf_se is not None else se
        _cd = ltf_candles
        if _le is None or not _cd or not htf_trend:
            steps["cfvg"] = "无15m数据/无背景方向"; return None
        n = len(_cd)
        want = "bear" if htf_trend == "up" else "bull"        # 反转方向 = 与背景相反
        _dir = "short" if want == "bear" else "long"
        _ci = None
        if getattr(C, "CFVG_REQUIRE_CHOCH", True):
            _name = "CHoCH_down" if want == "bear" else "CHoCH_up"
            _ci = next((e[0] for e in reversed(getattr(_se, "events", []) or []) if e[1] == _name), None)
            if _ci is None:
                steps["cfvg"] = "无逆势CHoCH(锚定缺失)"; return None
            if (n - 1 - _ci) > int(getattr(C, "CFVG_MAX_AGE_BARS", 8)):
                steps["cfvg"] = f"逆势CHoCH已过{n - 1 - _ci}根"; return None
        _lo_fvg = (_ci - 1) if _ci is not None else 0
        _cands = [f for f in (getattr(_le, "fvgs", []) or [])
                  if f.get("kind") == want and not f.get("filled")
                  and f.get("idx") is not None and int(f["idx"]) >= _lo_fvg]
        steps["cfvg_n"] = len(_cands)
        if not _cands:
            steps["cfvg"] = "无反向FVG"; return None
        _pick = str(getattr(C, "FVG_PICK", "nearest")).lower()
        if _pick == "exclude_newest" and len(_cands) > 1:
            _cands = _cands[:-1]
        elif _pick == "farthest" and _cands:
            _cands = _cands[:1]
        _N = int(getattr(C, "RETRACE_MAX_AGE_BARS", 4))
        _lo = max((_ci if _ci is not None else 0), n - 1 - _N)
        for _i in range(n - 1, _lo - 1, -1):
            _b = _cd[_i]
            _hit = [f for f in _cands if _b.low <= f["top"] and _b.high >= f["bottom"]]
            if not _hit:
                continue
            _f = _hit[-1]
            _li = int(_f["idx"]) - 1
            if not (0 <= _li < n):
                continue
            _lc = _cd[_li]
            px = _b.close
            if _dir == "long":
                sl = _lc.low * (1 - C.SL_BUFFER_PCT); risk = px - sl
            else:
                sl = _lc.high * (1 + C.SL_BUFFER_PCT); risk = sl - px
            if risk <= 0:
                continue
            if str(getattr(C, "TP_MODE", "pct")).lower() == "pct":
                _pp = float(getattr(C, "TP_PCT", 1.0)) / 100.0
                tp, _src = (px * (1 + _pp) if _dir == "long" else px * (1 - _pp)), "pct"
            else:
                _rr = float(C.TP_RR)
                tp, _src = (px + _rr * risk if _dir == "long" else px - _rr * risk), "rr"
            rr = abs(tp - px) / max(risk, 1e-9)
            steps["cfvg"] = {"dir": _dir, "choch_idx": _ci,
                             "fvg": (round(float(_f["bottom"]), 2), round(float(_f["top"]), 2)),
                             "tp_src": _src, "RR": round(rr, 2)}
            _rz = (f"{'▼' if _dir == 'short' else '▲'}反向FVG(反转) | 损{sl:.1f} 标{tp:.1f} "
                   f"(TP={_src} · RR1:{rr:.1f})")
            return EntrySignal(_dir, px, sl, tp, _rz, steps, "high" if rr >= 2 else "normal", 1)
        steps["cfvg"] = "未回踩反向FVG"; return None

    def _ifvg_signal(self, se, le, ltf_se, ltf_le, ltf_candles, htf_trend, steps):
        """★2026-10-06 按视频《IFVG的正确用法(BV1537DzfEq8)》: IFVG 反转入场
           事件来源 = ltf_le.ifvg_events (由 liquidity 记录"顺势FVG被反向实体收盘穿越")
           方向 = 反转方向; 入场 = 反转蜡烛实体 CE(0.5)/0.25; 止损 = 反转蜡烛极值外侧;
           止盈 = 未被扫掉的摆动极值(视频: 被清扫的原始盘整高/低点)
           三条件: ①左侧有同向清扫 ②留有未被扫掉的摆动极值 ③取最近那一根 IFVG
        """
        _le = ltf_le if ltf_le is not None else le
        _cd = ltf_candles
        if _le is None or not _cd:
            steps["ifvg"] = "无15m数据"; return None
        n = len(_cd)
        _age = int(getattr(C, "IFVG_MAX_AGE_BARS", 8))
        cand = [e for e in (getattr(_le, "ifvg_events", []) or [])
                if 0 <= (n - 1 - int(e["flip_idx"])) <= _age and int(e["flip_idx"]) <= n - 2]
        steps["ifvg_n"] = len(cand)
        if not cand:
            steps["ifvg"] = "无候选IFVG(近N根内)"; return None
        e = max(cand, key=lambda x: int(x["flip_idx"]))       # 条件③: 清扫段最后一根
        d = e["dir"]
        if getattr(C, "IFVG_REQUIRE_HTF_ALIGN", True) and \
           ((d == "bull" and htf_trend != "up") or (d == "bear" and htf_trend != "down")):
            steps["ifvg"] = f"反转方向{d}与1H({htf_trend})不一致"; return None
        fi = int(e["flip_idx"]); fc = _cd[fi]
        if getattr(C, "IFVG_REQUIRE_SWEEP", True):             # 条件①: 左侧须有同向清扫
            _w = int(getattr(C, "IFVG_SWEEP_WINDOW", 30))
            _want = "down" if d == "bull" else "up"
            if not any((s[1] == _want and 0 <= fi - int(s[0]) <= _w)
                       for s in (getattr(_le, "sweeps", []) or [])):
                steps["ifvg"] = "左侧无同向清扫(条件①不满足)"; return None
        for j in range(fi + 1, n):                             # 失效: 反转蜡烛极值被收盘破坏
            if d == "bull" and _cd[j].close < fc.low:
                steps["ifvg"] = "反转蜡烛低点已被收盘跌破(失效)"; return None
            if d == "bear" and _cd[j].close > fc.high:
                steps["ifvg"] = "反转蜡烛高点已被收盘突破(失效)"; return None
        px = _cd[n - 1].close
        sw = getattr(se, "swings", []) or []                   # 条件②+止盈: 未被扫掉的摆动极值
        if d == "bull":
            _t = [float(s[2]) for s in sw if s[1] == "H" and float(s[2]) > px]
            tp_liq = min(_t) if _t else None
        else:
            _t = [float(s[2]) for s in sw if s[1] == "L" and float(s[2]) < px]
            tp_liq = max(_t) if _t else None
        if tp_liq is None and getattr(C, "IFVG_REQUIRE_FAIL", True):
            steps["ifvg"] = "无未被扫掉的摆动极值(无止盈目标)"; return None
        _lvl = float(getattr(C, "IFVG_CE_LEVEL", 0.5))          # 入场: 回踩到反转蜡烛实体 CE
        ce = fc.open + _lvl * (fc.close - fc.open)
        bar = _cd[n - 1]
        if not (bar.low <= ce <= bar.high):
            steps["ifvg"] = f"未回踩到CE({ce:.2f})"; return None
        entry = ce
        if d == "bull":
            sl = fc.low * (1 - C.SL_BUFFER_PCT); risk = entry - sl
        else:
            sl = fc.high * (1 + C.SL_BUFFER_PCT); risk = sl - entry
        if risk <= 0:
            steps["ifvg"] = "几何无效(risk<=0)"; return None
        _tpm = str(getattr(C, "IFVG_TP_MODE", "liq")).lower()   # 止盈口径
        if _tpm == "liq" and tp_liq is not None:
            tp, _src = tp_liq, "liq"
        elif str(getattr(C, "TP_MODE", "pct")).lower() == "pct":
            _pp = float(getattr(C, "TP_PCT", 1.0)) / 100.0
            tp, _src = (entry * (1 + _pp) if d == "bull" else entry * (1 - _pp)), "pct"
        else:
            _rr = float(C.TP_RR)
            tp, _src = (entry + _rr * risk if d == "bull" else entry - _rr * risk), "rr"
        _rrx = abs(tp - entry) / max(risk, 1e-9)
        steps["ifvg"] = {"dir": d, "flip_idx": fi, "ce": round(ce, 2), "tp_src": _src, "RR": round(_rrx, 2)}
        _dir = "long" if d == "bull" else "short"
        _rz = (f"{'▲' if d == 'bull' else '▼'}IFVG反转(15m) | 损{sl:.1f} 标{tp:.1f} "
               f"(入场=反转蜡烛实体{int(_lvl * 100)}% · TP={_src} · RR1:{_rrx:.1f})")
        return EntrySignal(_dir, entry, sl, tp, _rz, steps, "high" if _rrx >= 2 else "normal", 1)

    def _evaluate_fvg(self, candles, se, le, htf_trend, bar_i=None, ltf_se=None, ltf_le=None, ltf_candles=None):
        """【FVG 回踩模型】返回 EntrySignal 或 None
        ★2026-10-04 用户裁定 "全部按A": 入场改为【1H BOS/CHoCH 定方向 + 15m 回踩 FVG 进场(一碰就进)】
        ★2026-10-05: 止损 = FVG 左侧那根K线极值外侧 ; 止盈 = 目标浮盈 TP_USD 美元(详见下方③)
        (旧"15m 同向 CHoCH 即入场"已停用)"""
        i = bar_i if bar_i is not None else len(candles) - 1
        steps = {}
        self.last_steps = steps   # ★诊断(2026-10-03): 同一个dict对象 → evaluate 返回 None 时,
                                  #   外部仍可读到"走到了哪一步"(判断本轮为何无信号), 只写日志不推送

        # ① 趋势 (规则A8: 必须顺大级别趋势; 趋势=结构方向, 见 main.get_htf_trend)
        steps["htf_trend"] = htf_trend
        if not htf_trend:
            return None

        # ============ 1H方向 + 15m FVG回踩 (2026-10-04 用户裁定 "全部按A") ============
        #   1H(背景) = 结构方向 BOS/CHoCH 定方向
        #   15m(入场) = 价格回踩进【顺势方向】FVG 即入场(一碰就进, 不等确认)
        #   止损 = FVG 左侧那根K线极值外侧 ; 止盈 = 目标浮盈 TP_USD 美元
        px = ltf_candles[-1].close if ltf_candles else candles[i].close
        _H = getattr(se, "last_swing_high", None)                 # (idx,'H',price)
        _L = getattr(se, "last_swing_low", None)
        # 斐波腿/50% 仅保留作信息展示, 不参与准入, 也不再做止损基准
        if _H and _L and _H[2] != _L[2]:
            leg_hi, leg_lo = max(_H[2], _L[2]), min(_H[2], _L[2])
            mid = (leg_hi + leg_lo) / 2.0
            steps["zone"] = {"high": round(leg_hi, 4), "low": round(leg_lo, 4),
                             "mid": round(mid, 4), "premium": bool(px >= mid)}
        # (可选门槛) 是否仍要求"扫到止损密集区" —— 默认关, 由 C.REQUIRE_SWEEP 控制
        if C.REQUIRE_SWEEP:
            _opp = ("BOS_down", "CHoCH_down") if htf_trend == "up" else ("BOS_up", "CHoCH_up")
            _seg = max([e[0] for e in se.events if e[1] in _opp], default=-1)
            _sd = [s for s in le.sweeps if s[0] > _seg
                   and ((htf_trend == "up" and s[1] == "down") or (htf_trend == "down" and s[1] == "up"))]
            steps["sweep"] = _sd
            if not _sd:
                return None

        # ③ ★2026-10-05 按笔记《FVG》+《BOS和CHOCH概念》重构: 结构与 FVG 合成【一条因果链】
        #   笔记《BOS和CHOCH概念》「实战配置逻辑」: Swing定方向 → Internal CHoCH(回调结束)
        #        → Internal BOS(延续确认) → 进场触发
        #   笔记《FVG》: ①先有 BOS/CHoCH → ②检查【产生该结构的推动浪里】有没有 FVG
        #        (没有 = 低质量突破, 直接忽略) → ③确认结构有效后【不追高, 等回调进该 FVG】入场
        #   ⇒ 旧版把"回踩FVG"与"结构确认"当两道独立门: 一个要求"价格此刻还在FVG里",
        #     一个要求"刚发生BOS", 两者时点互斥 → 近乎哑火。现改为同一条链:
        #     BOS 之后、最近 N 根内, 价格回调进【该段推动浪留下的 FVG】才进场。
        _evs = getattr(ltf_se, "events", []) or [] if ltf_se is not None else []
        _n = len(ltf_candles) if ltf_candles else 0
        _k = int(getattr(C, "INT_CONFIRM_MAX_AGE_BARS", 8))
        _N = int(getattr(C, "RETRACE_MAX_AGE_BARS", 4))
        _up = (htf_trend == "up")
        _same_bos = "BOS_up" if _up else "BOS_down"
        _opp_cho = "CHoCH_down" if _up else "CHoCH_up"
        _opp_bos = "BOS_down" if _up else "BOS_up"
        _ch_i = next((e[0] for e in reversed(_evs) if e[1] == _opp_cho), None)
        _bo_i = next((e[0] for e in reversed(_evs) if e[1] == _same_bos), None)
        _bo_age = None if _bo_i is None else (_n - 1 - _bo_i)
        # ---- 结构门 ----
        _ok, _why = True, ""
        if getattr(C, "INT_REQUIRE_BOS", False):
            if _bo_i is None:
                _ok, _why = False, "无顺势BOS"
            elif _bo_age > _k:
                _ok, _why = False, f"BOS已过{_bo_age}根(>{_k})"
            elif any(x > _bo_i for x in [e[0] for e in _evs if e[1] == _opp_bos]):
                _ok, _why = False, "BOS后出现反向BOS(结构已反转)"
            #  注: 反向 CHoCH 不再判否 —— 笔记要求"等回调进FVG", 而回调本身就会产生反向CHoCH
        if _ok and getattr(C, "INT_REQUIRE_CHOCH", False):
            if _ch_i is None:
                _ok, _why = False, "无逆势CHoCH(回调)"
            elif _bo_i is not None and _ch_i >= _bo_i:
                _ok, _why = False, "CHoCH晚于BOS(顺序不对)"
        steps["internal"] = {"choch_idx": _ch_i, "bos_idx": _bo_i, "age": _bo_age, "ok": _ok, "why": _why}
        if not _ok:
            return None

        # ---- FVG: 只认【产生该 BOS 的那段推动浪】里留下的顺势、未回填 FVG(笔记第2~3步) ----
        trigger, _fvg = None, None
        _cands = []
        if ltf_le is not None and ltf_candles and _bo_i is not None:
            _want = "bull" if _up else "bear"
            _leg_from = _ch_i if _ch_i is not None else 0
            _cands = [f for f in getattr(ltf_le, "fvgs", [])
                      if f.get("kind") == _want and not f.get("filled")
                      and f.get("idx") is not None
                      and _leg_from <= int(f["idx"]) <= (_bo_i + 1)]
            # ★2026-10-06 按视频《为什么你越用FVG胜率越低？》: 突破缺口不该等回踩 → 支持换取法
            _pick = str(getattr(C, "FVG_PICK", "nearest")).lower()
            if _pick == "exclude_newest" and len(_cands) > 1:
                _cands = _cands[:-1]
            elif _pick == "exclude_break":
                _cands = [f for f in _cands if int(f["idx"]) < _bo_i]
            elif _pick == "farthest" and _cands:
                _cands = _cands[:1]
            # ★② 剔除"假破形态"的 FVG(推动K线长影刺破后收回 / 次日实体反包)
            if getattr(C, "FVG_FAKEBREAK_FILTER", False) and _cands:
                _fr = float(getattr(C, "FVG_FAKE_WICK_RATIO", 1.0))
                _eng = bool(getattr(C, "FVG_FAKE_ENGULF", True))
                _keep = []
                for _f in _cands:
                    _j = int(_f["idx"])
                    if not (0 <= _j < len(ltf_candles)):
                        continue
                    _c2 = ltf_candles[_j]
                    _bd = max(abs(_c2.close - _c2.open), 1e-9)
                    if _want == "bull":
                        _fake = (_c2.high - max(_c2.open, _c2.close)) >= _fr * _bd
                        if not _fake and _eng and _j + 1 < len(ltf_candles):
                            _c3 = ltf_candles[_j + 1]
                            _fake = (_c3.close < _c3.open) and (_c3.open >= _c2.close) and (_c3.close <= _c2.open)
                    else:
                        _fake = (min(_c2.open, _c2.close) - _c2.low) >= _fr * _bd
                        if not _fake and _eng and _j + 1 < len(ltf_candles):
                            _c3 = ltf_candles[_j + 1]
                            _fake = (_c3.close > _c3.open) and (_c3.open <= _c2.close) and (_c3.close >= _c2.open)
                    if not _fake:
                        _keep.append(_f)
                steps["fvg_fake_dropped"] = len(_cands) - len(_keep)
                _cands = _keep
            steps["fvg_pick"] = {"mode": _pick, "n_cands": len(_cands)}
            # ---- 回踩: 必须发生在 BOS 之后, 且不早于最近 N 根(笔记第4步: 不追高, 等回调) ----
            # ★视频#2: Filled Gap(已被"实体"进入过的缺口) ≠ Tap Gap(仅影线穿刺) → 可选剔除
            _ff = bool(getattr(C, "FVG_FILLED_FILTER", False))
            _fm = str(getattr(C, "FVG_FILLED_MODE", "prior")).lower()
            _ff_dropped = 0
            _lo = max(_bo_i + 1, _n - 1 - _N)
            for _i in range(_n - 1, _lo - 1, -1):
                _bar = ltf_candles[_i]
                _hit = [f for f in _cands if _bar.low <= f["top"] and _bar.high >= f["bottom"]]
                if _ff and _hit:
                    _keep_hit = []
                    for _f in _hit:
                        _be = _f.get("body_entered_idx")
                        # None=从未被实体进入(最纯的 Tap Gap); > _i=实体在触发那根之后才进(仍算影线穿刺);
                        # == _i=触发那根本身带实体进入(仅 strict 模式判否)
                        if _be is None or _be > _i or (_be == _i and _fm != "strict"):
                            _keep_hit.append(_f)
                    _ff_dropped += len(_hit) - len(_keep_hit)
                    _hit = _keep_hit
                if _hit:
                    _fvg = _hit[-1]
                    _age = _n - 1 - _i
                    trigger = (f"15m 回踩{'▲' if _want == 'bull' else '▼'}FVG "
                               f"{_fvg['bottom']:.1f}~{_fvg['top']:.1f}"
                               f"（推动浪FVG · BOS后{_n - 1 - _bo_i - _age}根触及）")
                    steps["fvg"] = {"kind": _want, "bottom": round(_fvg["bottom"], 2),
                                    "top": round(_fvg["top"], 2),
                                    "born_idx": _fvg.get("born_idx") or _fvg.get("idx")}
                    steps["retrace_age"] = _age
                    break
            if _ff:
                steps["fvg_filled_dropped"] = _ff_dropped
            steps["leg_fvgs"] = len(_cands)
        steps["trigger"] = trigger
        if not trigger:
            return None

        # ④ 止损 = 形成这段缺口的【起点K线】(FVG 左侧那根)的极值 外侧 ; 止盈 = 目标浮盈金额
        #   ★2026-10-05 用户裁定: 止损不再挂 FVG 区间外沿, 改挂 "FVG 左侧那根K线"的极值 ——
        #     多头: 起点那根的最低价 × (1-buffer) ; 空头: 起点那根的最高价 × (1+buffer)
        _li = int(_fvg.get("idx", 0)) - 1                # 缺口左侧(起点)那根 15m K线
        if 0 <= _li < len(ltf_candles):
            _lc = ltf_candles[_li]
            if htf_trend == "up":
                sl = _lc.low * (1 - C.SL_BUFFER_PCT)
                risk = px - sl
            else:
                sl = _lc.high * (1 + C.SL_BUFFER_PCT)
                risk = sl - px
        else:                                            # 兜底: 退回 FVG 外沿
            if htf_trend == "up":
                sl = _fvg["bottom"] * (1 - C.SL_BUFFER_PCT)
                risk = px - sl
            else:
                sl = _fvg["top"] * (1 + C.SL_BUFFER_PCT)
                risk = sl - px
        # 几何有效性: 止损必须在价格正确一侧(价格已冲出 FVG 则该单无意义)
        if risk <= 0:
            steps["geometry_bad"] = round(risk, 4)
            return None
        # ③ 止盈: 口径由 C.TP_MODE 决定
        #   "liq"(★2026-10-06 用户裁定, 依笔记《FVG》"止盈第一目标 = 最近的前方流动性"):
        #        取 1H 上【前方最近的未突破摆动高点(做多)/摆动低点(做空)】; 取不到 → 退回 TP_RR
        #   "usd"(2026-10-05 旧口径) = 固定浮盈 TP_USD 美元 (名义 ≈ WEEX_MARGIN_USD × LEVERAGE_FIXED)
        #   "rr"  = 固定盈亏比
        _tpm = str(getattr(C, "TP_MODE", "rr")).lower()
        if _tpm in ("liq", "liq2r"):
            _lv = []
            for _s in (getattr(se, "swings", []) or []):
                try:
                    _kd = _s[1]
                    _pp = float(_s[2])
                except Exception:
                    continue
                if (htf_trend == "up" and _kd == "H" and _pp > px) or \
                   (htf_trend == "down" and _kd == "L" and _pp < px):
                    _lv.append(_pp)
            _rrx = float(C.TP_RR)
            _rr_tp = (px - _rrx * risk) if htf_trend == "down" else (px + _rrx * risk)
            _cand = (min(_lv) if htf_trend == "up" else max(_lv)) if _lv else None
            if _tpm == "liq2r":     # ★笔记"剩余仓位看向 2R 或更高的流动性目标" → 取更远的那一个
                if _cand is None:
                    tp, _src = _rr_tp, "fallback_rr"
                else:
                    tp = max(_cand, _rr_tp) if htf_trend == "up" else min(_cand, _rr_tp)
                    _src = "liq_or_2R"
            else:
                tp, _src = (_cand, "liquidity") if _cand is not None else (_rr_tp, "fallback_rr")
            rr = abs(tp - px) / max(abs(px - sl), 1e-9)
            _rz = (f"1H{htf_trend} | 现价{px:.1f} → {trigger} | 损{sl:.1f} 标{tp:.1f} "
                   f"(TP={_src}, RR1:{rr:.1f})")
            steps["tp_src"] = _src
        elif _tpm == "pct":
            # ★2026-10-06 用户裁定: 固定价格百分比(实测 90 天最优档)
            _pp = float(getattr(C, "TP_PCT", 1.0)) / 100.0
            tp = (px * (1 - _pp)) if htf_trend == "down" else (px * (1 + _pp))
            rr = abs(tp - px) / max(abs(px - sl), 1e-9)
            _rz = (f"1H{htf_trend} | 现价{px:.1f} → {trigger} | 损{sl:.1f} 标{tp:.1f} "
                   f"(固定{_pp * 100:.1f}%, RR1:{rr:.1f})")
            steps["tp_src"] = "pct"
        elif _tpm == "usd":
            _notional = float(C.WEEX_MARGIN_USD) * float(C.LEVERAGE_FIXED)
            _dist = float(C.TP_USD) * px / max(_notional, 1e-9)
            tp = (px - _dist) if htf_trend == "down" else (px + _dist)
            rr = abs(tp - px) / max(abs(px - sl), 1e-9)
            _rz = (f"1H{htf_trend} | 现价{px:.1f} → {trigger} | 损{sl:.1f} 标{tp:.1f} "
                   f"(浮盈{C.TP_USD:.0f}U, RR1:{rr:.1f})")
        else:
            rr = C.TP_RR
            tp = (px - rr * risk) if htf_trend == "down" else (px + rr * risk)
            _rz = f"1H{htf_trend} | 现价{px:.1f} → {trigger} | 损{sl:.1f} 标{tp:.1f} RR=1:{rr:.1f}"
        _dir = "long" if htf_trend == "up" else "short"
        return EntrySignal(_dir, px, sl, tp, _rz, steps, "high" if rr >= 2 else "normal", 0)

    # ---------- 模型2: 双蜡烛真假突破 (规则C3, CRT核心) ----------
    def double_candle_breakout(self, candles, i=None):
        """右侧K实体收过左侧高点=真突破(延续); 仅影线刺破收回=假突破(反转)"""
        i = i if i is not None else len(candles) - 1
        if i < 1: return None
        prev, cur = candles[i-1], candles[i]
        return {
            "true_break_up":   cur.close > prev.high,                    # 实体收过前高
            "false_break_up":  cur.high > prev.high and cur.close < prev.high,  # 影线刺破收回→看空
            "true_break_down": cur.close < prev.low,
            "false_break_down": cur.low < prev.low and cur.close > prev.low,    # 影线刺破收回→看多
        }

    # ---------- 模型3: MSS 双仓 (规则C5) ----------
    def mss_two_position(self, se, htf_trend):
        """MSS出现开第一仓(60%) → CHoCH(反转预警)出现后回踩补第二仓(40%)"""
        ms = [e for e in se.events[-30:] if "CHoCH" in e[1]]
        if not ms:
            return None
        first = ms[0]; second = ms[-1] if len(ms) > 1 else None
        return {
            "pos1_trigger": {"bar": first[0], "event": first[1], "size_ratio": C.MSS_TWO_POS_RATIO[0]},
            "pos2_trigger": {"bar": second[0], "event": second[1], "size_ratio": C.MSS_TWO_POS_RATIO[1]} if second else None,
            "note": "第一仓MSS进场, 第二仓CHoCH确认后回踩补",
        }

    # ---------- 模型4: 等待序列 (规则C13, 笨蛋钱集) ----------
    def waiting_sequence(self, candles, se, le, i=None):
        """关键位下破→等下截取→iFVG→回踩→拐头 → 进场条件清单"""
        i = i if i is not None else len(candles) - 1
        seq = {
            "1_break_level": any(e[1] == "BOS_down" for e in se.events[-20:]),
            "2_sweep":       any(s[1] == "down" and 0 <= i - s[0] <= 15 for s in le.sweeps),
            "3_ifvg":        any(e[1] == "iFVG_bull_flip" and 0 <= i - e[0] <= 15 for e in le.events),
            "4_retrace":     le.snapshot()["active_fvgs"] != [],
            "5_turn_up":     candles[i].close > candles[i].open,
        }
        seq["complete"] = all(seq[k] for k in ["1_break_level", "2_sweep", "3_ifvg", "4_retrace", "5_turn_up"])
        return seq
