# 暗夜猎手 (NightHunter) · 策略诊断引擎
# 策略诊断/阈值回标引擎 —— 自进化阶段①
# 输入: state["history"] (signal/exit记录, 含pnl)
# 输出: 胜率/期望/参数建议 (不自动改config, 生成建议供人工确认, 保护资金)
import json, os, statistics

def analyze(history, margin_per_trade=5.0):
    """返回诊断结果 dict"""
    sigs = [h for h in history if h.get("type") == "signal"]
    exs = [h for h in history if h.get("type") == "exit"]
    n = len(exs)
    if n == 0:
        return {"ok": False, "summary": f"信号{len(sigs)}个, 尚无平仓样本(持仓中或未触发)",
                "brief": f"尚无平仓样本(信号{len(sigs)}条)", "advice": []}

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

    # 一行结论(日报用, 2026-10-03)
    if wr >= be_wr:
        brief = f"{n}笔 · 期望为正(胜率{wr:.0%}≥{be_wr:.0%})"
    else:
        brief = f"{n}笔 · 期望为负(胜率{wr:.0%}<{be_wr:.0%}) · 建议降杠杆/放宽止损"
    if n < 10:
        brief += f" · 样本偏少,再攒{10-n}笔"

    advice = []
    if n < 10:
        advice.append(f"⚠️ 样本 {n} 笔, 统计不显著 — 继续积累到 10 笔以上再行动")
    if wr >= be_wr:
        advice.append(f"✅ 期望为正 (胜率{wr:.0%} ≥ 平衡点{be_wr:.0%}) — 维持当前参数")
    else:
        advice.append(f"🔴 期望为负 (胜率{wr:.0%} < 平衡点{be_wr:.0%}) — 建议: ①暂停自动交易 ②降杠杆放宽止损")
    if n >= 5 and len(losses) / n > 0.8:
        advice.append(f"💡 止损率{len(losses)/n:.0%}过高: 止损距离仅0.2%(100倍限制) → 考虑杠杆降至20倍(止损放宽至1.5%)")
    if mx >= 4:
        advice.append(f"⚠️ 出现过 {mx} 连亏 → 建议加入『连亏3次自动暂停当日交易』保护")
    if n >= 10 and total < 0 and wr > be_wr:
        advice.append("💡 胜率达标但总亏 → 检查是否有单笔异常亏损(滑点/爆仓)")

    summary = (f"样本{n}笔 | 胜率{wr:.0%} | 平衡点{be_wr:.0%} | "
               f"均盈{avg_win:+.1f}U 均亏{avg_loss:+.1f}U | 累计{total:+.1f}U | 最大连亏{mx}")
    return {"ok": True, "n": n, "wr": wr, "be_wr": be_wr, "total": total,
            "avg_win": avg_win, "avg_loss": avg_loss, "max_loss_streak": mx,
            "summary": summary, "brief": brief, "advice": advice}

def weekly_report(state):
    """周报格式(供企微推送)"""
    d = analyze(state.get("history", []))
    lines = ["**🔬 策略诊断报告**", ""]
    lines.append(d["summary"])
    if d["advice"]:
        lines.append("")
        lines.extend(d["advice"])
    return "\n".join(lines)

if __name__ == "__main__":
    # 本地测试
    st = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")))
    print(weekly_report(st))
