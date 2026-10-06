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
BASE_TF = "15m"       # ★2026-10-07 用户裁定「把 1 小时撤掉」→ 只看 15m (profile 会覆盖)
HTF = "15m"           # 背景级别 = 15m 自身(不再用 1H)
STRATEGY_PROFILES = {
    "15": {"label": "15m", "base_tf": "15m", "htf": "15m", "ltf": "15m",
           "swing_left": 3, "swing_right": 3,
           "swing_htf": 3, "swing_ltf": 3},   # ★2026-10-07 用户裁定: swing 4→3, 对齐用户读图口径
}
#   ★2026-10-07 用户裁定「swing 改 3 根」: 用用户 10-06 那张图当"标准答案"比对 ——
#     用户手画的 BOS(≈4154) 与 CHoCH(≈4146), 在 swing=3 时正好被引擎认定为
#     18:30 BOS_up 4154.0 与 22:15 CHoCH_down 4146.3; 而 swing=4(旧值) 那 11 小时只认 1 个事件。
#     ⇒ 用户的眼睛 ≈ 1~3 根, 引擎原用 4 根 → 过粗。诊断脚本: tools/diag_struct_marks.py

# ---------- ★2026-10-07 用户裁定: 推送静默时段(北京时) ----------
#   用户: "不要求24小时, 主要在交易时段盯就行了(亚洲盘/伦敦盘/纽约盘)" → 三盘并集 ≈ 07:00~次日05:00,
#   只掐掉凌晨最寡淡的一段。该时段内【不推信号提醒】(引擎照常运行、照常记录, 只是不发消息)。
QUIET_HOURS_BJ = (5, 7)       # [起, 止) 北京时整点; 仅此区间静默; None=关闭
#   ★2026-10-07 用户裁定「把一小时撤掉」: 周期链由 1H+15m → 【只看 15m】。
#     方向/背景/入场全部在 15m 上判定(原 1H 的方向门去掉)。若之后想换回/换成 4H:
#     只需改本 dict 的 base_tf/htf(或 env ENTRY_DIR_SOURCE), 其余链路不动。

# ---------- 仓位模式(用户指定): 固定保证金 × 固定杠杆 ----------
MARGIN_PER_TRADE = 5.0      # 每单保证金 5 USDT
LEVERAGE_FIXED = 50         # ★2026-10-06 用户裁定: 固定 50 倍 (原 100 → 25 → 50; 与 WEEX_LEVERAGE 保持一致)
                            #   [工] 仅用于展示横幅与 "usd" 止盈口径的旧换算; 实际仓位数量见 WEEX_LEVERAGE
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
WEEX_MARGIN_USD = 5.0          # 每单目标保证金(USDT)
#   ★2026-10-06 用户裁定: 总资金 100U / 每单保证金回到 5U（配合 25x → 名义 ≈125U）
# 杠杆: sim 接口【不能设置杠杆】→ 以【你在 WEEX App 里给该合约设的杠杆】为准。
#   下面的值只是"首单"用的假设值; 开仓成交后会从持仓返回的 leverage 自动校正并写入 state。
WEEX_LEVERAGE = {"BTC-USDT-SWAP": 50, "XAU-USDT-SWAP": 50}
#   ★2026-10-06 用户已在 WEEX App 手动改为 50x → 此处同步(config 与 state["weex_leverage"] 两处都要)
#   50x 的含义: 名义 = 保证金 × 50（5U → 250U；25x 时为 125U）。
#   爆仓价距进场 ≈ 1/50 ≈ 2%（含维持保证金约 1.4~2.0%）→ 仍远宽于结构止损(~0.3%), 不会"还没打到就先爆仓"。
#   止盈用【固定价格 ±1%】口径(TP_MODE="pct"), 与杠杆无关 —— 杠杆只放大同一价格走势的美元盈亏:
#       50x 下 ±1% ≈ ±2.5U/单, 结构止损 ~0.3% ≈ −0.75U/单(每单保证金 5U)。
# ★2026-10-04: 是否接管"交易所有仓但本地无记录"的游离持仓。
#   默认 False —— 模拟盘账户你本人也可能手动下单, 引擎不擅自接管别人的仓(只在推送里提醒)。
ADOPT_ORPHANS = False
# ★★2026-10-07 事故修复(用户反馈"手动设的止盈止损被每轮撤销"):
#   主因是 main.py 的"清理无持仓孤立挂单"误读了 OKX 字段(instId/posSide) → WEEX 下恒取到 None
#   → 每轮把交易所上【所有】条件单都撤掉(含你手动挂的)。已修正字段映射 + 认不出归属一律不撤。
#   下面这个开关是第二道保险: **默认关闭** —— 引擎不再主动撤销任何条件单
#   (交易所会在仓位平掉时自行清理; 引擎自身的保护单由"读回自检/自愈补挂"管理)。
#   要恢复"自动清理孤立挂单"只需把此项设为 True(此时仍只撤"确认无持仓"的单)。
ALGO_CLEANUP_ORPHANS = False
# 交易对映射(内部品种名 → 模拟盘下单符号): 见 engine/weex_trade.SYMBOL_MAP
#   BTC-USDT-SWAP → BTCSUSDT ; XAU-USDT-SWAP → XAUTSUSDT(黄金是 XAUT)
LIQ_BUFFER_PCT = 0.003      # [工] 仅用于"孤儿仓保命止损": 在【交易所返回的爆仓价】内 0.3% 处挂止损

