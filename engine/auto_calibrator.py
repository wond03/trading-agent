# 暗夜猎手 (NightHunter) · 策略诊断引擎
# 策略诊断/阈值回标引擎 —— 自进化阶段①
# 输入: state["history"] (signal/exit记录, 含pnl)
# 输出: 胜率/期望/参数建议 (不自动改config, 生成建议供人工确认, 保护资金)
#
# ★2026-10-07 用户裁定: 只统计【现行模型上线之后】的平仓。
#   原因: history 里的成交横跨 OKX旧链模型 → 1H+15m → fvg_touch/fvg_handover → fvg_both 多个版本,
#   其中 10-02 那笔 +10.82U 的旧模型大单把均盈拉到 +2.21U, 得出"期望为正"的假象;
#   剔掉它后均盈只剩 +0.48U、盈亏平衡点 56% ⇒ 实际是负期望。
#   统计起点由 config.STATS_SINCE(北京时间) 给出; 每次实质性改模型后同步更新它。
import json, os, statistics, datetime

_TZ = datetime.timezone(datetime.timedelta(hours=8))


def _parse_since(since):
    """'YYYY-MM-DD HH:MM'(北京时间) → 时间戳; 空/异常 → 0.0(不过滤)"""
    if not since:
        return 0.0
    try:
        return datetime.datetime.strptime(str(since).strip(), "%Y-%m-%d %H:%M").replace(tzinfo=_TZ).timestamp()
    except Exception:
        return 0.0


def analyze(history, margin_per_trade=5.0, since=None):
    """返回诊断结果 dict
    since: 'YYYY-MM-DD HH:MM'(北京时间) —— 只统计此刻之后的平仓(现行模型样本); 缺省不过滤"""
    since_ts = _parse_since(since)
    window = f"现行模型(自{since})" if since else "全样本"

    def _in_window(h):
        try:
            return float(h.get("ts") or 0) >= since_ts
        except Exception:
            return False

    sigs = [h for h in history if h.get("type") == "signal" and _in_window(h)]
    # 只统计真实成交的平仓: "未成交·作废"记录(pnl=0)会拉低胜率、虚增样本
    exs = [h for h in history if h.get("type") == "exit"
           and not h.get("void") and "作废" not in (h.get("detail") or "")
           and _in_window(h)]
    n = len(exs)
    if n == 0:
        return {"ok": False, "window": window, "n": 0,
                "summary": f"{window} | 信号{len(sigs)}个, 尚无平仓样本(持仓中或未触发)",
                "brief": (f"现行模型尚无平仓样本(信号{len(sigs)}条)" if since
                          else f"尚无平仓样本(信号{len(sigs)}条)"),
                "advice": []}

    pnls = [h.get("pnl", 0) for h in exs]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / n
    avg_win = statistics.mean(wins) if wins else 0.0
    avg_loss = statistics.mean(losses) if losses else 0.0
    total = sum(pnls)
    # 盈亏平衡胜率 = |avg_loss| / (avg_win + |avg_loss|)
    be_wr = abs(avg_loss) / (avg_win + abs(avg_loss)) if (avg_win + abs(avg_loss)) > 0 else 1.0
    # 最大连亏
    streak = mx = 0
    for p in pnls:
        streak = streak + 1 if p <= 0 else 0
        mx = max(mx, streak)

    # 一行结论(日报用, 2026-10-03; 2026-10-07 起带"现行模型"字样)
    _pfx = "现行模型" if since else ""
    if wr >= be_wr:
        brief = f"{_pfx}{n}笔 · 期望为正(胜率{wr:.0%}≥{be_wr:.0%})"
    else:
        brief = f"{_pfx}{n}笔 · 期望为负(胜率{wr:.0%}<{be_wr:.0%}) · 建议降杠杆/放宽止损"
    if n < 10:
        brief += f" · 样本偏少,再攒{10 - n}笔"

    advice = []
    if since:
        advice.append(f"📅 统计窗口: 只含 {since}(北京) 之后的平仓 —— 旧模型成交已剔除")
    if n < 10:
        advice.append(f"⚠️ 样本 {n} 笔, 统计不显著 — 继续积累到 10 笔以上再行动")
    if wr >= be_wr:
        advice.append(f"✅ 期望为正 (胜率{wr:.0%} ≥ 平衡点{be_wr:.0%}) — 维持当前参数")
    else:
        advice.append(f"🔴 期望为负 (胜率{wr:.0%} < 平衡点{be_wr:.0%}) — 建议: ①暂停自动交易 ②降杠杆放宽止损")
    if n >= 5 and len(losses) / n > 0.8:
        advice.append(f"💡 止损率{len(losses) / n:.0%}过高: 止损距离仅0.2%(100倍限制) → 考虑杠杆降至20倍(止损放宽至1.5%)")
    if mx >= 4:
        advice.append(f"⚠️ 出现过 {mx} 连亏 → 建议加入『连亏3次自动暂停当日交易』保护")
    if n >= 10 and total < 0 and wr > be_wr:
        advice.append("💡 胜率达标但总亏 → 检查是否有单笔异常亏损(滑点/爆仓)")

    summary = (f"{window} | 样本{n}笔 | 胜率{wr:.0%} | 平衡点{be_wr:.0%} | "
               f"均盈{avg_win:+.1f}U 均亏{avg_loss:+.1f}U | 累计{total:+.1f}U | 最大连亏{mx}")
    return {"ok": True, "window": window, "n": n, "wr": wr, "be_wr": be_wr, "total": total,
            "avg_win": avg_win, "avg_loss": avg_loss, "max_loss_streak": mx,
            "summary": summary, "brief": brief, "advice": advice}


def weekly_report(state, since=None):
    """周报格式(供企微推送)"""
    d = analyze(state.get("history", []), since=since)
    lines = ["**🔬 策略诊断报告**", ""]
    lines.append(d["summary"])
    if d["advice"]:
        lines.append("")
        lines.extend(d["advice"])
    return "\n".join(lines)


if __name__ == "__main__":
    # 本地测试
    st = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")))
    try:
        import config as C
        _s = getattr(C, "STATS_SINCE", None)
    except Exception:
        _s = None
    print(weekly_report(st, since=_s))
