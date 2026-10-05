# 🌙 暗夜猎手 NightHunter

> 森林查尔斯 SMC 价格行为课程的规则实现 —— 自动盯盘 + **WEEX 模拟盘**交易引擎

- **策略**：1H 定方向 → 15m 回踩 FVG → Internal 结构确认（逆势 CHoCH → 顺势 BOS）
- **品种**：BTC / XAU（黄金）
- **数据源**：信号与回测 = **WEEX 合约**；交易 = **WEEX 模拟盘**（历史曾用 OKX，已于 2026-10-04 整体切换）
- **运行**：GitHub Actions（`watch.yml`，由 cron-job.org 每 15 分钟触发）

## 目录结构

```
trading_agent/
├── engine/                ★ 引擎代码
│   ├── config.py          配置中心（口径单一事实来源）
│   ├── structure.py       结构引擎（开源库 smartmoneyconcepts + 分层 swing + CHoCH只预警）
│   ├── liquidity.py       流动性/FVG（开源库 fvg + 截取检测）
│   ├── entry.py           入场模板（1H方向 → 15m回踩FVG → Internal 确认）
│   ├── exits.py           出场管理（保本 / 移动止损 / 浮盈按币数量计）
│   ├── risk.py            风控门
│   ├── weex_client.py     WEEX 合约行情（信号/回测数据源）
│   ├── weex_trade.py      WEEX 模拟盘客户端（签名/下单内联TP-SL/条件单）
│   ├── weex_broker.py     WEEX 适配层
│   ├── main.py            主循环（引擎侧兜底出场 + 交易 + 推送 + 日报）
│   ├── reports/           运行日报归档（engine/reports/运行日报_YYYYMMDD.md）
│   └── state.json         运行状态（由 Actions 每轮提交持久化）
├── tools/                 工具脚本（回测 / 频率扫描 / 诊断 / 知识库同步）
├── deploy/                文档源文件（说明书、代码合集、部署手册）
└── .github/workflows/     watch.yml（主引擎）/ mirror_weex.yml（API不可达时的K线镜像）
```

## 关键设计

1. **只用课程体系**：结构 / 流动性 / FVG —— **不引入任何传统指标**（均线、MACD、布林带等）
2. **持仓保护不依赖交易所条件单**：该模拟盘条件单会自行消失 → 由引擎每轮巡检（15m 触价 + 交易所真实浮盈 ≥10U）市价平仓
3. **状态持久化**：`engine/state.json` 每轮 git commit；**严禁**为它配置 `actions/cache`（会复活陈旧的持仓状态）
4. **无未来函数**：实盘入口剔除未收盘 K 线；swing/BOS 判定带 `SMC_STRICT_CAUSAL` 守卫

## 文档（知识库 wind）

| 文档 | 位置 |
|---|---|
| 信号逻辑说明书（规则总纲） | `02-规则库与提取结论` |
| 课程规则库（校准稿 v2） | `02-规则库与提取结论` |
| 代码合集（最新） | `03-代码与部署` |
| 部署手册（WEEX 版） | `03-代码与部署` |
| 运行日报 | `05-运行日报` |