# ---------- 结构引擎 (模块A) ----------
# ★2026-10-04 起 = 【唯一关键旋钮】: 结构参考点/斐波腿 = 已确认 swing 极值(照开源库 smartmoneyconcepts 机制)
#   窗口越宽 → swing 越"大" → 腿越宽、止损越宽、信号越少但单笔期望越高(90天实测见 todo)
SWING_LEFT = 3        # [工] swing 极值确认窗口(左) —— 与开源库 smartmoneyconcepts 的 swing_length 同义
SWING_RIGHT = 3       # [工] swing 极值确认窗口(右)
                      # ★2026-10-07 用户裁定 4→3: 用用户 10-06 那张图当标准答案比对 ——
                      #   他手画的 BOS(≈4154)/CHoCH(≈4146) 在 s=3 时正好对应引擎的 18:30 BOS_up 4154.0
                      #   与 22:15 CHoCH_down 4146.3; s=4 时那 11 小时只认 1 个事件(全漏)。
                      #   参考: 开源库默认 swing_length=50(左右各50根), 在 1H/15m 上信号过少(90天仅6笔)。
                      #   敏感度(90天): s=2 → 353笔/−59.6U; s=4 → 见回测报告; s=5 → 164笔/+47.5U;
                      #                 s=10 → 92笔/+40.0U; s=20 → 39笔/+129.2U(样本少); s=50 → 6笔。
                      #   注: 运行期会被 STRATEGY_PROFILES[*].swing_left/right 覆盖, 两处必须一致。
# ★2026-10-05 按笔记《BOS和CHOCH概念》分层: 高周期用大 swing 定【Swing 方向】, 低周期用小 swing 做【Internal 结构】。
#   笔记建议: 高时间框架 Swing Length 10~15 ; 低时间框架(15m/5m) 2~5。
#   (运行期会被 STRATEGY_PROFILES[*].swing_htf/swing_ltf 覆盖, 两处必须一致)
SWING_LEN_HTF = 3     # 背景/定方向 的 swing_length (★2026-10-07: 10 → 3, 与 profile 的 swing_htf 保持一致)
                      # ★2026-10-05 90天实测选档(其余口径: 内部确认门k=4 + 止盈浮盈10U):
                      #   1H=4(旧) 127笔/净-26.09U → 1H=10 【99笔/净+40.88U/每笔+0.413/胜率18.2%】(最优,首次转正)
                      #   → 1H=12 105笔/+33.75U ; 1H=15 102笔/+1.28U ; 15m=2 211笔/-64.91U(太细=噪声)
