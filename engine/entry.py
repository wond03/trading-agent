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
          止损 = FVG 远端外侧 ; 止盈 = 固定 1:2
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
        #   止损 = FVG 远端外侧 ; 止盈 = 固定盈亏比 TP_RR(1:2)
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

        # ③ 入场信号: 15m 回踩【顺势方向】FVG
        #   做多取最近未回填的 bull FVG ; 做空取最近未回填的 bear FVG
        #   触发 = 最新 15m K 线【触及】该 FVG 区间(一碰就进)
        trigger, _fvg = None, None
        if ltf_le is not None and ltf_candles:
            _want = "bull" if htf_trend == "up" else "bear"
            _cands = [f for f in getattr(ltf_le, "fvgs", [])
                      if f.get("kind") == _want and not f.get("filled")]
            _bar = ltf_candles[-1]
            _hit = [f for f in _cands if _bar.low <= f["top"] and _bar.high >= f["bottom"]]
            if _hit:
                _fvg = _hit[-1]                       # 最近的"被触及"FVG
                trigger = (f"15m 回踩{'▲' if _want == 'bull' else '▼'}FVG "
                           f"{_fvg['bottom']:.1f}~{_fvg['top']:.1f}")
                steps["fvg"] = {"kind": _want, "bottom": round(_fvg["bottom"], 2),
                                "top": round(_fvg["top"], 2), "born_idx": _fvg.get("born_idx")}
        steps["trigger"] = trigger
        if not trigger:
            return None

        # ④ 止损 = FVG 远端外侧(多: 下沿再下 / 空: 上沿再上) ; 止盈 = 固定盈亏比 TP_RR
        #   ★用户裁定 "全部按A": 止损改挂 FVG 外沿(不再用"最近 swing 极值" → 修掉止损贴脸)
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
        rr = C.TP_RR
        tp = (px - rr * risk) if htf_trend == "down" else (px + rr * risk)
        _dir = "long" if htf_trend == "up" else "short"
        _rz = f"1H{htf_trend} | 现价{px:.1f} → {trigger} | 损{sl:.1f} 标{tp:.1f} RR=1:{rr:.1f}"
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
