# 暗夜猎手 (NightHunter) · 风控与仓位
# 风控层 —— 森林查尔斯课程模块E1/F实现
# 2026-10-02 清理: 删除未接线的死代码(杠杆公式/1%风险仓位/滚仓 PyramidingManager)
#   实际下单走【固定保证金 × 固定杠杆】(用户指定), 见下方 size_fixed_margin
import config as C

class RiskManager:
    """开单前的门 (规则F1: 五条件严格AND, 缺一不做)"""

    def __init__(self, capital_usd=10000.0, risk_score=3):
        self.capital = capital_usd
        self.risk_score = max(0, min(3, risk_score))
        self.daily_trades = 0
        self.trade_log = []

    # ---------- 五条件 AND 门 (规则F1) ----------
    def check_gates(self, signal, all_conditions=None):
        """返回 (通过: bool, 明细: list[str])
        ★2026-10-07 修正: 按【当前信号模型】取条件。
           旧代码固定读 steps["htf_trend"] / ["trigger"](都是旧四步链的键), 换到 fvg_touch /
           fvg_handover 之后这两个键根本不存在 → 恒判 ❌ → **每一个真信号都被误报成
           "信号被风控拦截"**, 而且因为走了拦截分支, 信号本身(进场/止损/目标)还推不出来。"""
        detail, ok = [], True
        s = signal.steps
        mode = str(getattr(C, "SIGNAL_MODE", "chain")).lower()
        if mode == "fvg_handover":
            _d = s.get("fvgh") if isinstance(s.get("fvgh"), dict) else {}
            cond = {
                "①缺口交接(反向缺口被实体收盘打掉)": bool(_d.get("handover")),
                "②回踩顺势缺口": bool(_d.get("fvg")),
                "③止损/止盈已算出": bool(_d.get("sl")) and bool(_d.get("tp")),
            }
        elif mode == "fvg_touch":
            _d = s.get("fvgt") if isinstance(s.get("fvgt"), dict) else {}
            cond = {
                "①15m FVG回踩": bool(_d.get("fvg")),
                "②止损/止盈已算出": bool(_d.get("sl")) and bool(_d.get("tp")),
            }
        elif mode == "fvg_both":
            _d = s.get("fvgb") if isinstance(s.get("fvgb"), dict) else {}
            cond = {
                "①回踩进缺口(两侧独立)": bool(_d.get("fvg")),
                "②止损=本段结构极值": bool(_d.get("sl")) and bool(_d.get("stop_src")),
                "③止盈已算出": bool(_d.get("tp")),
            }
        else:
            # ★兜底(2026-10-07 补): 任何"新模型"的 steps(带 fvgb/fvgh/fvgt 字典)都不该去读旧四步链的键。
            #   教训: 只按 SIGNAL_MODE 白名单判断, 新加一个模式忘了登记 → 又掉回旧分支 → 全部误报。
            _nd = next((s[k] for k in ("fvgb", "fvgh", "fvgt") if isinstance(s.get(k), dict)), None)
            if _nd is not None:
                cond = {
                    "①回踩形态成立": bool(_nd.get("fvg")),
                    "②止损/止盈已算出": bool(_nd.get("sl")) and bool(_nd.get("tp")),
                }
            else:
                cond = {
                    "①背景方向": bool(s.get("htf_trend")),
                    "②15m FVG回踩入场": bool(s.get("trigger")),
                }
        if all_conditions:
            cond.update(all_conditions)
        for k, v in cond.items():
            detail.append(f"{'✅' if v else '❌'}{k}")
            if not v: ok = False
        # 日内限单 (规则F2)
        if self.daily_trades >= C.DAILY_MAX_TRADES:
            detail.append(f"❌日内已开{self.daily_trades}单(上限{C.DAILY_MAX_TRADES}, 规则F2)")
            ok = False
        return ok, detail

# ========== 固定保证金模式 (用户指定: 每单 5U) ==========
def size_fixed_margin(price, inst_id, leverage=None, mgn_per_contract=None):
    """固定保证金仓位, 张数 = 目标保证金 / 每张占用保证金, 按步长取整, 不低于最小下单。
    ★2026-10-04 方案A(用户裁定): 优先用【交易所口径的真实每张占用】(mgn_per_contract, 由
      main.real_margin_per_contract 反推)。因为 OKX 对 XAU 实收保证金并不等于"名义÷设置杠杆"
      (账户设50倍却按≈25倍收, 且交易所会自行变动), 用"实际占用"换算才能保证出来就是 5U。
      取不到实测值时, 退回"名义÷杠杆"的估算(leverage)。"""
    spec = C.INST_SPECS.get(inst_id)
    if not spec:
        return None
    lev = leverage or C.LEVERAGE_FIXED
    _mgn = (getattr(C, "INST_MARGIN_USD", None) or {}).get(inst_id, C.MARGIN_PER_TRADE)
    src = "assumed"
    if mgn_per_contract and mgn_per_contract > 0:
        raw_lots = _mgn / mgn_per_contract                 # ★按交易所实际占用换算
        src = "exchange"
    else:
        raw_lots = (_mgn * lev) / (spec["ctVal"] * price)
    lot = spec["lotSz"]
    lots = max(round(raw_lots / lot) * lot, spec["minSz"])
    actual_notional = lots * spec["ctVal"] * price
    actual_margin = round(lots * mgn_per_contract, 2) if src == "exchange" else round(actual_notional / lev, 2)
    return {"lots": round(lots, 6), "notional": round(actual_notional, 2),
            "margin": round(actual_margin, 2), "leverage": lev, "margin_src": src,
            "per_contract": round(mgn_per_contract, 6) if src == "exchange" else None,
            "risk_amount": round(actual_margin, 2), "stop_pct": round(100.0 / lev, 2)}


# ★2026-10-03 用户裁定: 爆仓价一律以【交易所返回的 liqPx】为准, 本地不做任何估算。
#   原 liquidation_price() / liquidation_sl() 已删除 —— 它们用 MMR_ESTIMATE 臆算爆仓价,
#   既污染止损决策, 又会在推送里给出与交易所不一致的"爆仓价"。