SWING_LEN_LTF = 3     # 15m(入场/Internal) 的 swing_length (★2026-10-07: 4 → 3)
SMC_STRICT_CAUSAL = True   # [工] 无未来函数守卫: break 必须发生在 swing 确认(pivot+S)之后
                           #   (开源库原版允许 break 早于 swing 确认 = 回测偷看未来; True=修掉)
# ★2026-10-05 按用户笔记《BOS和CHOCH概念》修正: CHoCH 只是【反转预警】, 不立即翻转趋势。
#   True  = 趋势只由【BOS】翻转(反向 BOS 出现才确认反转); CHoCH 记入 trend_warn 作预警
#   False = 旧口径(最后一个结构事件即翻转趋势, CHoCH 也立刻翻)
CHOCH_IS_WARNING_ONLY = True

# ---------- 流动性 / FVG (模块B) ----------
IFVG_CONFIRM_BARS = (3, 8)     # iFVG牛熊转换: 下跌FVG出现后3~8根内回填(规则B4; 课程自称"可加可不加")
SWEEP_DOUBLE_POINT_H1 = False   # 2026-10-03 用户新口径: "双点"改为【必须扫到止损密集区】(更严)。开关保留备用。

# ---------- ② 截取目标 = 止损密集区 (2026-10-03 用户新口径) ----------
#   前高上方 / 前低下方 / 双顶双底(等高簇) / 趋势线(等高等低连线)
ZONE_TOL_PCT = 0.001        # [工] 同价簇容差: swing 点价格差 <= 0.1% 视为同一密集区(双顶/双底)
ZONE_LOOKBACK = 12          # [工] 参与聚簇的最近 swing 点数
TRENDLINE_PTS = 3           # [工] 趋势线 = 最近 3 个同向 swing 点连线(须单调)
RETRACE_MAX_AGE_BARS = 4    # ★启用(2026-10-05): 回踩必须【晚于 BOS】且发生在最近 N 根 15m 内
                            #   (笔记《FVG》: 结构确认后"不追高, 等回调进 FVG" → 回踩天然晚于 BOS)
CONFIRM_TURN_BAR = False    # [工] "回踩不得破预警起点"开关: 2026-10-03 实测此条会掐掉 5/6 的信号 → 默认关

# ---------- 视频法 (2026-10-04 用户裁定 A): 1H定背景(BOS+溢价/折价) → 15m 出 CHoCH 即入场 ----------
REQUIRE_SWEEP = False       # ② 是否仍要求"扫到止损密集区"(视频法不需要; 默认关, 需要时打开)
ENTRY_MAX_AGE_BARS = 4      # [已废弃 2026-10-04] 15m CHoCH 的"够新"限制(用户裁定删除)
SL_BUFFER_PCT = 0.0005      # 止损放在结构高点/低点外侧的缓冲(0.05%)
MIN_RR = 1.5                # [已废弃 2026-10-04] 盈亏比门槛(用户裁定删除; rr 仅作展示)
# ★★2026-10-06 用户裁定: 止盈 = 【固定价格百分比】或【固定盈亏比】(liq2r 经实测不是最优)
#   TP_MODE = "pct" → 止盈 = 入场价 ± TP_PCT%  (实测 90 天最优: 每笔R +0.33 / 净 +8.37U / 回撤 3.88U)
#   TP_MODE = "rr"  → 止盈 = 入场价 ± TP_RR × 风险距离 (实测次优, 与 pct 接近: 2R ≈ 0.6~1.0%)
#   （已弃用: "liq" 纯流动性目标中位仅 0.14%、比止损还近 → 期望为负; "liq2r" 加了 2R 下限仍不如 pct）
#   ⚠️ 参数将在【扩数据 180~365 天】复核后再定稿
TP_MODE = "pct"
#   TP_MODE = "struct" → ★2026-10-07 用户要求: 止盈 = 【打结构位】
#       多单 → 上方【最近的已确认摆动高点】; 空单 → 下方【最近的摆动低点】;
#       距入场不足 TP_STRUCT_MIN_PCT% 的摆动点跳过(避免贴脸目标); 取不到则退回 pct。
TP_STRUCT_MIN_PCT = 0.5      # "struct" 口径: 目标至少距入场 N%(比这近的摆动点忽略)
TP_PCT = 1.0                # TP_MODE="pct" 时的目标价格百分比(%)
TP_USD = 10.0               # (仅 "usd" 时生效) 止盈目标浮盈(USDT)
TP_RR = 2.0                 # "rr"/"liq2r" 的盈亏比
TP_USD = 10.0               # (仅 TP_MODE="usd" 时生效) 止盈目标浮盈(USDT)
TP_RR = 2.0                 # 固定盈亏比 —— "liq" 取不到前方摆动点 / "rr" 时生效
                            #   (旧口径: 原来是对侧结构点/腿的另一端 → 目标太近、扣费后 RR<1)
