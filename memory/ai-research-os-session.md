---
name: ai-research-os-session
description: AI Research OS 进度快照 — 完成度、已知限制、下一步、机器环境
metadata:
  type: project
---

# AI Research OS — 进度快照

## 位置
`E:\Project\ai_research_OS\`（Windows；旧机器路径 /home/wsm/codes/... 已废弃）

## 变更日志
- **2026-10-24（失败告警 + 调度状态/立即运行 + CSV 导出）**: run 失败（手动/定时）与定时任务自身异常经同一 Webhook 推送失败摘要；新增 `GET /screener/schedule`（cron/预设/下次运行/Webhook 只读状态）、`POST /screener/schedule/run`（持久任务 `screener_schedule`，202/409，不阻塞 HTTP）、`GET /screener/runs/{id}/export`（UTF-8 BOM CSV）。前端选股页新增「定时任务」卡片（状态/下次运行/立即运行）与历史运行「CSV」按钮。screener + financial_sync 298 passed。
- **2026-10-24（近似命中）**: 报告新增「附：近似命中（仅差 1 条规则）」：`screening.evaluate_near_misses` 找出恰好失败 1 条规则且无缺失数据的票（按市值降序前 10），union 模式经 `compose.evaluate_near_misses_by_preset` 逐预设判断去重并标注预设；不影响候选池/推荐。`_rule_hit` 重构出 `_rule_value` 复用指标取值。测试补近似命中与报告分区。
- **2026-10-24（运行取消）**: 新增 `POST /screener/runs/{id}/cancel` + `screener/cancel.py` 进程内取消事件；状态机新增 `cancelling`/`cancelled`。worker 在行情拉取后、财务补采后、进入深判前、每只深判开始前、报告生成前检查取消；`judge_candidates(should_stop=...)` 取消剩余 asyncio 任务。排队中的 run 启动时直接收尾；已结束 run 取消返回 409、重复取消幂等。前端历史运行表新增「取消」按钮，状态映射补 cancelling/cancelled。screener + financial_sync 292 passed。
- **2026-10-24（变化日报 Webhook）**: 新增 `screener/notify.py`：定时选股变化日报生成后推送群机器人摘要（企微/飞书/钉钉/通用 JSON），配置 `SCREENER_WEBHOOK_URL`/`SCREENER_WEBHOOK_FORMAT`/`SCREENER_WEBHOOK_NOTIFY_ON`（changes|always）；业务错误码与网络异常只记日志、不阻断调度。`build_run_diff_data` 额外返回变化详情供通知使用，原 `build_run_diff` 签名不变。screener + financial_sync 287 passed。
- **2026-10-24（选股 → 研究中心交接）**: 新增 `screener/handoff.py`：`POST /screener/runs/{run_id}/to-research` 把该轮推荐股（按置信度排序，默认 5 只，可传 `tickers`/`limit`）创建为研究中心会话（`auto_plan=False`，tag `["screener", run_id]`，metadata 记录 `screener_run_id`/`screener_ticker`，已创建过则跳过）；前端历史运行表新增「送入」按钮。顺带修复 `ResearchSession.tags` 类型不一致（模型注解/响应 schema 原为 dict，实际 service 存 list[str]，导致有 tags 的会话详情 500），统一为 `list[str]`（JSONB 列不变，无需迁移）。screener + financial_sync 281 passed；research 22 passed / 2 既有失败（证据继承依赖本地 LLM）。
- **2026-10-24（知识库空提示）**: 含定性标准的 run 会检查已索引文档数；为 0 时日志告警并在报告概览写明“知识库为空，定性标准会判数据不足”，并指向文档中心上传/索引流程。纯量化预设不受影响。screener + financial_sync 279 passed。
- **2026-10-24（表现基准）**: 推荐后表现接口新增沪深300 T+1 同期限收益、基准与超额列；修复 `backtest_data.fetch_index_daily` 的既有 import/解析错误（`_AKSHARE_PROLOGUE`/`_run_child` 来源错误、返回 list 被当字符串）；基准不可用时自动省略。screener + financial_sync 278 passed。实跑基准入口 2026-10-23 收盘 4105.329。
- **2026-10-24（回测风险指标）**: `compute_nav_and_stats` 新增基准 CAGR、年化超额、年化波动、Sharpe、Sortino、Calmar（季度收益年化 ×√4，无风险利率 `BACKTEST_RISK_FREE_RATE` 默认 2%）；回测报告展示全部指标；screener + financial_sync 277 passed。样例报告：CAGR 25.78%、基准年化 1.74%、超额 +24.03%、Sharpe 1.08、Sortino 2.29、Calmar 2.58。
- **2026-10-24（组合构建）**: 新增 `screener/portfolio.py` 纯函数（equal/score/confidence 加权，单票/行业上限，冲突时保留现金，不做杠杆）；API `POST /screener/runs/{id}/portfolio`；前端历史运行表新增「组合」按钮与参数面板、持仓表。screener + financial_sync 275 passed。实跑核心资产 13 推荐：等权 7.69%/只，电子行业触及 35% 上限，保留 3.5% 现金。
- **2026-10-24（行业专属指标）**: 指标库 33→42；银行侧净息差、不良贷款、贷款总额、不良率、拨备率、一级资本充足率；保险侧净投资收益率、已赚保费、偿付能力充足率；新增「银行价值」「保险价值」预设（共 8 套）；SW 一级行业把保险与券商同归“非银金融”，服务层用 F10 贷款/保费字段区分 `financial_type`，银行/保险预设只筛对应子行业；迁移 `c7d8e9f0a1b2`；screener + financial_sync 268 passed。实跑：银行预设 8 家全部银行；保险预设 5 家全部险企。
- **2026-10-24（因子深度）**: 指标库 24→33；新增 F10 直接指标 ROIC、利息保障倍数、现金比率、FCFF、现金流/营业利润、实际税率、有息负债率，以及派生 PEG、FCF 收益率；核心资产/GARP 加 `roic>10`，深度价值加 `fcf_yield>0`，高成长加 `peg<2`；F10 2026Q2 重灌 5,739 家（ROIC 5,635、FCFF 5,635、利息保障 5,367）；回测历史财务补拉加入 F10 主要指标；迁移 `b6c7d8e9f0a1`；screener + financial_sync 261 passed。实跑：核心资产 13 候选；临时 `fcf_yield>3 & peg<1.5` 预设选出 50 只。
- **2026-10-24（三态结论 + 置信度）**: `ScreenerJudgement.verdict` 新增 recommend/reject/insufficient/failed（迁移 `a5b6c7d8e9f0`）；证据守卫/资料不足/低置信度 → insufficient，显式不满足 → reject；报告拆分「未通过标准」与「数据不足」，API 透出 verdict；新增 `SCREENER_MIN_CONFIDENCE`（默认 0）。screener + financial_sync 258 passed。实跑临时护城河预设：7 候选全部 insufficient、0 推荐，报告两个分区正常。
- **2026-10-24（LLM 深判评测）**: 新增 `screener/eval/judge_cases.jsonl`（10 用例：无资料文档类、财务可验证、带资料引用、混合标准）+ `screener/judge_eval.py` + `scripts/eval_judge.py`；指标 JSON 合法率/推荐匹配/证据违规/自动降级/平均耗时，报告落 `screener/reports/eval-judge-*.md`。本地 qwen3.5-q4 实跑：10/10 JSON 合法、7/7 推荐匹配、0 证据违规、平均 9.1s。screener + financial_sync 257 passed。知识库仍为 0 文档，评测使用受控片段，不依赖生产知识库。
- **2026-10-24（行业相对排名）**: 新增 `screener/industry_ranking.py`：候选在行业内计算 ROE/营收增长/净利增长/现金流质量/PE/PB 分位（金融行业用 PE/PB/ROE），综合 `industry_score`；排序改为 得分 → 行业分位 → 市值；新增 `cap_by_industry` 单行业上限（`SCREENER_MAX_PER_INDUSTRY`，默认 8）；报告/深判上下文展示行业分位。screener + financial_sync 251 passed。实跑核心资产 13 候选，电子 5/医药 3/有色 2/其他 3，行业分位正常写入报告。
- **2026-10-24（推荐后表现跟踪）**: 新增 `screener/performance.py` 纯函数（1/3/6/12 月 + 当前收益）与 `performance_service.py`（T+1 收盘买入、等权汇总平均收益/胜率/样本数）；API `GET /screener/runs/{id}/performance`；前端历史运行表新增「表现」按钮与汇总/个股表；日线覆盖不足标记 `no_entry_price`。screener + financial_sync 245 passed。实跑 2026-10-22 运行：21 推荐，当前仅 4 只有本地日线（采集进行中），收益 0（10/23 为最新交易日）。
- **2026-10-24（回测 PIT + 交易费用）**: `market.financial_metrics` 新增 `announcement_date`（迁移 `f4a5b6c7d8e9`），yjbb 解析“最新公告日期”；历史 2025Q1–2026Q2 公告日覆盖 46,443/46,448（99.99%，回补脚本 `scripts/backfill_announcement_dates.py`）；回测 `_load_financials_by_period` 按公告日 ≤ 调仓日过滤（缺失公告日回退旧口径）；`compute_holding_returns` 支持 `cost_buy/cost_sell`，服务层计佣金万三 + 卖出印花税 0.05% + 单边滑点 0.1%；成交量为 0 视为停牌不可交易；回测免责声明更新；screener + financial_sync 241 passed。
- **2026-10-24（选股 P2：定时筛选 + 变化日报）**: 新增 `core/screener_schedule.py`，`SCREENER_SCHEDULE`（工作日 16:30）按 `SCREENER_SCHEDULE_PRESETS`（默认 core）运行预设，已有进行中 run 时跳过；每轮与同口径上一轮 completed run 对比（presets 用 mode/combine/preset_ids，freeform 用 criteria_hash），只输出新推荐/掉出推荐/新进候选/移出候选，Markdown 落 `screener/reports/*-diff-*.md` 并写 `screener.diff` 事件；API `GET /screener/runs/{id}/diff`；前端历史表新增「日报」按钮；手动触发 `POST /scheduler/run/screener_schedule`。screener + financial_sync 237 passed。实跑：core 13 候选，对比 17:52 基线无变化。
- **2026-10-24（选股 P1：TTM + 盈利质量）**: `valuation.py` 新增 `ttm_value`（上年年报 + 本期累计 − 上年同期；历史期缺失回退单期年化），PE/PS 改用 TTM；新增 `cfo_to_ni`（TTM 现金流/净利润）、`cfo_to_revenue`、`accrual_ratio`（应计比率）三个质量指标；指标库 21→24；核心资产/GARP 加 `cfo_to_ni>0.8`、深度价值 `>0.7`、高成长 `>0.5`；回补 2025Q1–Q4 财务（`scripts/backfill_financial_periods.py`）；迁移 `e3f4a5b6c7d8`；screener 232 passed。实跑：核心资产候选 18→13；临时质量预设 `cfo_to_ni>1.2 & pe<20` 选出 50 只；茅台 cfo_to_ni 1.46、应计 -12.2%。
- **2026-10-24（选股 P0：股票池卫生 + 行业隔离）**: ①`pool.py` 入口统一过滤 ST/*ST/退市、停牌/无行情、换手率<0.05%、市值<10亿，报告新增「股票池卫生过滤」统计（实跑排除 ST 196 只、停牌 3 只）；②新增 `market.stock_industry` 表（迁移 `c1d2e3f4a5b6`），申万一级 31 行业为主 + 新浪补缺，共 5,663 只（主板 2111/2111），候选携带 industry/sector，报告/深判上下文展示行业；③行业隔离：工业预设自动排除金融股，新增内置「金融价值」预设（pb<1.5、pe<10、roe>8、市值>100亿，迁移 `d2e3f4a5b6c7`），金融预设只选银行/非银金融；④screener 测试 226 passed。实跑：核心资产 18 候选全部 industrial；金融临时预设 50 候选全部银行/非银金融。
- **2026-10-24（Screener 优化 5 阶段）**: ①深判 `max_tokens` 1024→2560（截断重试 3584+压缩提示），上下文金额统一亿/万、比率带单位，净利润/ROE/毛利率越界加异常提示，报告市值/价格格式化；②freeform 指标白名单对齐真实入库指标（移除 gross_profit/operating_profit/rd_expense/total_equity），无数据指标自动降级为定性条目，所需指标全市场零覆盖时 run 显式失败；新增 `value_unit`（元/万/亿/%/倍）服务端换算，修掉“100亿→100”单位错误；③深判接入 KnowledgeService 检索（hybrid、无 reranker），新增确定性证据守卫：无资料时文档类命中降级、财务类要求 evidence 含数字、有资料必须引用 `[n]`，任一条降级即 recommend=False 且置信度≤0.4；无定性标准时跳过 LLM（auto-pass）；④状态分阶段提交（screening/judging/completed 可见）、前端自动接管进行中 run、union 收集缺失数据名单、预设报告补个股理由、标准条目前缀归一化去重；触发后立即提交 run 行（修 POST→GET 404 竞态）；⑤新增 PE/PB/PS 派生估值（市值/年化净利、市值/净资产、市值/年化营收）与内置预设估值条件（深度价值 pe<25/pb<3，GARP pe<40，周期反转 pb<2.5）；`core/financial_sync.py` 挂工作日 3:15 财务数据刷新。迁移 head `b7c8d9e0f1a2`；全量 391 passed / 2 failed / 2 skipped（失败为既有 research 证据继承依赖本地 LLM 结构化输出问题），screener + financial_sync 专项 214 passed，前端 build 绿。A股主板行情采集累计 259/2111 只（1,822,820 行），按 10 只/批后台续采。**注意**：知识库当前 0 文档，含定性标准的四套预设会稳定 0 推荐（数据不足），核心资产/纯量化预设正常。
- **2026-10-23（Screener 预设回测 MVP + A股主板数据采集）**: `POST /screener/backtests`（preset_id + years 1-10，409 防并发）+ `GET /screener/backtests/{id}`。数据层 `backtest_data.py`：外部 MySQL 前复权日线（`BACKTEST_MYSQL_URL` 仅存 .env；同票同日重复行去重；本地 `market.stock_prices` 加 (ticker,date) 唯一约束、幂等灌库）+ 历史财务缺失期按需补拉（SAVEPOINT 隔离）+ 沪深300 基准。核心 `backtest.py` 纯函数：调仓日 = 披露截止日后首个交易日、**4 月调仓统一用上一年年报**（无未来函数）、停牌收益 0 标注、净值/CAGR/最大回撤/年度胜率。编排 `backtest_service.py`（状态机 pending→running→completed/failed，持久任务 `screener_backtest`）+ `backtest_report.py`（Markdown 报告含免责声明：未计费用、近似市值、幸存者偏差）。result 形状 `{summary, yearly}`。迁移 `f7a9c3e1b5d2` + `a1b2c3d4e5f6`。票池本地空时取外部库 distinct symbol（含退市票）。**日线拉取为逐只「边拉边灌」模式**（单票一次查询 ~1200 行、立即落库 commit，本地表行数即真实进度；≥200 根视为完整可断点续传；单票瞬时网络错误重试 3 次退避；全市场 ~18 分钟）。测试：models 2/2 + data 7/7 + core 12/12 通过，api 2/3（1 个待查）、回归 screener_api 5/5；端到端真实冒烟完成度 ~4%（5273 只拉取正常，整体验证待后续重跑）。
- **2026-10-23（A股主板数据采集）**: 通过 akshare 新浪源获取全市场 A 股 5,576 只（sz:2,906 / sh:2,317 / bj:353），其中主板 2,111 只（沪市主板 1,700 + 深市主板 411）。股票代码已批量落库 `company.companies`（is_active=false, priority=999，2,111 条）。行情采集脚本 `ingest_main_board_batch.py` 支持分批（--limit N）、中断恢复（自动跳过已有 >=200 行的股票），每只约 40–60 秒。当前已采集 **94 只**（约 653,003 行，1991–2026-10-23），覆盖 000001–000166 及 600036/600276/600519 等。美股（yfinance）需代理，本地无法直连。
- **2026-10-22（Screener 数据补全）**: F10 主要指标全市场采集（`RPT_F10_FINANCE_MAINFINADATA`：`LD`/`SD`/`TOAZZL`/`CHZZL`/`YSZKZZL`/`EPSJB` + 营收/净利同比，A 股前缀过滤）；yjbb 补 eps/营收同比/净利同比映射；新增 revenue_growth / net_income_growth 指标与迁移 `e2b6f4a8c9d1`；高成长预设改用营收/净利同比（>20%）；报告概览标注财务数据截至。实跑：深度价值 50 候选/21 推荐，高成长 106 候选；current_ratio/quick_ratio 覆盖 98.2%。全套 305 passed / 2 failed（research 证据继承依赖真实 light-tier LLM 的预存环境问题，非本次改动）。
- **2026-10-21**: LLM 智能选股器（Screener）。新模块 `backend/screener/`：用户维护 `screener/criteria.md` 自然语言标准，`POST /screener/runs` 手动触发 → LLM 翻译标准（`ScreenerRule` doc_hash 缓存）→ 确定性初筛（akshare 全市场快照 `stock_zh_a_spot_em` + 股票池过滤 + 量化规则）→ LLM 逐只深判（单只失败隔离，落 `ScreenerJudgement` 备将来回测）→ Markdown 报告（`screener/reports/`，含标准吻合度逐条说明）。新表 screener.screener_runs/judgements/rules（迁移 `b5d2f8a3c6e1`，head）。前端 `/screener` 页（标准编辑 + 触发 + 报告渲染）。v1 不接知识库检索与定时触发；模拟盘明确排除（用户手动）。
- **2026-10-16**: 跨会话证据继承。auto-gather 第 6 步带入同公司已完成会话证据（`_select_and_inherit`，上限 10 条 + 去重 + 幂等，不走 LLM 二次分类）；Evidence 新列 `inherited_from_session_id`（迁移 `a9c4d7e2f1b8`）；前端「📥 历史已核实」徽标跳原会话。auto_gather 响应新增 inherited_added。
- **2026-10-15**: 比率层 + PE/PB 历史分位 + 覆盖矩阵定性维度。新增 `market/ratio_service.py`（compute_ratios/percentile_rank 纯函数 + RatioService + build_ratio_block 报告区块）、新表 `market.valuation_history`（估值历史，PE/PB 分位源，akshare `stock_a_indicator_lg` 兜底采集）、`GET /market/ratios/{ticker}[/valuation-percentile]` 端点、公司详情页比率卡片、覆盖矩阵定性覆盖维度（row.qualitative，年报正文 mda/risk 切片）+ Market.vue 定性列。迁移 head `f3a8c2e1b7d9`。回归 168 passed / 4 failed（均预存 Ollama embeddings 环境依赖）。
- **2026-10-14（瘦身）**: 分析师评价驱动的功能瘦身。**删**: 旧晨报全链路（core/brief_generator.py + core/morning_brief.py + scheduler 任务 + dashboard /brief /generate-brief 路由 + Dashboard/System 前端卡，给"差异日报"让路）；macro_indicators 表（有表无链路死数据，模型+domain entry+迁移 drop）；RAG 评估脚本（scripts/eval_retrieval.py + eval_classifier.py）；AI 中心摘要/提取（/ai/summarize /extract + service 方法 + 前端演示卡；保留 prompt_templates 表 + /ai/generate 模板执行 + /ai/usage——knowledge_ask 覆盖机制依赖模板表）。迁移 e8a2c4f6b9d1。公司中心/观察引擎/Portfolio 后端经依赖分析保留（承重墙）。
- **2026-10-14**: 数据分工原则落地（接口管"数"，PDF 管"事"）。**完成**: ② 文档 chunk content_type 打标（document/content_classifier.py 纯函数 + chunk 列 + Qdrant payload + /knowledge/search?content_type= 过滤，BM25 sparse 过滤顺带修复了原 doc_type 参数未生效的缺口）；③ 报告双轨（Evidence 加 content_nature 列，LLM 批量分类带 nature，report prompt 双轨规则，证据条目带 [ev:id]，ResearchDetail.vue 报告内联引用可点击回跳证据卡+高亮）；④ structured_facts 交叉验证（research/fact_validator.py 纯函数，偏差≥10% → Observation(attention) 口径差异事件）；① 报告 prompt 规则"数字只准用已核实事实/Market 区块"。迁移 d5e7a9c1b3f4（chunk content_type + evidence content_nature）。新增单测 test_content_classifier(7) + test_fact_validator(9)。测试 150 passed / 5 failed（既有环境：无 Ollama embeddings；本机 jieba 装的是残缺 0.34 版无 lcut，BM25 不可用，待修环境）。前端 build+vue-tsc 绿。
- **2026-10-13**: 分析师优化方案（先砍后补）。**砍**: AI 工作流（drop ai_workflows 表，0d04258）、akshare MySQL 镜像层（A股改 akshare 子进程直连，bac6cf3）、合成数据种子脚本（10e324b）。**补**: 数据覆盖矩阵（ae90779 + 单测 c3ef444）。另: 迁移补齐 morning_briefs/observations（8208cea）、LLM 切 DeepSeek 云端并完成分类评测（deepseek-chat 15/15=100% vs 关键词基线 26.7%）、plan_type 贯通快速研究（67a138f）、token 用量统计、period_compare（YoY/QoQ/同业中位）、ReportCharts 可视化、start-dev.cmd 一键启动、三份文档架构同步（5894dda）。全套测试 132 passed / 5 failed（失败均为无 Ollama embeddings 的环境依赖）。
- **2026-08-05**: 修 K 线刷新不更新（PRICE_STALE_DAYS 陈旧镜像问题，该问题已随 MySQL 层移除而消失）。
- **2026-08-04**: 目录与模块清理，测试 125 passed。

## 完成度（按模块）

| 模块 | 完成度 | 现状 |
|------|:---:|------|
| 公司中心 | ~90% | CRUD/搜索/标签/Thesis/自选全可用；搜索范围为自建公司库（PG） |
| 市场中心 | ~90% | A股行情/财务/估值 akshare 直连全链路 + 数据覆盖矩阵（含量性维度）+ 比率层 + PE/PB 历史分位；美股 yfinance 备选 |
| 文档中心 | ~90% | 上传→后台索引→表格结构化→关联公司全链路；OCR 明确 V1 不做 |
| 知识中心 | ~90% | 混合 RAG + Reranker + 中文检索优化 + 文档问答 + 评估集 |
| AI 中心 | ~75% | 模板/摘要/提取/Token 用量统计；AI 工作流已移除（单用户用不上） |
| 研究中心 | ~92% | 全链路 + plan_type 四模板 + LLM 证据分类 + 多周期/同业比对 + 报告可视化 |
| 投资组合 | ~40% | 自选已并入公司；持仓/日志仅后端，前端待做 |
| 智能选股 | ~97% | 42 指标（TTM 估值 + 现金流质量 + 因子深度 + 银行/保险专属）+ 8 内置预设；股票池卫生 + 行业隔离/相对排名；深判知识库/证据守卫 + 三态结论 + 评测器；预设回测；定时筛选 + 变化日报/失败告警 Webhook + 推荐后表现 + 组合构建 + 送入研究 + 运行取消 + CSV 导出 + 近似命中；财务数据工作日定时更新（2026-10-24） |
| 系统/调度 | ~85% | 调度/观察/任务/事件/新鲜度/覆盖矩阵/Token 用量卡片 |

总体：V1.1 达成，V2 按分析师优先级推进中（见下）。

## 核心数据分工原则（2026-10-14 定稿：接口管"数"，PDF 管"事"）
- **定量层** = Market 中心是数字唯一事实源：所有下游（报告上下文/图表/比率层）引用财务数字只能走 Market 接口数据，禁止从文档/证据文本抽数
- **定性层** = Document/Knowledge 管"事"：MD&A、风险、公告、附注等正文内容；财报 PDF 表格降级为验证用途
- **structured_facts = 质检器**：与 Market 接口值交叉比对，口径差异生成观察事件，不进报告数字链路
- 报告双轨：数字论断引用 Market 区块禁止改写；定性论断内联 `[ev:id]` 回跳证据

## 下一步优先级（2026-10-14 更新，按此顺序继续）

### 已完成（2026-10-14，勿重做）
- ✅ 文档 chunk content_type 打标（classifier 纯函数 + 检索过滤）
- ✅ 报告双轨 + 引用回溯（content_nature + [ev:id] 内联 + 前端回跳）
- ✅ structured_facts 交叉验证（fact_validator 纯函数 → Observation 口径差异）
- ✅ 定量唯一事实源规则（报告 prompt 数字只走已核实事实/Market 区块）

1. ✅ **比率层 + 历史分位**（2026-10-15 完成，迁移 head `f3a8c2e1b7d9`）
   - 基于标准枚举指标计算派生比率：毛利率/净利率/ROE/资产负债率/周转率
   - PE/PB 历史分位：akshare `stock_a_indicator_lg` 历史序列入 PG 后算分位
   - 产出：`market/ratio_service.py`（纯函数可单测）+ 报告上下文区块 + 前端展示
2. ✅ **覆盖矩阵加定性维度**（2026-10-15 完成）
   - coverage 矩阵扩展"定性覆盖"：该公司是否有已索引年报正文（mda/risk 章节存在）
3. ✅ **跨会话证据继承**（2026-10-16 完成，迁移 head `a9c4d7e2f1b8`）
   - 新 session 带入同公司历史已核实证据，标 `inherited`（gather_service + Evidence 来源标记）
4. **差异日报**（未开始，方案不变）
   - 晨报只报变化（新公告/财报日临近/价格异动/证据冲突），brief_generator + observation_engine

### 收尾小项（2026-10-15 最终 review 挂账，非阻塞）
- Market.vue 覆盖网格列数动态化（当前硬编码 `repeat(5, 90px)`，tracked_types 恒为 4+定性 才显示正确）
- test_finalize_session 补 LLM mock（finalize 走真实 LLM 无 mock/超时，测试挂起，现被 deselect）
- qualColor/qualLabel 硬编码色值 → 统一 CSS 变量
- akshare_executor subprocess 输出统一 `encoding='utf-8'`（消 Windows GBK 解码 warning）
- akshare_mcp venv 本机路径未配好 → A 股采集（含估值历史首次拉取）在本机不可用，分位端点降级 available:false

### 环境待修（本机）
- ~~jieba 残缺 0.34~~ 已修（2026-10-14 force-reinstall jieba 0.42.1，BM25 恢复）
- Embedding 指向未安装的 Ollama → 文档索引稠密向量不可用，4 项测试失败（预存，装 Ollama 或配 sentence-transformers 即消）

### 已完成（本轮，勿重做）
- ✅ 数据覆盖矩阵 — `GET /market/freshness/coverage` + Market 页卡片（缺口标 missing）

## 已明确放弃（勿再提议）
- multi-agent / trading agents / LangGraph DAG 工作流（单用户工具过度设计）
- akshare MySQL 中间层（子进程直连替代）
- 合成行情数据（研究工具宁缺毋假）

## 环境要点（本机 Windows）
- docker compose 栈：postgres/qdrant/redis（`docker/docker-compose.yml`）；一键启动 `start-dev.cmd`（依赖栈+后端:8000+前端:5173）
- LLM：DeepSeek 云端（.env OPENAI_* 已配，key 已 gitignore）；light tier 同走云端；本机无 ollama
- Embedding 仍指向本机 Ollama（未安装）→ 文档上传/知识检索的稠密向量不可用，BM25 兜底；pytest 有 5 项因此失败
- akshare 走独立 `akshare_mcp` venv 子进程（`AKSHARE_MCP_DIR` 指向旧机器路径，**本机需改 .env 并确认 venv 存在**，否则 A 股采集失败但不崩）
- 迁移 head：`c7d8e9f0a1b2`（银行/保险专属指标与预设）
- pytest 需先起 docker postgres；测试库 airesearch_test 由 conftest 用 create_all 重建（**改模型后旧测试库不会自动加列，需 DROP DATABASE airesearch_test 重建**）；`tests/test_session` fixture 为服务级测试专用（勿用 managed_session，会写进开发库）

## 相关文档
- **启动命令** → [`USAGE.md`](../USAGE.md)「服务启动与停止」
- **架构与配置** → [`backend/README.md`](../backend/README.md)
- **下一步方案细节** → [`README.md`](../README.md)「Roadmap」
