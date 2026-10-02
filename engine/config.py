# 暗夜猎手 (NightHunter) · 配置中心
# 盯盘/交易引擎配置 —— 森林查尔斯课程规则库实现
# 所有 [待标定] 阈值先用默认值, 上模拟盘后用数据回测校准
# 依据: /sandbox/workspace/trading_agent/transcripts/规则库_森林查尔斯课程.md

# ---------- 品种与周期 ----------
SYMBOLS = {
    "BTC-USDT-SWAP": {"enabled": True, "modules": ["structure", "liquidity", "entry", "funding"], "td_mode": "isolated"},
    "XAU-USDT-SWAP": {"enabled": True, "modules": ["structure", "liquidity", "entry"], "td_mode": "isolated"},   # 2026-10-02 用户指定: XAU 保持启用, 与BTC同跑双方案, 不做品种暂停
}
# 合约规格(2026-09-30 云端实测 OKX /public/instruments)
INST_SPECS = {
    "BTC-USDT-SWAP": {"ctVal": 0.01,  "lotSz": 0.01, "minSz": 0.01},
    "XAU-USDT-SWAP": {"ctVal": 0.001, "lotSz": 1,    "minSz": 1},
}
# ---------- 仓位模式(用户指定): 固定保证金 × 固定杠杆 ----------
MARGIN_PER_TRADE = 5.0      # 每单保证金 5 USDT
LEVERAGE_FIXED = 100        # 固定 100 倍
INST_LEVER = {"BTC-USDT-SWAP": 100, "XAU-USDT-SWAP": 50}   # 各品种实际最大杠杆(OKX实测: XAU上限50)
LIQ_BUFFER_PCT = 0.003      # 爆仓线前 0.3% 强平(等效止损, 避免爆仓罚金)
MMR_ESTIMATE = 0.005        # 维持保证金率估算(100倍档约0.4%~0.5%)
BASE_TF = "1H"        # 主分析周期 (2026-10-02定: 15m经回测证明负期望, 回归1H)
HTF = "4H"            # 高一级周期 (只推一级, 规则A6)
TIMEFRAME_SECONDS = {"1H": 3600, "4H": 14400, "15m": 900, "5m": 300}

# ---------- 周期链 (2026-10-02 用户裁定: 4-1-15 单链, 不再拆分并行方案) ----------
# 一条链走完: 4H 定趋势 → 1H 找截取/转势(结构级别) → 15m 触发入场(规则C1五步); 日线不用
# htf=趋势级别(高一级); base_tf=结构级别(找截取/转势); ltf=触发级别(低一级, 规则C1第⑤步"切小级别等转势")
STRATEGY_PROFILES = {
    "4-1-15": {"label": "4-1-15", "base_tf": "1H", "htf": "4H", "ltf": "15m",
               "swing_left": 2, "swing_right": 2, "sweep_window": 20},
}
# 日内限单: DAILY_MAX_TRADES 统一上限

# ---------- 结构引擎 (模块A) ----------
SWING_LEFT = 2        # swing确认窗口(1H下=2小时) [待标定]
SWING_RIGHT = 2
HTF_TREND_WEIGHT = True   # 多周期共振: 基础周期信号必须与HTF趋势同向(规则A8), 否则降级观察

# ---------- 流动性/FVG (模块B) ----------
IFVG_CONFIRM_BARS = (3, 8)  # IFVG牛熊转换: 下跌FVG出现后3~8根内回填(规则B4), 超过8根视为失效
SWEEP_WINDOW = 20     # 截取有效期(根): 1H下=20小时
SWEEP_DOUBLE_POINT_H1 = True   # 2026-10-02 校准恢复: 课程B5"1H必须双点截取"(此前为凑信号量临时放宽为False)
SIGNAL_GRADING = True          # 分级信号: A级(双点+回踩FVG,完整五步) / B级(单点或仅回踩斐波)
TRUE_BREAK_BY_CLOSE = True    # 实体收过=真突破, 影线刺破收回=截取扫损(规则A11/B11 ★核心二元判定)