SEG_MIN_BARS = 3            # [工] 段最小尺寸: 被打穿的"段极值"至少已存在 N 根, 否则不算 CHoCH
                            #   (防"BOS后2根就被打穿=噪声"; 0=不过滤)

# ---------- ★2026-10-06 按用户视频《为什么你越用FVG胜率越低？》改: 缺口分类 ----------
#   视频要点: ① 真突破形成的【第一个缺口/OB 不会被轻易回踩】→ 在突破缺口上等回踩 = 大概率是弱/假突破;
#            ② 假突破(插针/反包/破坏块/N形)留下的 FVG【不是阻力, 是"假破的润滑剂"】;
#            ③ 只有【MEASURING GAP(动能不足回补型)】才是入场区。
#   注: smc.fvg 把缺口标记在【中间那根推动K线】(c2)上 → 缺口 = c1.high ~ c3.low。
FVG_PICK = "exclude_newest"  # ★2026-10-06 用户裁定「按视频采用」: 排除离突破位最近(最晚生成)的那根
                            #   依据: 视频铁律「不能在 Breakaway Gap(突破缺口) 挂单」——
                            #        真突破的第一根缺口很少被回踩, 能被回踩到=大概率弱/假突破。
                            #   90 天 A/B(见 deploy_out/FVG取法_90天对比.md): 胜率 36.0%→46.2%(+10.2pp)、
                            #        净利 +7.91→+10.15U(+28%)、每笔 0.069→0.260U、每笔R 0.39→0.52,
                            #        BTC 与黄金同步改善; 代价=笔数 114→39(−66%, ≈0.43 笔/天)。
                            #   候选取值: "nearest"=旧口径(取最近那根) / "exclude_newest"=本项
                            #            "exclude_break"=排除突破那根及之后 / "farthest"=只取最早那根
FVG_FAKEBREAK_FILTER = False  # ② 是否剔除"假破形态"的 FVG
FVG_FAKE_WICK_RATIO = 1.0     # 推动K线(c2)的长影线 ≥ 实体 × 该倍数 → 判为"刺破后收回(插针)"
FVG_FAKE_ENGULF = True        # c3 实体反包 c2 实体 → 判为"假破反包"
# ★2026-10-06 按视频《为什么你越用FVG胜率越低？》#2: Filled Gap vs Tap Gap
#   视频: 「Filled Gap(会被实体填补的缺口)不应入场; 只有 Tap Gap(仅被影线穿刺、没有实体进入)才最优」
#   我方旧口径只按课程 B3「实体收盘【完全】穿过」判失效 → 被实体部分填补的缺口仍算有效并照常入场。
#   本开关: 在"回踩触发"那一步再判一次 —— 若该缺口此前已被【实体(开收区间)进入】过 → 视为 Filled Gap 剔除。
#   字段来源: engine/liquidity.py 每个 FVG 的 body_entered_idx(首个实体进入的K线索引, 无则 None)。
FVG_FILLED_FILTER = False     # 是否启用"实体填补(Filled Gap)"过滤 (默认关; A/B 后再定)
FVG_FILLED_MODE = "prior"     #   "prior"  = 触发那根【之前】已有实体进入 → 判为 Filled Gap 剔除
                              #   "strict" = 更严: 连触发那根本身也必须是纯影线穿刺(实体不得进入)

