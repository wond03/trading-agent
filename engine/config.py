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

# ---------- 周期链 (2026-10-04 用户裁定: 三个级别太多 → 两个级别 1H + 15m) ----------
# 1H 定趋势/找截取/反转预警 → 15m 回踩FVG/入场
BASE_TF = "1H"        # 主分析周期(profile 会覆盖)
HTF = "1H"            # 背景级别(定趋势、找截取)
STRATEGY_PROFILES = {
    "1-15": {"label": "1-15", "base_tf": "1H", "htf": "1H", "ltf": "15m",
             "swing_left": 4, "swing_right": 4},      # ★2026-10-04: 2 → 4 (与 SWING_LEFT/RIGHT 对齐)
}

# ---------- 仓位模式(用户指定): 固定保证金 × 固定杠杆 ----------
MARGIN_PER_TRADE = 5.0      # 每单保证金 5 USDT
LEVERAGE_FIXED = 100        # 固定 100 倍
# ★2026-10-04 用户裁定【方案A】: 每单目标保证金 5U, 张数用【交易所实际每张占用】换算
#   (见 main.real_margin_per_contract: 实测持仓反推 > 梯度保证金表 imr > 退回名义÷杠杆)。
#   背景: OKX 对 XAU-USDT-SWAP 实收保证金 ≠ 名义÷设置杠杆(账户设50倍, 实收≈25倍, 且会自行变动),
#   只按公式算会开出 10U 的仓。改用实际占用后: XAU≈30张、BTC≈0.59张, 两者实收都≈5U。
INST_MARGIN_USD = {"BTC-USDT-SWAP": 5.0, "XAU-USDT-SWAP": 5.0}   # 【OKX 旧口径, 已弃用(仅存档)】
INST_LEVER = {"BTC-USDT-SWAP": 100, "XAU-USDT-SWAP": 50}        # 【OKX 旧口径, 已弃用(仅存档)】

# ---------- ★2026-10-04 用户裁定: 下单从 OKX 整体切到【WEEX 模拟盘】, 不再保留 OKX ----------
#   接口: https://api-contract.weex.com 的 /capi/v3/sim/*(仅 余额/持仓/下单/历史 四个)
#   下单数量 = 【币的数量】(不是张数): 0.0059 BTC / 0.121 XAUT。张数=币量/contractVal。
#   止盈止损 = 下单时内联 tpTriggerPrice/slTriggerPrice 一并提交(无独立条件单接口)。
#   平仓 = 反向市价单; 没有撤单接口 → 全用市价单, 成交靠轮询持仓确认。
WEEX_MARGIN_USD = 5.0          # 每单目标保证金(USDT; 模拟盘计价资产为 SUSDT)
# 杠杆: sim 接口【不能设置杠杆】→ 以【你在 WEEX App 里给该合约设的杠杆】为准。
#   下面的值只是"首单"用的假设值; 开仓成交后会从持仓返回的 leverage 自动校正并写入 state。
WEEX_LEVERAGE = {"BTC-USDT-SWAP": 100, "XAU-USDT-SWAP": 100}
# ★2026-10-04: 是否接管"交易所有仓但本地无记录"的游离持仓。
#   默认 False —— 模拟盘账户你本人也可能手动下单, 引擎不擅自接管别人的仓(只在推送里提醒)。
ADOPT_ORPHANS = False
# 交易对映射(内部品种名 → 模拟盘下单符号): 见 engine/weex_trade.SYMBOL_MAP
#   BTC-USDT-SWAP → BTCSUSDT ; XAU-USDT-SWAP → XAUTSUSDT(黄金是 XAUT)
LIQ_BUFFER_PCT = 0.003      # [工] 仅用于"孤儿仓保命止损": 在【交易所返回的爆仓价】内 0.3% 处挂止损

