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
             "swing_left": 4, "swing_right": 4,          # ★2026-10-04: 2 → 4 (与 SWING_LEFT/RIGHT 对齐)
             "swing_htf": 10, "swing_ltf": 4},           # ★2026-10-05: 分层(笔记建议 高周期10~15/低周期2~5); 实测 10 最优
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
WEEX_MARGIN_USD = 5.0          # 每单目标保证金(USDT)
#   ★2026-10-06 用户裁定: 总资金 100U / 每单保证金回到 5U（配合 25x → 名义 ≈125U）
# 杠杆: sim 接口【不能设置杠杆】→ 以【你在 WEEX App 里给该合约设的杠杆】为准。
#   下面的值只是"首单"用的假设值; 开仓成交后会从持仓返回的 leverage 自动校正并写入 state。
WEEX_LEVERAGE = {"BTC-USDT-SWAP": 25, "XAU-USDT-SWAP": 25}
#   ★2026-10-06 用户已在 WEEX App 手动改为 25x → 此处同步(config 与 state["weex_leverage"] 两处都要)
#   25x 的含义: 名义 = 保证金 × 25（5U → 125U；原 100x 是 500U）。
#   好处: 爆仓价距进场由 ~0.7% 放宽到 ~2.8% → 结构止损再也不会"还没打到就先爆仓"。
#   副作用: 同样 5U 保证金，盈亏的【美元幅度】缩到 1/4 →
#           止盈不能再用"固定浮盈 10U"(25x 下 10U 浮盈 = 价格要走 8%!)，改用笔记的
#           "前方流动性目标"; 若要维持原美元波动，需把每单保证金从 5U 提到约 20U。
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
# ★2026-10-05 按笔记《BOS和CHOCH概念》分层: 高周期用大 swing 定【Swing 方向】, 低周期用小 swing 做【Internal 结构】。
#   笔记建议: 高时间框架 Swing Length 10~15 ; 低时间框架(15m/5m) 2~5。
#   (运行期会被 STRATEGY_PROFILES[*].swing_htf/swing_ltf 覆盖, 两处必须一致)
SWING_LEN_HTF = 10    # 1H(背景/定方向) 的 swing_length
                      # ★2026-10-05 90天实测选档(其余口径: 内部确认门k=4 + 止盈浮盈10U):
                      #   1H=4(旧) 127笔/净-26.09U → 1H=10 【99笔/净+40.88U/每笔+0.413/胜率18.2%】(最优,首次转正)
                      #   → 1H=12 105笔/+33.75U ; 1H=15 102笔/+1.28U ; 15m=2 211笔/-64.91U(太细=噪声)
SWING_LEN_LTF = 4     # 15m(入场/Internal) 的 swing_length
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