# ---------- ★2026-10-06 按视频《为什么你用ICT策略总止损?——(2)IFVG的正确用法》(BV1537DzfEq8) ----------
#   IFVG 反转入场: 顺势 FVG 被【反向实体收盘穿越】后, 角色反转成反向入场区。
#   视频三条件: ①左侧 Market Maker Model 走完(原始盘整+≥2次冲击→清扫流动性)
#               ②左侧留有未被扫掉的 Failure Swing 流动性(≈"未被扫掉的摆动极值")
#               ③只认"清扫段最后一根" IFVG 的反转
#   周期: 不用 1m, 至少 3/5/15m(我方入场周期=15m, 天然满足)
#   入场: 反转蜡烛实体 50%(CE)/25% 挂限价; 止损: 反转蜡烛极值外侧; 止盈: 被清扫的原始盘整高/低点
#   实现位置: engine/liquidity.py 生成 ifvg_events; engine/entry.py::_ifvg_signal 判入场。
IFVG_MODE = "off"             # "off"=仅FVG(现行) / "add"=FVG无信号时补一个IFVG反转 / "only"=仅IFVG反转
IFVG_MAX_AGE_BARS = 8         # 反转蜡烛距当前最多 N 根 15m 内(且须早于当前那根 = 有回踩空间)
IFVG_REQUIRE_HTF_ALIGN = True # 反转方向须与 1H 结构方向一致
IFVG_REQUIRE_SWEEP = True     # 条件①: 反转蜡烛之前须发生过"同向清扫"(bull反转需前置 down sweep)
IFVG_SWEEP_WINDOW = 30        #   清扫须发生在反转蜡烛前 N 根内
IFVG_REQUIRE_FAIL = True      # 条件②: 须存在未被扫掉的摆动极值(=止盈目标), 无则不进场
IFVG_CE_LEVEL = 0.5           # 入场位: 反转蜡烛实体 0.5(CE) / 0.25
IFVG_TP_MODE = "liq"          # 止盈: "liq"=未被扫掉的摆动极值(被清扫的原始盘整高/低点) / "pct" / "rr"

# ---------- ★2026-10-06 用户提问「只看15分钟的FVG呢?」: 方向来源可切换 ----------
#   "1h"  = 现行: 用 1H(背景级别) 结构方向定多空, 15m 回踩 FVG 入场
#   "15m" = 只看 15m: 多空方向改用【15m 自己的结构方向】, 其余链路(15m结构确认+FVG回踩)不变
#   (若再把 INT_REQUIRE_BOS/INT_REQUIRE_CHOCH 关掉, 就接近"纯 15m FVG")
ENTRY_DIR_SOURCE = "1h"

