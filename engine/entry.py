# 暗夜猎手 (NightHunter) · 入场模板
# 入场模板 —— 森林查尔斯课程模块C实现
# 规则依据: C1-C20 (五步流程/双蜡烛真假突破/MSS双仓/斐波分批/等待序列/时段过滤)
import config as C

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
        """返回 EntrySignal 或 None
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
            # ---- 回踩: 必须发生在 BOS 之后, 且不早于最近 N 根(笔记第4步: 不追高, 等回调) ----
            _lo = max(_bo_i + 1, _n - 1 - _N)
            for _i in range(_n - 1, _lo - 1, -1):
                _bar = ltf_candles[_i]
                _hit = [f for f in _cands if _bar.low <= f["top"] and _bar.high >= f["bottom"]]
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
