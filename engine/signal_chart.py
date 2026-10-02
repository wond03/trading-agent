# 暗夜猎手 · 推送用信号标注图
# 两联图: 上=1H(结构/截取/BOS/CHoCH)  下=15m(转势CHoCH + FVG回踩区)
# 并画出该笔的 进场/止损/止盈/离场 水平线
# ★容错原则(2026-10-03): 任何异常只打印并返回 None, **绝不允许影响交易主流程**
import datetime

CST = datetime.timezone(datetime.timedelta(hours=8))


def _dt(ts):
    """★2026-10-03: 兼容毫秒与秒两种时间戳(OKX=毫秒 / Gate=秒), 否则 fromtimestamp 会报 year out of range"""
    v = float(ts)
    if v > 1_000_000_000_000:
        v /= 1000.0
    return datetime.datetime.fromtimestamp(v, CST)


def render(inst_id, bars_main, bars_ltf, se, le, s15, l15, lines, out_path,
           title="", main_tf="1H", ltf_tf="15m", main_n=72, ltf_n=96):
    """lines: [(价格, 标签, 颜色hex)]  例如 [(进场,'#1f6feb'), ...]
    返回 out_path；失败返回 None"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.patches import Rectangle
    except Exception as e:
        print(f"[画图] matplotlib 不可用: {e}")
        return None
    try:
        plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "Noto Sans SC",
                                           "WenQuanYi Zen Hei", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        num = mdates.date2num

        def X(ts):
            return num(_dt(ts).replace(tzinfo=None))

        M = list(bars_main)[-main_n:]
        L = list(bars_ltf)[-ltf_n:]
        if len(M) < 5 or len(L) < 5:
            print("[画图] K线太少, 跳过")
            return None

        nm = {"BTC": "BTC", "XAU": "黄金"}.get(inst_id.split("-")[0], inst_id.split("-")[0])
        fig = plt.figure(figsize=(13, 9.6), dpi=110)
        gs = fig.add_gridspec(2, 1, height_ratios=[3, 2], hspace=0.16)
        ax1 = fig.add_subplot(gs[0]); ax2 = fig.add_subplot(gs[1])

        def draw(ax, bars, w):
            for b in bars:
                col = "#26a69a" if b.close >= b.open else "#ef5350"
                x = X(b.ts)
                ax.vlines(x, b.low, b.high, color=col, lw=0.8, zorder=3)
                lo, hi = min(b.open, b.close), max(b.open, b.close)
                ax.add_patch(Rectangle((x - w / 2, lo), w, max(hi - lo, 1e-9),
                                       facecolor=col, edgecolor=col, lw=0.4, zorder=4))

        def inwin(t, bars):
            return bars[0].ts <= t <= bars[-1].ts

        # ---------- 上: 主周期(1H) ----------
        draw(ax1, M, 0.62 / 24)
        ax1.set_title(f"{nm} · {main_tf}   {title}", fontsize=13, pad=10)
        # ★防重叠(2026-10-03): 只在可见窗口内取"最近若干个"事件, 并交错偏移, 避免标签堆成一团
        sw = [s for s in getattr(se, "swings", [])
              if 0 <= s[0] < len(bars_main) and inwin(bars_main[s[0]].ts, M)][-12:]
        for s in sw:
            up = s[1] == "H"
            ax1.annotate(f"{'H' if up else 'L'} {s[2]:,.0f}", (X(bars_main[s[0]].ts), s[2]),
                         textcoords="offset points", xytext=(0, 6 if up else -12), ha="center",
                         fontsize=7.5, color="#0b6b5e" if up else "#8e2f2a")
            ax1.scatter([X(bars_main[s[0]].ts)], [s[2]], s=18, marker="v" if up else "^",
                        color="#0b6b5e" if up else "#8e2f2a", zorder=6)
        sp = [s for s in getattr(le, "sweeps", [])
              if 0 <= s[0] < len(bars_main) and inwin(bars_main[s[0]].ts, M)][-14:]
        for s in sp:                                  # 截取(影线扫流动性)
            b = bars_main[s[0]]
            ax1.scatter([X(b.ts)], [b.high if s[1] == "up" else b.low], s=34, marker="x",
                        color="#c77700", zorder=7, linewidths=1.4)
        ev = [e for e in getattr(se, "events", [])
              if e[1] in ("BOS_up", "CHoCH_up", "BOS_down", "CHoCH_down")
              and 0 <= e[0] < len(bars_main) and inwin(bars_main[e[0]].ts, M)][-8:]
        for k, e in enumerate(ev):                    # BOS / CHoCH (交错高度防重叠)
            up = e[1].endswith("up")
            dy = (18 if up else -22) + (11 if k % 2 else 0) * (1 if up else -1)
            ax1.annotate(e[1], (X(bars_main[e[0]].ts), e[2]), textcoords="offset points",
                         xytext=(0, dy), ha="center", fontsize=8,
                         fontweight="bold", color="#0b6b5e" if up else "#8e2f2a")

        # ---------- 下: 小周期(15m) ----------
        draw(ax2, L, 0.62 / 96)
        ax2.set_title(f"{nm} · {ltf_tf}   转势 CHoCH ＋ FVG(回踩区)", fontsize=12, pad=8)
        for f in getattr(l15, "fvgs", []):
            if 0 <= f["idx"] < len(bars_ltf) and inwin(bars_ltf[f["idx"]].ts, L):
                col = "#26a69a" if f["kind"] == "bull" else "#ef5350"
                x = X(bars_ltf[f["idx"]].ts)
                ax2.add_patch(Rectangle((x, f["bottom"]), X(L[-1].ts) - x,
                                        max(f["top"] - f["bottom"], 1e-9),
                                        facecolor=col, alpha=0.16, zorder=1))
        for e in getattr(s15, "events", []):
            if e[1] in ("CHoCH_up", "CHoCH_down") and 0 <= e[0] < len(bars_ltf) \
               and inwin(bars_ltf[e[0]].ts, L):
                up = e[1].endswith("up")
                ax2.annotate("转" + ("多" if up else "空"), (X(bars_ltf[e[0]].ts), e[2]),
                             textcoords="offset points", xytext=(0, 18 if up else -24), ha="center",
                             fontsize=8.5, fontweight="bold", color="#0b6b5e" if up else "#8e2f2a")

        # ---------- 水平线: 进场/止损/止盈 ----------
        for ax, bars in ((ax1, M), (ax2, L)):
            ax.grid(alpha=0.22)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=6 if ax is ax1 else 3))
            ax.set_ylabel("价格")
            lo = min(b.low for b in bars); hi = max(b.high for b in bars)
            xl = ax.get_xlim()[0]
            for (px, lab, col) in lines:
                ax.axhline(px, ls="--", lw=1.9, color=col, alpha=1.0, zorder=5)
                ax.text(xl, px, f" {lab} {px:,.1f}", color=col, fontsize=10,
                        fontweight="bold", va="bottom", ha="left", zorder=8,
                        bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                  edgecolor="none", alpha=0.75))
                lo = min(lo, px); hi = max(hi, px)
            pad = (hi - lo) * 0.07 or 1
            ax.set_ylim(lo - pad, hi + pad)

        fig.savefig(out_path, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print(f"[画图] 已生成 {out_path}")
        return out_path
    except Exception as e:
        print(f"[画图] 渲染异常: {type(e).__name__} {e}")
        return None