# ---------- ★2026-10-07 用户裁定「可以」: 信号重建为【15m FVG 回踩提示】 ----------
#   起因: 旧"四步链"(逆势CHoCH→顺势BOS≤4根→该推动浪FVG→回踩≤4根) 在真实数据上过去24h信号=0,
#         而"价格回踩进未回填15m FVG"的事件约 10~19 次/天 —— 规则和用户读图方式不是一回事。
#   新口径(方案2): 只要【价格新回踩进一个未回填的 15m FVG】就提示; 并要求【最近 N 根内出现过
#         BOS/CHoCH 结构】作背书(不是门槛链, 只是"这根 FVG 有结构背景"的筛子)。
#   方向: 看涨缺口(bull FVG)→做多提示; 看跌缺口(bear FVG)→做空提示。
#   止损: FVG 左侧那根K线极值外侧(沿用现行); 止盈: 沿用全局 TP_MODE(现为固定±1%)。
SIGNAL_MODE = "fvg_both"      # "chain"=旧四步链 / "fvg_touch"=FVG回踩 / "fvg_handover"=缺口交接定向 / "fvg_both"=★两侧独立(现行)
FVGT_REQUIRE_STRUCT = True    # 方案2: 需最近 N 根内出现过 BOS/CHoCH(结构背书)
FVGT_STRUCT_WINDOW = 8        # 结构须落在最近 N 根 15m 内
FVGT_MAX_CAND = 4             # 同一时刻最多取最近 N 根未回填 FVG 作为候选(取最近那根)

# ---------- ★2026-10-07 用户读图口径: 【缺口交接 → 回踩顺势缺口】(SIGNAL_MODE="fvg_handover") ----------
#   用户原话: "出现了choch我没有着急入场, 在看价格行为; FVG有多个出现, 多FVG把空FVG打掉了,
#             然后回踩了多FVG, 随后价格开始上涨; 出现choch之后也确实出现了fvg"。
#   含义: 入场依据不是"哪根缺口被碰到", 而是【反向缺口被实体收盘打掉(=缺口交接)】
#         → 方向由"哪一侧赢了"给出 → 再等价格【回踩交接后新生成的顺势缺口】。
#   数据源: engine/liquidity.py 的 ifvg_events(反向缺口被实体收盘穿越) —— 与"收盘穿破"口径天然一致。
#   实现: engine/entry.py::_fvg_handover_signal
FVGH_MAX_AGE_BARS = 12       # 交接事件须落在最近 N 根 15m 内
FVGH_MAX_BARS_AFTER = 8      # 顺势缺口须在交接发生后 N 根内生成
FVGH_TAKEOVER = True         # ★2026-10-07 用户口径B: 缺口【接管】也算交接
                             #   (后生成的反向缺口覆盖/重叠同区域的前一个缺口 → 交接, 方向=后来者)
                             #   用户实例: 02:45 多缺口4168.1~4172.4 被 03:15 空缺口4170.6~4172.4 接管 → 做空
FVGH_REQUIRE_CHOCH = False   # 是否额外要求最近出现过 CHoCH(默认关: 用户实例中引擎认不到他手画的CHoCH)
FVGH_CHOCH_WINDOW = 12

# ---------- ★2026-10-06 用户想法: BOS/CHoCH 产生的 FVG 都有价值(含【反向FVG】) ----------
#   用户原话要点: ① BOS 不代表价格继续; ② 后续跌破该段最近低点 → 转 CHoCH(方向反转), 伴随的 FVG 可入场;
#                 ③ 涨 BOS 后出现的【看跌 FVG】(与 BOS 反向) 也可入场; ④ BOS 与 CHoCH 的 FVG 都有参考价值。
#   现状: 只取【顺势】FVG(方向=1H); 本开关追加【反向 FVG】入场(方向=CHoCH 的反转方向, 与 1H 相反)。
#   实现: engine/entry.py::_counter_fvg_signal(15m 逆势CHoCH → 该反向 FVG 回踩入场)。
FVG_COUNTER_MODE = "off"      # "off"=现行 / "add"=顺势FVG无信号时补一个反向FVG / "only"=仅反向FVG
CFVG_MAX_AGE_BARS = 8         # 逆势 CHoCH 距当前最多 N 根 15m 内
CFVG_REQUIRE_CHOCH = True     # True=须有逆势CHoCH锚定(用户①②); False=只看"反向FVG"(用户③)

