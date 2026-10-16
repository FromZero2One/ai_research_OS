# 跨会话证据继承（Evidence Inheritance）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新研究会话执行 auto-gather 时，自动带入同公司历史已完成会话的证据并标记「历史已核实」，前端证据卡显示可跳转的继承徽标。

**Architecture:** 在 `GatherService.auto_gather` 末尾新增第 6 步（纯查询+插入，不重新走 LLM 分类/抽取）；`ResearchEvidence` 新增 `inherited_from_session_id` 外键列做标记；前端 ResearchDetail.vue 加徽标。规格见 `docs/superpowers/specs/2026-10-16-evidence-inheritance-design.md`。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic；pytest + TestClient；Vue 3 + Element Plus。

## Global Constraints

- 全中文注释/UI；注释风格与现有文件一致（中文 docstring + 行内说明）
- 迁移基于 head `f3a8c2e1b7d9`，新 revision id 用 `a9c4d7e2f1b8`
- 测试跑 pytest 需先起 docker postgres；**改模型后旧测试库不自动加列，测试前执行 `DROP DATABASE airesearch_test` 重建**（conftest 用 create_all）
- 本机 Python 3.14 全局环境（无 .venv），pytest 在 `backend/` 目录下运行（PYTHONPATH=. 已由 pytest.ini/pyproject 处理则直接 `python -m pytest`）
- 预存失败 4 项（Ollama embeddings 环境依赖）不算回归
- ruff --fix 慎用（会删当时未用的 import）；提交前只跑 `ruff check` 确认无新告警
- 继承证据**不**重新走 LLM 批量分类、事实抽取、交叉验证
- auto_gather 响应新增 `inherited_added: int` 字段

---

### Task 1: 数据模型列 + 迁移 + API 响应字段

**Files:**
- Modify: `backend/research/models.py`（ResearchEvidence，structured_facts 列之后，约 L113-115）
- Create: `backend/alembic/versions/a9c4d7e2f1b8_add_evidence_inherited_from.py`
- Modify: `backend/research/schemas.py:160-179`（EvidenceResponse）

**Interfaces:**
- Consumes: 现有 `ResearchEvidence`（research/models.py:54）、alembic head `f3a8c2e1b7d9`
- Produces: `ResearchEvidence.inherited_from_session_id: uuid.UUID | None`；`EvidenceResponse.inherited_from_session_id: UUID | None = None`（Task 2 的测试与前端依赖此字段出现在 API 响应中）

- [ ] **Step 1: 模型加列**

在 `backend/research/models.py` 的 `ResearchEvidence` 中，`structured_facts` 列定义之后（`# ----` 分隔注释前）加入：

```python
    inherited_from_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research.research_sessions.id", ondelete="SET NULL"),
        nullable=True,
        comment="继承自历史已完成会话的证据（非空即继承证据）",
    )
```

（`ForeignKey`、`UUID`、`uuid` 该文件已导入，无需新增 import。）

- [ ] **Step 2: 新建迁移文件**

创建 `backend/alembic/versions/a9c4d7e2f1b8_add_evidence_inherited_from.py`：

```python
"""add research_evidences.inherited_from_session_id

Revision ID: a9c4d7e2f1b8
Revises: f3a8c2e1b7d9
Create Date: 2026-10-16

证据继承：标记证据来自同公司历史已完成会话（非空即继承证据）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "a9c4d7e2f1b8"
down_revision: str | None = "f3a8c2e1b7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_evidences",
        sa.Column(
            "inherited_from_session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research.research_sessions.id", ondelete="SET NULL"),
            nullable=True,
            comment="继承自历史已完成会话的证据（非空即继承证据）",
        ),
        schema="research",
    )


def downgrade() -> None:
    op.drop_column(
        "research_evidences", "inherited_from_session_id", schema="research"
    )
```

- [ ] **Step 3: API 响应加字段**

`backend/research/schemas.py` 的 `EvidenceResponse`（L160-179）中，`structured_facts` 行之后加：

```python
    inherited_from_session_id: UUID | None = None
```

- [ ] **Step 4: 验证迁移链与模型加载**

```bash
cd backend
alembic heads        # 应只显示 a9c4d7e2f1b8
python -c "from research.models import ResearchEvidence; print(ResearchEvidence.__table__.c.keys())"
```

Expected: 输出包含 `inherited_from_session_id`，无 import 错误。

- [ ] **Step 5: Commit**

```bash
git add backend/research/models.py backend/research/schemas.py backend/alembic/versions/a9c4d7e2f1b8_add_evidence_inherited_from.py
git commit -m "feat: research_evidences inherited_from_session_id column + migration"
```

---

### Task 2: 继承逻辑 `_select_and_inherit` + auto_gather 集成（TDD）

