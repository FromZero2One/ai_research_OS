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
- **2026-10-14**: 数据分工原则落地（接口管"数"，PDF 管"事"）。**完成**: ② 文档 chunk content_type 打标（document/content_classifier.py 纯函数 + chunk 列 + Qdrant payload + /knowledge/search?content_type= 过滤，BM25 sparse 过滤顺带修复了原 doc_type 参数未生效的缺口）；③ 报告双轨（Evidence 加 content_nature 列，LLM 批量分类带 nature，report prompt 双轨规则，证据条目带 [ev:id]，ResearchDetail.vue 报告内联引用可点击回跳证据卡+高亮）；④ structured_facts 交叉验证（research/fact_validator.py 纯函数，偏差≥10% → Observation(attention) 口径差异事件）；① 报告 prompt 规则"数字只准用已核实事实/Market 区块"。迁移 d5e7a9c1b3f4（chunk content_type + evidence content_nature）。新增单测 test_content_classifier(7) + test_fact_validator(9)。测试 150 passed / 5 failed（既有环境：无 Ollama embeddings；本机 jieba 装的是残缺 0.34 版无 lcut，BM25 不可用，待修环境）。前端 build+vue-tsc 绿。
- **2026-10-13**: 分析师优化方案（先砍后补）。**砍**: AI 工作流（drop ai_workflows 表，0d04258）、akshare MySQL 镜像层（A股改 akshare 子进程直连，bac6cf3）、合成数据种子脚本（10e324b）。**补**: 数据覆盖矩阵（ae90779 + 单测 c3ef444）。另: 迁移补齐 morning_briefs/observations（8208cea）、LLM 切 DeepSeek 云端并完成分类评测（deepseek-chat 15/15=100% vs 关键词基线 26.7%）、plan_type 贯通快速研究（67a138f）、token 用量统计、period_compare（YoY/QoQ/同业中位）、ReportCharts 可视化、start-dev.cmd 一键启动、三份文档架构同步（5894dda）。全套测试 132 passed / 5 failed（失败均为无 Ollama embeddings 的环境依赖）。
- **2026-08-05**: 修 K 线刷新不更新（PRICE_STALE_DAYS 陈旧镜像问题，该问题已随 MySQL 层移除而消失）。
- **2026-08-04**: 目录与模块清理，测试 125 passed。

## 完成度（按模块）

| 模块 | 完成度 | 现状 |
|------|:---:|------|
| 公司中心 | ~90% | CRUD/搜索/标签/Thesis/自选全可用；搜索范围为自建公司库（PG） |
| 市场中心 | ~85% | A股行情/财务/估值 akshare 直连全链路 + 数据覆盖矩阵；美股 yfinance 备选 |
| 文档中心 | ~90% | 上传→后台索引→表格结构化→关联公司全链路；OCR 明确 V1 不做 |
| 知识中心 | ~90% | 混合 RAG + Reranker + 中文检索优化 + 文档问答 + 评估集 |
| AI 中心 | ~75% | 模板/摘要/提取/Token 用量统计；AI 工作流已移除（单用户用不上） |
| 研究中心 | ~92% | 全链路 + plan_type 四模板 + LLM 证据分类 + 多周期/同业比对 + 报告可视化 |
| 投资组合 | ~40% | 自选已并入公司；持仓/日志仅后端，前端待做 |
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

1. **比率层 + 历史分位**（下一项，未开始，完全建立在接口数据上）
   - 基于标准枚举指标计算派生比率：毛利率/净利率/ROE/资产负债率/周转率
   - PE/PB 历史分位：akshare `stock_a_indicator_lg` 历史序列入 PG 后算分位
   - 产出：`market/ratio_service.py`（纯函数可单测）+ 报告上下文区块 + 前端展示
2. **覆盖矩阵加定性维度**（未开始）
   - coverage 矩阵扩展"定性覆盖"：该公司是否有已索引年报正文（mda/risk 章节存在）
3. **跨会话证据继承**（未开始，方案不变）
   - 新 session 带入同公司历史已核实证据，标 `inherited`（gather_service + Evidence 来源标记）
4. **差异日报**（未开始，方案不变）
   - 晨报只报变化（新公告/财报日临近/价格异动/证据冲突），brief_generator + observation_engine

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
- 迁移 head：`d5e7a9c1b3f4`（chunk content_type + evidence content_nature）
- pytest 需先起 docker postgres；测试库 airesearch_test 由 conftest 用 create_all 重建（**改模型后旧测试库不会自动加列，需 DROP DATABASE airesearch_test 重建**）；`tests/test_session` fixture 为服务级测试专用（勿用 managed_session，会写进开发库）

## 相关文档
- **启动命令** → [`USAGE.md`](../USAGE.md)「服务启动与停止」
- **架构与配置** → [`backend/README.md`](../backend/README.md)
- **下一步方案细节** → [`README.md`](../README.md)「Roadmap」
