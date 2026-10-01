# 暗夜猎手 (NightHunter) · 入场模板
# 入场模板 —— 森林查尔斯课程模块C实现
# 规则依据: C1-C20 (五步流程/双蜡烛真假突破/MSS双仓/斐波分批/等待序列/时段过滤)
import config as C
from structure import atr

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
    ①HTF定趋势 ②下推一级找截取 ③截取后看转势 ④等回踩 ⑤回踩中触发 → 开单
    总开关(规则C2): 无截取或无转 = 不开单"""

    def __init__(self):
        self.last_signal_bar = -99

    def evaluate(self, candles, se, le, htf_trend, bar_i=None):
        """返回 EntrySignal 或 None"""
        i = bar_i if bar_i is not None else len(candles) - 1
        a = atr(candles)
        steps = {}

        # ① HTF趋势 (规则A8: 信号必须与大级别同向)
        steps["htf_trend"] = htf_trend
        if not htf_trend:
            return None

        # ② 找截取 (规则C2: 无截取不开单; B5: 1H需双点)
        recent_sweeps = [s for s in le.sweeps if 0 <= i - s[0] <= 20]
        valid_sweeps = []
        for s in recent_sweeps:
            is_double = (s[3] >= 2) if isinstance(s[3], int) else False
            # sweep方向 vs 趋势方向: 顺势的截取 = 扫对侧流动性
            if htf_trend == "up" and s[1] == "down":      # 上升趋势中的下截取 = 扫下方流动性(多单机会)
                if is_double or not C.SWEEP_DOUBLE_POINT_H1:
                    valid_sweeps.append(s)
            if htf_trend == "down" and s[1] == "up":      # 下降趋势中的上截取
                if is_double or not C.SWEEP_DOUBLE_POINT_H1:
                    valid_sweeps.append(s)
        steps["sweep"] = valid_sweeps
        if not valid_sweeps:
            return None
        sweep = valid_sweeps[-1]
        sweep_pts = sweep[3] if isinstance(sweep[3], int) else 1

        # ③ 转势确认 (规则C2/C13: 截取后必须出现转势)
        turn_events = [e for e in se.events if e[0] > sweep[0] and e[1] in ("CHoCH_up", "CHoCH_down", "BOS_up", "BOS_down")]
        turn_dir = None
        for e in turn_events:
            if htf_trend == "up" and e[1] in ("CHoCH_up", "BOS_up"):
                turn_dir = "up"; turn_bar = e[0]; break
            if htf_trend == "down" and e[1] in ("CHoCH_down", "BOS_down"):
                turn_dir = "down"; turn_bar = e[0]; break
        steps["turn"] = turn_dir
        if not turn_dir:
            return None

        # ④ 等回踩 (规则C6: 回踩到 FVG 或 斐波0.382-0.618 区间)
        sweep_price = sweep[2]                     # 被扫的极端价
        post_high = max(c.high for c in candles[sweep[0]:i+1])
        post_low = min(c.low for c in candles[sweep[0]:i+1])
        rng = post_high - post_low
        if rng <= 0:
            return None
        fib_levels = [post_high - rng * f for f in C.RETRACE_FIBS] if turn_dir == "up" \
                else [post_low + rng * f for f in C.RETRACE_FIBS]
        px = candles[i].close
        in_retrace = any(abs(px - lv) / rng < 0.25 for lv in fib_levels)
        # FVG 回踩检查
        in_fvg = any(f["kind"] == ("bull" if turn_dir == "up" else "bear")
                     and f["bottom"] <= px <= f["top"] for f in le.fvgs)
        steps["retrace"] = {"in_retrace": in_retrace, "in_fvg": in_fvg}
        if not (in_retrace or in_fvg):
            return None

        # ⑤ 触发确认 (规则C13: 回踩中拐头/再截取/出量 任一即触发)
        bar = candles[i]
        trigger = None
        if turn_dir == "up":
            if bar.close > bar.open: trigger = "回踩收阳"
            elif bar.low < candles[i-1].low and bar.close > candles[i-1].close: trigger = "下刺回收(猎取)"
        else:
            if bar.close < bar.open: trigger = "回踩收阴"
            elif bar.high > candles[i-1].high and bar.close < candles[i-1].close: trigger = "上刺回收(猎取)"
        # 出量确认(规则C17)
        vols = [c.vol for c in candles[-21:-1]]
        if sum(vols) > 0 and bar.vol > (sum(vols)/len(vols)) * C.VOLUME_SPIKE_MULT:
            trigger = trigger or "放量触发"
        steps["trigger"] = trigger
        if not trigger:
            return None

        if i - self.last_signal_bar < 5:   # 信号去重: 5根内不重复报
            return None
        self.last_signal_bar = i

        # 生成信号: SL在截取极值外+缓冲(规则F3); TP=斐波扩展目标(规则C7) 且至少满足RR门槛(规则E12)
        if turn_dir == "up":
            sl = sweep_price - a * C.SL_BUFFER_ATR
            risk = px - sl
            fib_rng = post_high - sweep_price                 # 反弹段长度
            tp_ext = sweep_price + fib_rng * 1.272            # 斐波1.272扩展(规则C7)
            tp_min = px + risk * C.RR_MIN_GROWTH              # RR门槛兜底(规则E12)
            tp = max(tp_ext, tp_min)
            rr = (tp - px) / max(risk, 1e-9)
            if rr < C.RR_MIN_GROWTH:
                return None
            conf = "high" if in_fvg and in_retrace else "normal"
            grade = "A" if (sweep_pts >= 2 and in_fvg) else "B"
            return EntrySignal("long", px, sl, tp,
                               f"下截取@{sweep_price:.0f}({sweep[3]}) → 转多@{turn_bar} → 回踩 → {trigger} | RR=1:{rr:.1f}", steps, conf, grade, sweep_pts)
        else:
            sl = sweep_price + a * C.SL_BUFFER_ATR
            risk = sl - px
            fib_rng = sweep_price - post_low
            tp_ext = sweep_price - fib_rng * 1.272
            tp_min = px - risk * C.RR_MIN_GROWTH
            tp = min(tp_ext, tp_min)
            rr = (px - tp) / max(risk, 1e-9)
            if rr < C.RR_MIN_GROWTH:
                return None
            conf = "high" if in_fvg and in_retrace else "normal"
            grade = "A" if (sweep_pts >= 2 and in_fvg) else "B"
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
        recent = [s for s in le.sweeps if 0 <= i - s[0] <= 20]
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
        if not (in_retrace or in_fvg):
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