**Files:**
- Modify: `backend/research/gather_service.py`（新增模块级常量与 `_select_and_inherit` 函数；`auto_gather` 末尾加第 6 步）
- Test: `backend/tests/test_research.py`（文件末尾新增 `TestEvidenceInheritance` 类）

**Interfaces:**
- Consumes: `ResearchEvidence.inherited_from_session_id`（Task 1）；现有 `EvidenceService`、`EventLogger`、`GatherService.auto_gather`
- Produces: `async def _select_and_inherit(session_db: AsyncSession, session_id: uuid.UUID, company_id: uuid.UUID, ticker: str | None) -> int`（模块级私有，仅 gather_service 内部使用）；`auto_gather` 返回 dict 新增 `"inherited_added": int`

- [ ] **Step 1: 先写失败测试**

在 `backend/tests/test_research.py` 末尾追加（文件顶部已 import `TestClient` 与 `SAMPLE_RESEARCH`，补充以下 import）：

```python
import knowledge.service
```

测试类（完整代码）：

```python
class TestEvidenceInheritance:
    """跨会话证据继承：同公司已完成会话的证据带入新会话，标 inherited。"""

    def _create_company(self, client: TestClient) -> dict:
        resp = client.post(
            "/api/v1/companies",
            json={"ticker": "600519", "name": "贵州茅台"},
        )
        assert resp.status_code in (200, 201, 409), resp.text
        return resp.json()

    def _completed_session_with_evidence(
        self, client: TestClient, company_id: str, question: str, n: int
    ) -> dict:
        s = client.post(
            "/api/v1/research/sessions",
            json={"title": f"S-{question[:8]}", "question": question, "company_id": company_id},
        ).json()
        for i in range(n):
            client.post(
                f"/api/v1/research/sessions/{s['id']}/evidences",
                json={
                    "source_type": "document",
                    "source_id": f"{s['id']}-{i}",
                    "source_title": f"历史证据 {i}",
                    "content": f"历史已完成会话的证据内容 {i}：" + question,
                    "evidence_type": "supporting",
                },
            )
        client.patch(f"/api/v1/research/sessions/{s['id']}", json={"status": "completed"})
        return s

    @staticmethod
    def _mock_search_empty(monkeypatch):
        async def _search(self, query, **kwargs):
            return []

        monkeypatch.setattr(knowledge.service.KnowledgeService, "search", _search)

    def _new_session(self, client: TestClient, company_id: str) -> dict:
        return client.post(
            "/api/v1/research/sessions",
            json={"title": "新会话", "question": "茅台的投资价值如何", "company_id": company_id},
        ).json()

    def test_inherit_from_completed_session(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        src = self._completed_session_with_evidence(client, company["id"], "茅台护城河分析", 3)
        new_s = self._new_session(client, company["id"])
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.status_code == 200, resp.text
        assert resp.json()["inherited_added"] == 3

        evidences = client.get(f"/api/v1/research/sessions/{new_s['id']}/evidences").json()
        inherited = [e for e in evidences if e["inherited_from_session_id"] == src["id"]]
        assert len(inherited) == 3

    def test_inherit_idempotent(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        self._completed_session_with_evidence(client, company["id"], "茅台盈利能力", 2)
        new_s = self._new_session(client, company["id"])
        self._mock_search_empty(monkeypatch)

        client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.json()["inherited_added"] == 0

    def test_draft_session_not_inherited(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        # 历史会话保持 draft（不设 completed）
        draft = client.post(
            "/api/v1/research/sessions",
            json={"title": "未完成", "question": "茅台风险", "company_id": company["id"]},
        ).json()
        client.post(
            f"/api/v1/research/sessions/{draft['id']}/evidences",
            json={
                "source_type": "document",
                "source_id": "draft-1",
                "content": "未完成会话的证据",
                "evidence_type": "neutral",
            },
        )
        new_s = self._new_session(client, company["id"])
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.json()["inherited_added"] == 0

    def test_dedup_against_existing(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        src = self._completed_session_with_evidence(client, company["id"], "茅台估值分析", 1)
        new_s = self._new_session(client, company["id"])
        # 手动加入与历史证据完全相同 (source_type, source_id, content) 的证据
        evidences = client.get(f"/api/v1/research/sessions/{src['id']}/evidences").json()
        same = evidences[0]
        client.post(
            f"/api/v1/research/sessions/{new_s['id']}/evidences",
            json={
                "source_type": same["source_type"],
                "source_id": same["source_id"],
                "content": same["content"],
                "evidence_type": "neutral",
            },
        )
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.json()["inherited_added"] == 0

    def test_limit_ten_newest_first(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        old = self._completed_session_with_evidence(client, company["id"], "老会话证据", 6)
        new = self._completed_session_with_evidence(client, company["id"], "新会话证据", 6)
        new_s = self._new_session(client, company["id"])
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.json()["inherited_added"] == 10

        evidences = client.get(f"/api/v1/research/sessions/{new_s['id']}/evidences").json()
        inherited_srcs = {
            e["inherited_from_session_id"] for e in evidences if e["inherited_from_session_id"]
        }
        # 新会话（updated_at 更晚）优先：12 条候选取 10 条，新会话 6 条全带，老会话补 4 条
        assert new["id"] in inherited_srcs
        assert old["id"] in inherited_srcs

    def test_no_company_no_inherit(self, client: TestClient, monkeypatch):
        # 无公司会话 + 存在已完成会话（未挂公司）也不继承
        src = client.post(
            "/api/v1/research/sessions",
            json={"title": "无公司会话", "question": "通用问题"},
        ).json()
        client.post(
            f"/api/v1/research/sessions/{src['id']}/evidences",
            json={
                "source_type": "document",
                "source_id": "nc-1",
                "content": "无公司证据",
                "evidence_type": "neutral",
            },
        )
        client.patch(f"/api/v1/research/sessions/{src['id']}", json={"status": "completed"})

        new_s = client.post(
            "/api/v1/research/sessions",
            json={"title": "新无公司会话", "question": "通用问题2"},
        ).json()
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.status_code == 200
        assert resp.json()["inherited_added"] == 0
```

