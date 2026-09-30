# 🌙 暗夜猎手 NightHunter

> 森林查尔斯 SMC 交易课程规则实现的自动盯盘+模拟盘交易引擎

> 目标：把 B 站《森林查尔斯》交易课程的规则体系，实现为监控 XAU + BTC 的自动盯盘 + OKX 模拟盘交易引擎
> 立项：2026-09-28 | 数据源：OKX（正式运行）/ Gate.io（本地测试）

## 目录结构

```
trading_agent/
├── README.md              本文件（项目索引）
├── engine/               ★ 正式引擎代码（以后只维护这里）
│   ├── config.py         配置中心（10个待标定阈值集中管理）
│   ├── structure.py      结构引擎（BOS实体确认/CHoCH/盘整屏蔽/影线vs实体）
│   ├── liquidity.py      流动性模块（FVG/回踩/iFVG翻转/IFVG牛熊转换/双点截取）
│   └── test_engines.py   引擎验证脚本（Gate.io真实数据）
├── transcripts/          课程资产
│   ├── 规则库_森林查尔斯课程.md   ★★ 270条规则总纲（一切开发的依据）
│   ├── bv_list.json      22集视频清单
│   └── <BV号>/transcript.txt   22份带时间戳文字稿（24.8万字）
├── tools/                工具脚本
│   ├── bilibili_transcribe.py  B站单视频转录管线
│   ├── transcribe_all.py       目录级批量转写
│   ├── batch_pipeline.py       全合集后台流水线（即转即删）
│   ├── run_ep1.py              指定段补转
│   └── upload_batch.py         项目资产批量上传知识库
├── model/                ASR模型（paraformer int8 233MB，勿删）
└── legacy/               旧版资料（v1演示引擎/部署手册/数据源测试）
```

## 项目进度

- [x] 课程22集→文字稿（24.8万字，Paraformer本地转写）
- [x] 规则提取（270条：可代码化~140/待标定~60/不可~70）
- [x] 资产上传知识库"wind"（25个文件，防丢失）
- [x] Step1 核心引擎：结构+流动性（已用真实K线验证）
- [ ] Step2 入场模板 + 出场管理
- [ ] Step3 风控层 + 滚仓仓位
- [ ] Step4 OKX客户端 + 主循环
- [ ] Step5 本地逻辑验证
- [ ] Step6 部署（GitHub Actions）上线

## 关键决策记录

1. **课程体系=SMC价格行为流**，不使用传统指标（老师：MACD/布林带"基本是废的"）→ v1演示信号库（RSI/MACD/EMA7-25）已作废
2. **监控品种**：BTC 跑全套模块；XAU 只跑结构+流动性（无永续/无逐笔数据）
3. **10个量化阈值**课程未给 → 先用默认值，模拟盘跑数据后回标
4. **部署路径**：代码在 GitHub Actions 云端跑（海外节点可访问OKX）；Webhook/API密钥存 GitHub Secrets
5. **本地测试用 Gate.io**（沙盒可达），正式跑用 OKX（沙盒不可达，AWS/GCP节点可）

## 常用命令

```bash
# 引擎验证（拉真实行情跑结构识别）
cd trading_agent/engine && python3 test_engines.py
# 新视频转录
cd trading_agent/tools && python3 bilibili_transcribe.py <BV链接>
```
