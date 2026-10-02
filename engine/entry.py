# 暗夜猎手 (NightHunter) · 入场模板
# 入场模板 —— 森林查尔斯课程模块C实现
# 规则依据: C1-C20 (五步流程/双蜡烛真假突破/MSS双仓/斐波分批/等待序列/时段过滤)
import config as C

class EntrySignal:
    def __init__(self, direction, entry, sl, tp, reason, steps, confidence="normal", grade="A", sweep_pts=1):
        self.direction = direction   # 'long' / 'short'
        self.entry = entry
        self.sl = sl
        self.tp = tp
        self.reason = reason
        self.steps = steps           # 五步通过明细
        self.confidence = confidence # normal / high(多周期共振)
        self.grade = grade           # A级(双点截取+回踩FVG) / B级(单点或仅斐波回踩)
        self.sweep_pts = sweep_pts   # 截取扫过的点数

    def __repr__(self):
        rr = abs(self.tp - self.entry) / max(abs(self.entry - self.sl), 1e-9)
        return (f"[{self.direction.upper()}] entry={self.entry:.1f} SL={self.sl:.1f} TP={self.tp:.1f} "
                f"RR=1:{rr:.1f} | {self.reason}")

class EntryEngine:
    """五步流程状态机 (规则C1):
    ①大级别定趋势 ②下推一级找截取 ③切小级别看转势 ④等回踩FVG ⑤触发 → 开单
    总开关(规则C2): 无截取或无转 = 不开单"""

    def __init__(self):
        self.last_signal_bar = -99

    def evaluate(self, candles, se, le, htf_trend, bar_i=None, ltf_se=None, ltf_le=None, ltf_candles=None):
        """返回 EntrySignal 或 None
        课程原文流程(BV1H8cuzmEe5): ①大级别定趋势 ②下推一级找截取(1H需"双点") ③截取后(切小级别)看转
                                  ④转了等回踩(踩回FVG) ⑤回踩后切小级别再等转 → 开
        ★2026-10-02 按原文重建: 转势必须【晚于截取】(用时间比, 非根数); 双点=两根不同K线各扫一点"""
        i = bar_i if bar_i is not None else len(candles) - 1
        steps = {}

        # ① 趋势 (规则A8: 必须顺大级别趋势; 趋势=结构方向, 见 main.get_htf_trend)
        steps["htf_trend"] = htf_trend
        if not htf_trend:
            return None

        # ② 找截取 (规则C2: 无截取不开单; B5: 1H需双点)
        #    双点(原文 BV1w8cuzmEqw[104-105min]「一小时要双点…卡了就卡在一起了, 那种都不能算」)
        #    = 顺势方向上, 有 >=2 根【不同K线】各扫掉过一个点(不是"同一根K线扫2个点")
        #    ★2026-10-02 去掉根数时效, 改为"以结构为准": 只看【当前这一段】(= 上一次反向结构破坏之后)
        #      原文 BV1w8cuzmEcs[034min]「再截取的话…前面这两个就彻底失效了」→ 新结构出现, 旧截取作废
        _opp = ("BOS_down", "CHoCH_down") if htf_trend == "up" else ("BOS_up", "CHoCH_up")
        _seg = max([e[0] for e in se.events if e[1] in _opp], default=-1)   # 当前段起点(上次反向结构破坏)
        same_dir = [s for s in le.sweeps if s[0] > _seg
                    and ((htf_trend == "up" and s[1] == "down") or (htf_trend == "down" and s[1] == "up"))]
        if not same_dir:
            return None
        _bars_hit = sorted({s[0] for s in same_dir})            # 本段内发生过顺势截取的不同K线
        steps["sweep"] = same_dir
        if C.SWEEP_DOUBLE_POINT_H1 and len(_bars_hit) < 2:
            return None                                         # 1H 必须双点
        sweep = same_dir[-1]
        sweep_pts = len(_bars_hit)
        sweep_ts = candles[sweep[0]].ts                         # ★截取发生的时间(转势必须晚于它)

        # ③ 转势 (原文 BV1H8cuzmEe5[003/005min]「一小时找到拌饭或双点, 进五分钟看结构」「切小级别再等转」)
        #    → 转势在【小级别(15m)】看; 只认 CHoCH(BOS不算); 必须【晚于截取】
        #    ★2026-10-02 去掉根数时效: 只看【最近一次】CHoCH —— 结构最后转向哪, 就以哪为准
        turn_dir, turn_bar, turn_ts = None, None, None
        if ltf_se is not None and ltf_candles:
            _lx = [e for e in ltf_se.events if e[1] in ("CHoCH_up", "CHoCH_down")]
            if _lx:
                _last = _lx[-1]
                if 0 <= _last[0] < len(ltf_candles):
                    _t = ltf_candles[_last[0]].ts
                    if _t > sweep_ts:                           # 必须晚于截取
                        _d = "up" if _last[1] == "CHoCH_up" else "down"
                        if _d == htf_trend:
                            turn_dir, turn_bar, turn_ts = _d, _last[0], _t
        sweep_price = sweep[2]                     # 被扫的极端价
        steps["turn"] = turn_dir
        if not turn_dir:
            return None

        # ④ 等回踩 (原文 BV1w8cuzmEqw[061min]「一定要有 feg 的区域, 并且在转四位以内」;
        #            BV1w8cuzmErh[048min]「只要在里面, 引线上去什么的没所谓」)
        #    → 价格【首次】与顺势 FVG 区间发生交集(影线触及即可, 不要求收盘价); 且回踩不得破"转势起点"
        post_high = max(c.high for c in candles[sweep[0]:i+1])
        post_low = min(c.low for c in candles[sweep[0]:i+1])
        rng = post_high - post_low
        if rng <= 0:
            return None
        px = candles[i].close
        fib_levels = [post_high - rng * f for f in C.RETRACE_FIBS] if turn_dir == "up" \
                else [post_low + rng * f for f in C.RETRACE_FIBS]
        in_retrace = any(abs(px - lv) / rng < 0.25 for lv in fib_levels)
        _kind = "bull" if turn_dir == "up" else "bear"
        _fsrc = ltf_le if (ltf_le is not None and getattr(ltf_le, "fvgs", None)) else le
        _flist = [f for f in _fsrc.fvgs if f["kind"] == _kind]
        # 首次进入时间: 截取之后, 小级别K线【首次】与顺势FVG区间有交集(影线触及即可)
        retrace_ts = None
        _fvg_hit = None
        if _flist and ltf_candles:
            for c in ltf_candles:
                if c.ts <= sweep_ts:
                    continue
                _hit = next((f for f in _flist if f["bottom"] <= c.high and c.low <= f["top"]), None)
                if _hit:
                    retrace_ts, _fvg_hit = c.ts, _hit
                    break
        in_fvg = retrace_ts is not None
        steps["retrace"] = {"in_retrace": in_retrace, "in_fvg": in_fvg}
        # ★校准(2026-10-02 用户裁定): FVG 是入场的唯一必要条件 —— 没踩到FVG就不做
        if not in_fvg:
            return None
        # 回踩不得破"转势起点"(转势那根小级别K线的极值): 多单看低点 / 空单看高点
        if turn_bar is not None and ltf_candles and 0 <= turn_bar < len(ltf_candles):
            _tb = ltf_candles[turn_bar]
            if turn_dir == "up":
                if min(c.low for c in ltf_candles[turn_bar:]) < _tb.low:
                    return None
            else:
                if max(c.high for c in ltf_candles[turn_bar:]) > _tb.high:
                    return None

        # ⑤ 触发 (原文 BV1H8cuzmEe5[005min]「回踩之后切小级别, 切小级别再等转, 等转就开多了」)
        #    → 回踩到位【之后】小级别再出现的同向 CHoCH; 取不到小级别数据就不做(不再自创回退)
        trigger, strong = None, False
        if ltf_se is not None and ltf_candles:
            _lx = [e for e in ltf_se.events if e[1] in ("CHoCH_up", "CHoCH_down")]
            if _lx:
                _last = _lx[-1]                                 # 只看最近一次 CHoCH(去根数时效)
                if 0 <= _last[0] < len(ltf_candles):
                    _t = ltf_candles[_last[0]].ts
                    _d = "up" if _last[1] == "CHoCH_up" else "down"
                    if _t >= retrace_ts and _d == turn_dir:      # 必须晚于回踩 + 方向一致
                        trigger, strong = ("小级别转多" if _d == "up" else "小级别转空"), True
        steps["trigger"] = trigger
        if not trigger:
            return None

        # 生成信号 (2026-10-02 用户裁定): SL 挂【入场所用 FVG 的外沿】(不再用结构极值+ATR缓冲);
        #   TP 固定 1:2 (课程原文 BV1H8cuzmEbr[037min]「止盈的点位你就抓一比二」)
        if turn_dir == "up":
            sl = _fvg_hit["bottom"] if _fvg_hit else sweep_price
            risk = px - sl
            if risk <= 0:
                return None
            tp = px + risk * C.RR_MIN_GROWTH                  # 止盈 = 恰好 1:2
            rr = (tp - px) / risk
            conf = "high" if in_fvg and in_retrace else "normal"
            grade = "A" if (sweep_pts >= 2 and in_fvg and strong) else "B"
            return EntrySignal("long", px, sl, tp,
                               f"下截取@{sweep_price:.0f}({sweep[3]}) → 转多@{turn_bar} → 回踩 → {trigger} | RR=1:{rr:.1f}", steps, conf, grade, sweep_pts)
        else:
            sl = _fvg_hit["top"] if _fvg_hit else sweep_price
            risk = sl - px
            if risk <= 0:
                return None
            tp = px - risk * C.RR_MIN_GROWTH                  # 止盈 = 恰好 1:2
            rr = (px - tp) / risk
            conf = "high" if in_fvg and in_retrace else "normal"
            grade = "A" if (sweep_pts >= 2 and in_fvg and strong) else "B"
            return EntrySignal("short", px, sl, tp,
                               f"上截取@{sweep_price:.0f}({sweep[3]}) → 转空@{turn_bar} → 回踩 → {trigger} | RR=1:{rr:.1f}", steps, conf, grade, sweep_pts)

    # ---------- B级观察信号(埋伏提示: 截取+回踩到位, 不要求转势) ----------
    def __init_watch(self):
        if not hasattr(self, "_watch_seen"):
            self._watch_seen = set()

    def evaluate_watch(self, candles, se, le, htf_trend, bar_i=None):
        """B级机会观察: 已有顺势截取 + 价格回踩到位, 但转势尚未确认
        用途: 提前提示"机会在酝酿", 转势一旦出现即升级为A级信号"""
        self.__init_watch()
        i = bar_i if bar_i is not None else len(candles) - 1
        recent = [s for s in le.sweeps if 0 <= i - s[0] <= C.SWEEP_WINDOW]
        same = [s for s in recent if (htf_trend == "up" and s[1] == "down") or (htf_trend == "down" and s[1] == "up")]
        if not same:
            return None
        sweep = same[-1]
        # 若已出现顺势转势 → 归A级路径处理, 此处不报
        turns = [e for e in se.events if e[0] > sweep[0] and e[1] in ("CHoCH_up", "CHoCH_down", "BOS_up", "BOS_down")]
        if any((htf_trend == "up" and e[1] in ("CHoCH_up", "BOS_up")) or
               (htf_trend == "down" and e[1] in ("CHoCH_down", "BOS_down")) for e in turns):
            return None
        # 回踩到位判断
        post_high = max(c.high for c in candles[sweep[0]: i + 1])
        post_low = min(c.low for c in candles[sweep[0]: i + 1])
        rng = post_high - post_low
        if rng <= 0:
            return None
        px = candles[i].close
        fibs = ([post_high - rng * f for f in C.RETRACE_FIBS] if htf_trend == "up"
                else [post_low + rng * f for f in C.RETRACE_FIBS])
        in_retrace = any(abs(px - f) / rng < 0.25 for f in fibs)
        in_fvg = any((f["kind"] == ("bull" if htf_trend == "up" else "bear"))
                     and f["bottom"] <= px <= f["top"] for f in le.fvgs)
        if not in_fvg:
            return None
        fp = f"WATCH|{htf_trend}|{round(sweep[2] / 10) * 10}"
        if fp in self._watch_seen:
            return None
        self._watch_seen.add(fp)
        return {"type": "watch", "direction": htf_trend, "px": px,
                "sweep_level": sweep[2], "sweep_pts": sweep[3],
                "in_fvg": in_fvg, "in_retrace": in_retrace,
                "gap_bars": i - sweep[0]}

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
        """MSS出现开第一仓(60%) → CHoCH确认转势后回踩补第二仓(40%)"""
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