- [ ] **Step 2: 重建测试库并跑测试确认失败**

```bash
cd backend
docker exec -it airesearch-postgres psql -U airesearch -c "DROP DATABASE IF EXISTS airesearch_test;"
docker exec -it airesearch-postgres psql -U airesearch -c "CREATE DATABASE airesearch_test OWNER airesearch;"
python -m pytest tests/test_research.py::TestEvidenceInheritance -v
```

Expected: FAIL — `KeyError: 'inherited_added'` 或响应无该字段（`_select_and_inherit` 未实现）。

- [ ] **Step 3: 实现 `_select_and_inherit`**

在 `backend/research/gather_service.py` 中，`GatherService` 类之后、`settings_enabled_classifier` 函数之前新增（顶部 import 区补 `from sqlalchemy import select`）：

```python
# 证据继承上限：单次 auto-gather 最多带入的历史证据条数
_INHERIT_MAX = 10


async def _select_and_inherit(
    session_db: AsyncSession,
    session_id: uuid.UUID,
    company_id: uuid.UUID,
    ticker: str | None,
) -> int:
    """证据继承：同公司已完成会话的证据原样带入当前会话，标 inherited_from_session_id。

    规则（见 specs/2026-10-16-evidence-inheritance-design.md）：
    - 仅来源会话 status='completed'；按会话 updated_at 倒序（最新会话优先）
    - 幂等：已是继承证据（标记非空）不重复带入
    - 去重：与当前会话已有 (source_type, source_id, content[:256]) 相同的跳过
    - 上限 _INHERIT_MAX 条；不重新走 LLM 分类/事实抽取（原会话已完成）
    """
    from research.models import ResearchSession

    existing = (
        (await session_db.execute(
            select(ResearchEvidence).where(ResearchEvidence.session_id == session_id)
        )).scalars().all()
    )
    seen = {
        (ev.source_type, ev.source_id, (ev.content or "")[:256])
        for ev in existing
    }

    stmt = (
        select(ResearchEvidence, ResearchSession)
        .join(ResearchSession, ResearchEvidence.session_id == ResearchSession.id)
        .where(
            ResearchSession.company_id == company_id,
            ResearchSession.id != session_id,
            ResearchSession.status == "completed",
            ResearchEvidence.inherited_from_session_id.is_(None),
        )
        .order_by(ResearchSession.updated_at.desc(), ResearchEvidence.created_at.desc())
        .limit(_INHERIT_MAX * 6)  # 预留去重过滤后的余量
    )
    rows = (await session_db.execute(stmt)).all()  # list of (evidence, source_session)

    added = 0
    for evidence, _src_session in rows:
        if added >= _INHERIT_MAX:
            break
        key = (evidence.source_type, evidence.source_id, (evidence.content or "")[:256])
        if key in seen:
            continue
        session_db.add(
            ResearchEvidence(
                session_id=session_id,
                content=evidence.content,
                source_type=evidence.source_type,
                source_id=evidence.source_id,
                source_title=evidence.source_title,
                relevance_score=evidence.relevance_score,
                evidence_type=evidence.evidence_type,
                content_nature=evidence.content_nature,
                summary=evidence.summary,
                reliability=evidence.reliability,
                data_freshness=evidence.data_freshness,
                citation_quality=evidence.citation_quality,
                classification_source=evidence.classification_source,
                classification_confidence=evidence.classification_confidence,
                structured_facts=evidence.structured_facts,
                inherited_from_session_id=evidence.session_id,
            )
        )
        seen.add(key)
        added += 1

    if added:
        await session_db.flush()
        await EventLogger(session_db).record(
            source="research",
            event_type="evidence.inherited",
            entity_type="research_evidence_batch",
            entity_id=str(session_id),
            payload={"count": added, "ticker": ticker},
        )
        logger.info("Evidence inherited: %d rows into session %s", added, session_id)
    return added
```

