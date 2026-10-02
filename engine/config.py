# 暗夜猎手 (NightHunter) · 配置中心
# 盯盘/交易引擎配置 —— 森林查尔斯课程规则库实现
# 2026-10-02 大清理: 删除全部"写了但代码不引用"的历史项
#   被删项与依据说明见《暗夜猎手_信号逻辑说明书》第七节
#   标注 [工] = 工程默认(无课程原文依据), 需知悉

# ---------- 品种 ----------
SYMBOLS = {
    "BTC-USDT-SWAP": {"enabled": True, "modules": ["structure", "liquidity", "entry", "funding"], "td_mode": "isolated"},
    "XAU-USDT-SWAP": {"enabled": True, "modules": ["structure", "liquidity", "entry"], "td_mode": "isolated"},
}
# 合约规格(2026-09-30 云端实测 OKX /public/instruments)
INST_SPECS = {
    "BTC-USDT-SWAP": {"ctVal": 0.01,  "lotSz": 0.01, "minSz": 0.01},
    "XAU-USDT-SWAP": {"ctVal": 0.001, "lotSz": 1,    "minSz": 1},
}

# ---------- 周期链 (用户裁定 2026-10-02: 单链 4-1-15) ----------
# 4H 定趋势 → 1H 找截取 → 15m 反转预警(CHoCH) + 回踩FVG → 触发(规则C1五步)
BASE_TF = "1H"        # 主分析周期(profile 会覆盖)
HTF = "4H"            # 高一级周期(只推一级, 规则A6)
STRATEGY_PROFILES = {
    "4-1-15": {"label": "4-1-15", "base_tf": "1H", "htf": "4H", "ltf": "15m",
               "swing_left": 2, "swing_right": 2},
}

# ---------- 仓位模式(用户指定): 固定保证金 × 固定杠杆 ----------
MARGIN_PER_TRADE = 5.0      # 每单保证金 5 USDT
LEVERAGE_FIXED = 100        # 固定 100 倍
INST_LEVER = {"BTC-USDT-SWAP": 100, "XAU-USDT-SWAP": 50}   # 各品种实际上限(OKX实测: XAU上限50)
LIQ_BUFFER_PCT = 0.003      # [工] 仅用于"孤儿仓保命止损": 在【交易所返回的爆仓价】内 0.3% 处挂止损

# ---------- 结构引擎 (模块A) ----------
SWING_LEFT = 2        # [工] swing 极值确认窗口(左)
SWING_RIGHT = 2       # [工] swing 极值确认窗口(右)

# ---------- 流动性 / FVG (模块B) ----------
IFVG_CONFIRM_BARS = (3, 8)     # iFVG牛熊转换: 下跌FVG出现后3~8根内回填(规则B4; 课程自称"可加可不加")
SWEEP_DOUBLE_POINT_H1 = True   # 课程B5: 1H 截取必须"双点"(≥2根不同K线各扫掉一个点)

# ---------- 入场模板 (模块C) ----------
RETRACE_FIBS = [0.382, 0.5, 0.618]   # 回踩区间(规则C6; 当前仅用于标记 confidence)

# ---------- 出场管理 (模块D) ----------
TRAIL_SL_ON_BOS = True        # 突破结构位后 SL 移到"被突破位"(规则D4)

# ---------- 风控 (模块F) ----------
DAILY_MAX_TRADES = 999        # 日内限单(用户决定: 暂不设, 先攒样本)
RR_MIN_GROWTH = 2.0           # 止盈固定 1:2 (规则E12)

# ---------- 告警 ----------
WECOM_WEBHOOK_ENV = "WECOM_WEBHOOK"