# ---------- 入场模板 (模块C) ----------
ENTRY_STEPS = ["htf_trend", "sweep", "turn", "retrace", "trigger"]  # 五步流程(规则C1)
GATE_NO_SWEEP_NO_TRADE = True  # 总开关: 无截取或无转=不开单(规则C2)
RETRACE_FIBS = [0.382, 0.5, 0.618]   # 回踩分批位(规则C6)
FIB_TARGET_MAP = {            # 目标映射(规则C7, 两集口径不一, 取保守口径, 待回测统一)
    0.618: 1.272,
    0.5:   1.272,
    0.382: 1.618,
}
MSS_TWO_POS_RATIO = [0.6, 0.4]  # MSS双仓: 第一仓60% + CHoCH确认回踩补40%(规则C5)

# ---------- 出场管理 (模块D) ----------
EXIT_ON_VOLUME_SPIKE = True   # 出量→上保本(规则D1-①; 用户裁定2026-10-02: 只上保本不主动减仓), 阈值见下
VOLUME_SPIKE_MULT = 2.0       # [待标定] 成交量 > 20期均量*此倍数 = 出量
EXIT_ON_CHOCH_REVERSE = True  # 趋势转换立即出场不论盈亏(规则D1)
TP1_PREV_SWING = True         # TP1=段起点前高/前低, 到位上保本(规则D2/D8)
TRAIL_SL_ON_BOS = True        # 突破结构位后SL移到被突破位下方(规则D4)

# ---------- 风控 (模块F, 直接硬编码) ----------
RISK_PER_TRADE = 0.01         # 单笔风险 = 总仓1% (规则E1/F1)
MAX_LEVERAGE_CAP = 20         # 个人杠杆上限(规则E4: 老师最高20倍)
DAILY_MAX_TRADES = 999        # 2026-10-02 用户决定: 暂不设日内限单, 先攒样本数据
SL_AT_STRUCTURE = True        # 止损挂结构位外侧+留插针空间(规则F3)
REQUIRE_ALL_CONDITIONS = True # 五条件严格AND缺一不做(规则F1)
RR_MIN_GROWTH = 2.0           # 止盈固定1:2 (规则E12; 课程 BV1H8cuzmEbr[037min]"止盈就抓一比二", 前期发育口径). 用户裁定2026-10-02: 不再用斐波扩展凑目标
WEEKEND_POSITION_FACTOR = 0.5 # [待标定] 周末流动性差减仓系数(规则F9)

# ---------- 滚仓 (模块E) ----------
PYRAMID_TRIGGER_PROFIT = 2.0  # 浮盈达本金2倍才加仓(规则E7)
MAX_BOUND_POSITIONS = 2       # 主升浪最多2张绑定单(规则E7)
PYRAMID_MODE = "reverse"      # 倒金字塔: 越跌越加比重递增(规则E10)
SPOT_PERP_SPLIT = (0.8, 0.2)  # 80%现货+20%合约(规则E5)

# ---------- 数据源 ----------
DATA_SOURCE_LOCAL_TEST = "gate"   # 本地开发测试用Gate.io(沙盒可达); 正式运行=OKX(GitHub Actions)
DATA_SOURCE_PROD = "okx"
OKX_BASE = "https://www.okx.com"
OKX_SIM_HEADER = {"x-simulated-trading": "1"}  # OKX模拟盘必须带此header
INST_ID_MAP = {"BTC-USDT-SWAP": "BTC-USDT-SWAP", "PAXG-USDT": "PAXG-USDT"}

# ---------- 告警 ----------
WECOM_WEBHOOK_ENV = "WECOM_WEBHOOK"
PUSH_WATCH = False            # 2026-10-02 用户决定: 关闭"B级机会观察"推送(意义不大, 减少噪音)
