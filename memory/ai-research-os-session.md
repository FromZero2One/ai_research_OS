---
name: ai-research-os-v1-session
description: AI Research OS V1 架构实现进度 — 85个文件, 5800行, 7模块+Core, 后端通过, frontend npm installed
metadata:
  type: project
---

# AI Research OS V1 — 进度快照

## 位置
`/home/wsm/codes/ai_research_OS/`

## 完成状态
- **后端代码全部写完**: 85 个文件, 5800 行 (Python 4543 + TS/TSX 1289)
- **基础设施**: PostgreSQL + Qdrant + Redis (Docker)
- **数据库**: 表已创建, 8家样本公司 + 1个研究会话已 seed
- **已验证的 API**: Health ✅, Companies CRUD ✅, Research Workflow ✅ (create → evidences → finalize), AI Center ✅
- **Frontend**: npm install 已完成, 7个页面代码就绪

## 卡住的点
1. **SOCKS proxy** (`all_proxy=socks://127.0.0.1:7890`) 导致 Qdrant httpx 客户端初始化失败 — 需要 `export no_proxy=localhost,127.0.0.0/8,::1` 或安装 `httpx[socks]`
2. **sentence-transformers 未安装**: 需要约 2.2GB 下载
3. **`updated_at` 懒加载 fix**: 已部分修复 (research + company), 其他模块待补

## 下次启动顺序
```bash
# 1. docker compose -f docker/docker-compose.yml up -d
# 2. export no_proxy="localhost,127.0.0.0/8,::1"
# 3. cd backend && PYTHONPATH=. uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
# 4. (另一终端) cd frontend && npm run dev
```

## Key Decisions
- 依赖单向向上: Research → Knowledge → Document → Company
- Core 层只放 Protocol 接口, 实现在 adapters/
- Knowledge Center V1 = Hybrid RAG (Qdrant + BM25), 无 KG, 无 LlamaIndex
- AI Center 是能力层, 不是流程控制层
- Event Log 用于研究过程审计追踪
