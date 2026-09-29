# 盯盘/交易引擎配置 —— 森林查尔斯课程规则库实现
# 所有 [待标定] 阈值先用默认值, 上模拟盘后用数据回测校准
# 依据: /sandbox/workspace/trading_agent/transcripts/规则库_森林查尔斯课程.md

# ---------- 品种与周期 ----------
SYMBOLS = {
    "BTC-USDT-SWAP": {"enabled": True, "modules": ["structure", "liquidity", "entry", "funding"], "td_mode": "isolated"},
    "XAU-USDT-SWAP": {"enabled": True, "modules": ["structure", "liquidity", "entry"], "td_mode": "isolated"},  # 黄金合约(云端实测存在,100倍)
}
# 合约规格(2026-09-30 云端实测 OKX /public/instruments)
INST_SPECS = {
    "BTC-USDT-SWAP": {"ctVal": 0.01,  "lotSz": 0.01, "minSz": 0.01},
    "XAU-USDT-SWAP": {"ctVal": 0.001, "lotSz": 1,    "minSz": 1},
}
# ---------- 仓位模式(用户指定): 固定保证金 × 固定杠杆 ----------
MARGIN_PER_TRADE = 5.0      # 每单保证金 5 USDT
LEVERAGE_FIXED = 100        # 固定 100 倍
LIQ_BUFFER_PCT = 0.003      # 爆仓线前 0.3% 强平(等效止损, 避免爆仓罚金)
MMR_ESTIMATE = 0.005        # 维持保证金率估算(100倍档约0.4%~0.5%)
BASE_TF = "1H"        # 主分析周期 (规则A7: 做1H看4H; 做5m看1H)
HTF = "4H"            # 高一级周期 (只推一级, 规则A6)
TIMEFRAME_SECONDS = {"1H": 3600, "4H": 14400, "15m": 900, "5m": 300}

# ---------- 结构引擎 (模块A) ----------
SWING_LEFT = 2        # swing high/low: 左右各2根K线确认 (简化实现, 课程未给窗口, 待标定)
SWING_RIGHT = 2
CONSOLIDATION_ATR = 1.5   # [待标定] swing高低点间距 < ATR*此值 → 视为盘整区, 区内突破屏蔽信号(规则A4)
HTF_TREND_WEIGHT = True   # 多周期共振: 基础周期信号必须与HTF趋势同向(规则A8), 否则降级观察

# ---------- 流动性/FVG (模块B) ----------
FVG_MIN_ATR = 0.3         # [待标定] FVG最小尺寸 = ATR14 * 此值, 过滤噪声缺口(规则B1)
IFVG_CONFIRM_BARS = (3, 8)  # IFVG牛熊转换: 下跌FVG出现后3~8根内回填(规则B4), 超过8根视为失效
SWEEP_DOUBLE_POINT_H1 = True  # 1H级别截取须扫到2个点(规则B5); 实现为: 扫过的swing点数>=2
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
EXIT_ON_VOLUME_SPIKE = True   # 出量止盈(规则D1), 阈值见下
VOLUME_SPIKE_MULT = 2.0       # [待标定] 成交量 > 20期均量*此倍数 = 出量
EXIT_ON_CHOCH_REVERSE = True  # 趋势转换立即出场不论盈亏(规则D1)
TP1_PREV_SWING = True         # TP1=段起点前高/前低, 到位上保本(规则D2/D8)
TRAIL_SL_ON_BOS = True        # 突破结构位后SL移到被突破位下方(规则D4)

# ---------- 风控 (模块F, 直接硬编码) ----------
RISK_PER_TRADE = 0.01         # 单笔风险 = 总仓1% (规则E1/F1)
MAX_LEVERAGE_CAP = 20         # 个人杠杆上限(规则E4: 老师最高20倍)
DAILY_MAX_TRADES = 2          # 日内≤2单(规则F2)
SL_AT_STRUCTURE = True        # 止损挂结构位外侧+留插针空间(规则F3)
SL_BUFFER_ATR = 0.2           # [待标定] 止损在结构位外再加ATR*此值的插针缓冲
REQUIRE_ALL_CONDITIONS = True # 五条件严格AND缺一不做(规则F1)
RR_MIN_GROWTH = 2.0           # 前期发育盈亏比1:2(规则E12); 进阶RR>=4
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
