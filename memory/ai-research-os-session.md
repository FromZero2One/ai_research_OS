---
name: ai-research-os-session
description: AI Research OS 实现进度 — 8 中心 + Core，后端 132 py 文件 / 15.7k 行，前端 24 文件 / 3.1k 行，测试 125 通过
metadata:
  type: project
---

# AI Research OS — 进度快照

## 位置
`/home/wsm/codes/ai_research_OS/`

## 完成状态
- **后端**：132 个 py 文件，约 15.7k 行（不含 .venv）；**前端**：24 个文件，约 3.1k 行（Vue 3 + Element Plus + TanStack Query）
- **基础设施**：PostgreSQL(pgvector) + Qdrant + Redis + Ollama(bge-m3 / qwen3.5 等)
- **全量测试**：125 passed / 0 failed（专用 `airesearch_test` 库 + 隔离 `documents_test` Qdrant 集合）
- **主线功能**：公司中心（自选已并入，is_active 即关注）、市场中心、文档中心（后台异步索引 + PDF 表格结构化）、知识中心（混合 RAG + Reranker + 中文检索优化 + 文档问答/模型切换）、AI 中心、研究中心（一键研究 + 时间线 + 中文状态）、投资组合（仅自选页，持仓/日志待 V2）

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

总体：V1.1 功能目标基本达成（后端 ~85-90%、前端 ~80%），V2 未启动，生产化程度低（单用户本地工具，无认证）。

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

## 关键决策
- 依赖单向向上: Research → Knowledge → Document → Company；Core 层只放 Protocol，实现在 adapters/
- 自选列表 = 公司 is_active（消除两套列表重复）；持仓/日志后端就绪，前端待 V2(P&L)
- 财报 PDF 表格按词坐标重建为 Markdown（保留集团/母公司列组），整块入库避免表头丢失
- 问答默认 DeepSeek，可切本地 Ollama；Ollama qwen3 系列默认 `think=false`（思考链会吃光 token 预算）

## 启动
```bash
# 1. docker compose -f docker/docker-compose.yml up -d
# 2. cd backend && ALL_PROXY= all_proxy= PYTHONPATH=. .venv/bin/python -m uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
# 3. cd frontend && npm run dev   # http://localhost:5173
```
