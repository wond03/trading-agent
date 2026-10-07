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

    def evaluate(self, candles, se, le, htf_trend, bar_i=None, ltf_se=None, ltf_le=None, ltf_candles=None,
                 htf_swings=None):
        """★2026-10-08 精简（用户裁定"旧的代码全清理"）: 只剩现行模型 fvg_both。
        已删除的旧模型: 四步链 / fvg_touch / fvg_handover / IFVG 反转 / 反向FVG 补位。
        htf_swings: 大周期(1H/4H)摆动极值池, 供止盈"打结构位"用(None 则退回 15m/±1%)。"""
        steps = {}
        self.last_steps = steps
        return self._fvg_both_signal(se, le, ltf_se, ltf_le, ltf_candles, steps, htf_swings=htf_swings)
    def _resolve_tp(self, d, px, risk, ltf_se, htf_swings=None):
        """止盈口径统一出口(★2026-10-07 用户要求: 止盈改"打结构位")
           "pct"    = 固定百分比(±TP_PCT%)
           "struct" = 结构位: 多单打到【上方最近的已确认摆动高点】, 空单打到【下方最近的摆动低点】;
                      ★大周期优先(2026-10-07 用户裁定"用 1~4 小时的结构位"):
                        用传入的 htf_swings(1H/4H 摆动极值池)取【最近且距入场 ≥ TP_STRUCT_MIN_PCT%】的那个;
                        大周期取不到 → 退回 15m 摆动点; 都没有 → 退回 pct。
           "rr"     = 按 R 倍数
        """
        mode = str(getattr(C, "TP_MODE", "pct")).lower()
        _pp = float(getattr(C, "TP_PCT", 1.0)) / 100.0
        if mode == "struct":
            _mp = float(getattr(C, "TP_STRUCT_MIN_PCT", 0.5)) / 100.0
            # ★2026-10-08: 可选「目标至少要够得着风险」= TP_STRUCT_MIN_RR × 止损距离(默认 0=关)
            _rr_min = float(getattr(C, "TP_STRUCT_MIN_RR", 0.0) or 0.0)
            if _rr_min > 0 and px:
                _mp = max(_mp, _rr_min * abs(float(risk)) / float(px))
            _pool = list(htf_swings or [])
            _src = "struct(大周期)"
            if not _pool:                                  # 大周期没给/取不到 → 退回 15m 摆动点
                _pool = list(getattr(ltf_se, "swings", []) or [])
                _src = "struct(15m)"
            if d == "long":
                _c = [x[2] for x in _pool if x[1] == "H" and x[2] > px * (1 + _mp)]
                if _c:
                    return min(_c), _src
            else:
                _c = [x[2] for x in _pool if x[1] == "L" and x[2] < px * (1 - _mp)]
                if _c:
                    return max(_c), _src
            return (px * (1 + _pp) if d == "long" else px * (1 - _pp)), "pct(退回)"
        if mode == "rr":
            _rr = float(C.TP_RR)
            return (px + _rr * risk if d == "long" else px - _rr * risk), "rr"
        return (px * (1 + _pp) if d == "long" else px * (1 - _pp)), "pct"


    def _fvg_both_signal(self, se, le, ltf_se, ltf_le, ltf_candles, steps, htf_swings=None):
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
            # ★2026-10-07 用户裁定「信号保留 2~3 根」: 本根【或最近 K 根内】的首次探进都算 ——
            #   某轮漏跑(超时/节流/引擎未跑到)也不至于把这条信号丢掉;
            #   进场价仍取【首次探进那根】的收盘(保留期内不变 → 同一条信号不会变形)。
            _K = max(1, int(getattr(C, "FVGB_KEEP_BARS", 3)))
            _tb = None
            for _b in range(max(_fi + 1, (n - 1) - _K + 1), n):
                if _pen(_cd[_b], f):
                    _tb = _b; break
            if _tb is None:
                continue                                          # 最近 K 根内未探进缺口
            if any(_pen(_cd[k], f) for k in range(_fi + 1, _tb)):
                continue                                          # 更早之前已探进过 → 非"首次回踩"
            _bar = _cd[_tb]
            # ★用户理由②: 回踩必须是【影线】探进缺口, 实体压进缺口 = 真卖/买压 → 不做
            if getattr(C, "FVGB_WICK_ONLY", True):
                _bl, _bh = min(_bar.open, _bar.close), max(_bar.open, _bar.close)
                if f["kind"] == "bull" and _bl <= float(f["top"]):
                    continue
                if f["kind"] == "bear" and _bh >= float(f["bottom"]):
                    continue
            # ★用户理由①: 入场前出现"长上影"(多)/"长下影"(空) = 被拒绝 → 不做(只看到入场那根为止)
            if getattr(C, "FVGB_REJECT_LONG_WICK", True):
                _r = float(getattr(C, "FVGB_WICK_RATIO", 1.5))
                _mp = float(getattr(C, "FVGB_WICK_MIN_PCT", 0.08)) / 100.0
                _bad = False
                for k in range(_fi + 1, _tb + 1):
                    b = _cd[k]
                    _th = max(_r * abs(b.close - b.open), _mp * b.close)
                    if f["kind"] == "bull" and (b.high - max(b.open, b.close)) >= _th:
                        _bad = True; break
                    if f["kind"] == "bear" and (min(b.open, b.close) - b.low) >= _th:
                        _bad = True; break
                if _bad:
                    continue
            hit.append((f, _bar))
        steps["fvgb_n"] = len(hit)
        if not hit:
            steps["fvgb"] = "两侧均无新回踩(无既活着又被探进的缺口)"; return None
        f, bar = sorted(hit, key=lambda x: int(x[0]["idx"]))[-1]
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
        tp, _src = self._resolve_tp(d, px, risk, _se, htf_swings=htf_swings)
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
