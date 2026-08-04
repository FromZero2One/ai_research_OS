---
name: ai-research-os-session
description: AI Research OS 进度快照 — 完成度、已知限制、下一步、机器环境
metadata:
  type: project
---

# AI Research OS — 进度快照

## 位置
`/home/wsm/codes/ai_research_OS/`

## 变更日志
- **2026-08-04**: 目录与模块清理 — 删 `scripts/`、顶层 `data/`；`docs/superpowers/` → `docs/design/`(归档)；删 core 死代码 `security.py`/`aggregate.py`/`news_fetcher.py`，`crud.py` → `market/`；新增 `backend/README.md`/`frontend/README.md`，USAGE 瘦身。测试 125 passed。
- **2026-08-01**: 文档与代码对齐，前端 Vue 3 完成度约 80%。

## 完成度（按模块）

| 模块 | 完成度 | 现状 |
|------|:---:|------|
| 公司中心 | ~90% | CRUD/搜索/标签/Thesis/工作区/自选全可用 |
| 市场中心 | ~75% | A股行情/财务/估值可用；美股为合成数据占位（yfinance 受代理限制） |
| 文档中心 | ~90% | 上传→后台索引→表格结构化→关联公司全链路；OCR 明确 V1 不做 |
| 知识中心 | ~90% | 混合 RAG + Reranker + 中文检索优化 + 文档问答（模型切换）+ 评估集 |
| AI 中心 | ~80% | 模板/摘要后端全；工作流前端 UI 未做 |
| 研究中心 | ~90% | 会话/计划/证据/报告/决策/时间线/一键研究全链路 |
| 投资组合 | ~40% | 自选已并入公司；持仓/日志仅后端，前端待 V2 |
| 系统/调度 | ~85% | 调度/观察/任务/事件/新鲜度可用；newsnow 依赖外部路径 |

总体：V1.1 目标基本达成，V2 未启动，单用户本地工具（无认证）。

## 已知未完成 / 受限
- 美股真实行情（yfinance 被代理限制）
- 持仓/投资日志前端（后端就绪，随 V2 P&L 提供）
- AI 工作流前端 UI
- OCR（扫描版 PDF，V1 明确不做）
- 机器绑定配置：akshare_mcp 目录、newsnow 路径、MySQL 凭据、HF 模型缓存

## 下一步优先级
1. 美股数据打通（yfinance 直连/代理配置）
2. 持仓/日志前端（后端现成）
3. V2 方向：Auto Research 或 P&L 追踪

## 环境要点
- 本机代理 `socks://127.0.0.1:7890`：后端启动时 `clean_proxy_env()` 清理，脚本需自行调用；HuggingFace 下载走 `HF_ENDPOINT=https://hf-mirror.com`
- akshare 走独立 `akshare_mcp` venv 子进程（ticker 经环境变量传递）；云端 MCP 层默认禁用（`AKSHARE_CLOUD_MCP_URL` 留空）
- 外部数据源路径均可在 `backend/.env` 覆盖（AKSHARE_MCP_DIR / NEWSNOW_MCP_SERVER_PATH / AKSHARE_MYSQL_*）

## 相关文档
- **启动命令** → [`USAGE.md`](../USAGE.md)「服务启动与停止」
- **关键设计决策** → [`README.md`](../README.md)「Key Design Decisions」
- **架构设计史** → [`docs/design/architecture-optimisation.md`](../docs/design/architecture-optimisation.md)