# ---------- 结构引擎 (模块A) ----------
# ★2026-10-04 起 = 【唯一关键旋钮】: 结构参考点/斐波腿 = 已确认 swing 极值(照开源库 smartmoneyconcepts 机制)
#   窗口越宽 → swing 越"大" → 腿越宽、止损越宽、信号越少但单笔期望越高(90天实测见 todo)
SWING_LEFT = 4        # [工] swing 极值确认窗口(左) —— 与开源库 smartmoneyconcepts 的 swing_length 同义
SWING_RIGHT = 4       # [工] swing 极值确认窗口(右)
                      # ★2026-10-04 用户裁定: 统一为 4 (线上原为 2/回测原为 5, 已对齐)。
                      #   参考: 开源库默认 swing_length=50(左右各50根), 在 1H/15m 上信号过少(90天仅6笔)。
                      #   敏感度(90天): s=2 → 353笔/−59.6U; s=4 → 见回测报告; s=5 → 164笔/+47.5U;
                      #                 s=10 → 92笔/+40.0U; s=20 → 39笔/+129.2U(样本少); s=50 → 6笔。
                      #   注: 运行期会被 STRATEGY_PROFILES[*].swing_left/right 覆盖, 两处必须一致。
SMC_STRICT_CAUSAL = True   # [工] 无未来函数守卫: break 必须发生在 swing 确认(pivot+S)之后
                           #   (开源库原版允许 break 早于 swing 确认 = 回测偷看未来; True=修掉)

# ---------- 流动性 / FVG (模块B) ----------
IFVG_CONFIRM_BARS = (3, 8)     # iFVG牛熊转换: 下跌FVG出现后3~8根内回填(规则B4; 课程自称"可加可不加")
SWEEP_DOUBLE_POINT_H1 = False   # 2026-10-03 用户新口径: "双点"改为【必须扫到止损密集区】(更严)。开关保留备用。

# ---------- ② 截取目标 = 止损密集区 (2026-10-03 用户新口径) ----------
#   前高上方 / 前低下方 / 双顶双底(等高簇) / 趋势线(等高等低连线)
ZONE_TOL_PCT = 0.001        # [工] 同价簇容差: swing 点价格差 <= 0.1% 视为同一密集区(双顶/双底)
ZONE_LOOKBACK = 12          # [工] 参与聚簇的最近 swing 点数
TRENDLINE_PTS = 3           # [工] 趋势线 = 最近 3 个同向 swing 点连线(须单调)
RETRACE_MAX_AGE_BARS = 4    # [工] 回踩必须发生在最近 N 根 15m 内(防止"踩过很久才开仓"→开仓价离FVG很远)
CONFIRM_TURN_BAR = False    # [工] "回踩不得破预警起点"开关: 2026-10-03 实测此条会掐掉 5/6 的信号 → 默认关

# ---------- 视频法 (2026-10-04 用户裁定 A): 1H定背景(BOS+溢价/折价) → 15m 出 CHoCH 即入场 ----------
REQUIRE_SWEEP = False       # ② 是否仍要求"扫到止损密集区"(视频法不需要; 默认关, 需要时打开)
ENTRY_MAX_AGE_BARS = 4      # [已废弃 2026-10-04] 15m CHoCH 的"够新"限制(用户裁定删除)
SL_BUFFER_PCT = 0.0005      # 止损放在结构高点/低点外侧的缓冲(0.05%)
MIN_RR = 1.5                # [已废弃 2026-10-04] 盈亏比门槛(用户裁定删除; rr 仅作展示)
TP_RR = 2.0                 # ★止盈盈亏比(2026-10-04 用户裁定): 止盈 = 进场价 ± TP_RR × 风险距离
                            #   (原来是"对侧结构点/腿的另一端" → 目标太近、扣手续费后 RR<1; 改为固定 1:2)
SEG_MIN_BARS = 3            # [工] 段最小尺寸: 被打穿的"段极值"至少已存在 N 根, 否则不算 CHoCH
                            #   (防"BOS后2根就被打穿=噪声"; 0=不过滤)

# ---------- 入场模板 (模块C) ----------
RETRACE_FIBS = [0.382, 0.5, 0.618]   # 回踩区间(规则C6; 当前仅用于标记 confidence)

# ---------- 出场管理 (模块D) ----------
TRAIL_SL_ON_BOS = True        # 突破结构位后 SL 移到"被突破位"(规则D4)

# ---------- 风控 (模块F) ----------
DAILY_MAX_TRADES = 999        # 日内限单(用户决定: 暂不设, 先攒样本)
RR_MIN_GROWTH = 2.0           # 止盈固定 1:2 (规则E12)

# ---------- 告警 ----------
WECOM_WEBHOOK_ENV = "WECOM_WEBHOOK"