- [ ] **Step 4: auto_gather 接入第 6 步**

`auto_gather` 中，步骤 5（交叉验证 `discrepancies` 代码块）之后、`return` 之前插入：

```python
        # 6. 证据继承：同公司已完成会话的历史证据原样带入（标 inherited_from_session_id）
        inherited_added = 0
        if session.company_id:
            try:
                from company.service import CompanyService

                company = await CompanyService(self.session).get(session.company_id)
                inherited_added = await _select_and_inherit(
                    self.session, session_id, session.company_id, company.ticker
                )
            except Exception as e:
                logger.warning("Evidence inheritance skipped: %s", e)
```

`return` dict 增加一项：

```python
            "inherited_added": inherited_added,
```

- [ ] **Step 5: 跑测试确认通过**

```bash
python -m pytest tests/test_research.py::TestEvidenceInheritance -v
```

Expected: 6 passed。

- [ ] **Step 6: 全量回归 + lint**

```bash
python -m pytest -v
ruff check .
```

Expected: 除预存 4 项 Ollama embeddings 失败外全绿；ruff 无新告警。

- [ ] **Step 7: Commit**

```bash
git add backend/research/gather_service.py backend/tests/test_research.py
git commit -m "feat: inherit verified evidence from completed sessions in auto-gather"
```

---

### Task 3: 前端继承徽标

**Files:**
- Modify: `frontend/src/views/ResearchDetail.vue`（证据卡徽标行，约 L128-135）

**Interfaces:**
- Consumes: API 响应中 `evidence.inherited_from_session_id`（Task 1 已透出；`evidences` 在前端为 `any[]`，无需改 api.ts 类型）
- Produces: 证据卡「📥 历史已核实」徽标，点击跳转原会话

- [ ] **Step 1: 加徽标**

在 `ResearchDetail.vue` 徽标行（`🤖 AI分类` el-tag 附近，约 L134 后）追加：

```html
<el-tag
  v-if="ev.inherited_from_session_id"
  size="small"
  effect="plain"
  type="success"
  style="cursor: pointer"
  @click="router.push(`/research/${ev.inherited_from_session_id}`)"
>📥 历史已核实</el-tag>
```

（`router` 已在 `<script setup>` L16 定义：`const router = useRouter()`。）

- [ ] **Step 2: 类型检查与构建**

```bash
cd frontend
npm run build
```

Expected: vue-tsc 与 vite build 均无错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ResearchDetail.vue
git commit -m "feat(frontend): inherited evidence badge linking to source session"
```

---

### Task 4: 文档同步 + 收尾验证

**Files:**
- Modify: `README.md`（Roadmap 表格：证据继承行改 ✅，附一行说明）
- Modify: `memory/ai-research-os-session.md`（变更日志加 2026-10-16 条目）

- [ ] **Step 1: 更新 README Roadmap**

`README.md` Roadmap 表格中：

```
| ~~证据继承~~ | ✅ 2026-10-16 | auto-gather 自动带入同公司已完成会话证据（上限 10 条/去重/幂等），标 inherited_from_session_id，前端「📥 历史已核实」徽标可跳原会话 |
```

- [ ] **Step 2: 更新 session memory 变更日志**

`memory/ai-research-os-session.md` 变更日志顶部加：

```markdown
- **2026-10-16**: 跨会话证据继承。auto-gather 第 6 步带入同公司已完成会话证据（`_select_and_inherit`，上限 10 条 + 去重 + 幂等，不走 LLM 二次分类）；Evidence 新列 `inherited_from_session_id`（迁移 `a9c4d7e2f1b8`）；前端「📥 历史已核实」徽标跳原会话。auto_gather 响应新增 inherited_added。
```

- [ ] **Step 3: 最终验证**

```bash
cd backend && python -m pytest -q
cd ../frontend && npm run build
```

Expected: 测试除预存 4 项外全绿；build 绿。

- [ ] **Step 4: Commit**

```bash
git add README.md memory/ai-research-os-session.md
git commit -m "docs: evidence inheritance shipped - roadmap + session memory"
```