# ---------- ★2026-10-05 按用户笔记《BOS和CHOCH概念》补: Internal 结构确认 ----------
#   笔记"实战配置逻辑(专业用法)": ①Swing结构定方向 → ②等 Internal CHoCH(微观逆势转变=回调结束)
#   → ③等 Internal BOS(顺势突破=延续确认, 笔记称 "First BOS") → 才进场。
#   常见错误(笔记): 单独交易 CHoCH、在已大幅延伸的走势后追入 → 故 BOS 要"够新"。
#   实现位置: engine/entry.py 在 15m 回踩 FVG 之后追加此门(只加确认, 不改方向/止损/止盈口径)。
INT_REQUIRE_CHOCH = True     # 入场前, 15m 须已出现【逆势 CHoCH】(回调结束预警)
INT_REQUIRE_BOS = True       # 且随后出现【顺势 BOS】(延续确认)
INT_CONFIRM_MAX_AGE_BARS = 4 # 该 BOS 距当前不超过 N 根 15m(值越小越"新鲜"、信号越少)
# ★2026-10-05 按笔记《FVG》+《BOS和CHOCH概念》重构入场链(entry.py):
#   结构 与 FVG 不再是两道独立门, 而是【一条因果链】:
#     BOS(可达 N 根内) → 该段推动浪里必须留下顺势未回填 FVG(没有=低质量突破,忽略)
#       → 不追高, 等价格【回调进该 FVG】(回踩须晚于BOS、且最近 RETRACE_MAX_AGE_BARS 根内) → 进场
#   ① "BOS后出现反向 CHoCH" 不再判否(笔记要求等回调, 回调天然产生反向CHoCH);
#      仍禁"BOS后出现反向 BOS"(那才是结构真反转)。
#   ② 90天回测: 原版 97笔/+48.87U/期望0.504 → 本版 120笔/+69.77U/期望0.581; 30天同向。
                             # ★2026-10-05 90天实测选档(止盈=浮盈10U, 其余口径不变):
                             # ★2026-10-05 90天实测选档(止盈=浮盈10U, 其余口径不变):
                             #   无确认 649笔/净-306.5U/每笔-0.47  →  仅CHoCH 391/-171.4/-0.44
                             #   →  仅BOS 192/-59.5/-0.31  →  CHoCH+BOS k=4 【124笔/净-24.9U/每笔-0.20/胜率16.1%】(最优)
                             #   k=8 176/-52.7  ; k=16 235/-93.1  ; k=999 292/-100.0(毛最高+46U但笔数多、费多)

# ---------- 入场模板 (模块C) ----------
RETRACE_FIBS = [0.382, 0.5, 0.618]   # 回踩区间(规则C6; 当前仅用于标记 confidence)

# ---------- 出场管理 (模块D) ----------
TRAIL_SL_ON_BOS = True        # 突破结构位后 SL 移到"被突破位"(规则D4)

# ---------- 风控 (模块F) ----------
DAILY_MAX_TRADES = 999        # 日内限单(用户决定: 暂不设, 先攒样本)
RR_MIN_GROWTH = 2.0           # 止盈固定 1:2 (规则E12)

# ---------- 告警 ----------
WECOM_WEBHOOK_ENV = "WECOM_WEBHOOK"

# ---------- ★2026-10-05 (用户裁定 P3-11): 运行日报归档 ----------
#   日报文本落盘到 engine/reports/运行日报_YYYYMMDD.md(由 watch.yml 提交, 长期归档),
#   并在配置了 IMA_OPENAPI_* 凭据时, best-effort 同步到 知识库 wind / 05-运行日报。
KB_WIND_ID = "w_SEcqwVLdF6JKMFKUq73j75ULEcOcqGUfsLQC_35f4="   # 知识库 wind
KB_DAILY_FOLDER = "folder_7510739656931312"                   # wind/05-运行日报
