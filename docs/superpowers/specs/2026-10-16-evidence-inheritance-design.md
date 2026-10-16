# 设计文档：跨会话证据继承（Evidence Inheritance）

- 日期：2026-10-16
- 状态：已批准（对话中分节确认）
- 前置：比率层 + PE/PB 历史分位（2026-10-15，迁移 head `f3a8c2e1b7d9`）
- Roadmap 位置：证据继承为当前优先级第 3 项（此前两项已完成）

## 目标

新研究会话执行 auto-gather 时，自动带入**同公司、历史已完成会话**中的证据，标记为「历史已核实」，避免同一公司的重复研究重新搜集已验证内容。

## 已确认的需求决策（对话澄清）

| 决策点 | 结论 |
|---|---|
| 触发时机 | `auto_gather` 自动带入（用户零操作） |
| 入选标准 | 仅来源会话 `status='completed'` 的证据 |
| 标记方式 | Evidence 新增专用列（不用 extra_metadata） |
| 数量/去重/幂等 | 限最新 10 条 + 去重 + 重复 gather 幂等 |
| 前端展示 | 证据卡「📥 历史已核实」徽标，点击跳原会话 |

## 方案选型

采用**方案 A：GatherService 内嵌继承步骤**。在 `auto_gather` 流程末尾新增第 6 步，纯查询+插入，不引入新 service/端点（方案 B 对单用户工具过度设计），不采用展示层 join（方案 C 会让 [ev:id] 引用与证据列表跨 session 化，改动面反而大）。

## 设计

### 1. 数据模型（research/models.py）

`ResearchEvidence` 新增：

```python
inherited_from_session_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("research.research_sessions.id", ondelete="SET NULL"),
    nullable=True,
    comment="继承自历史已完成会话的证据（非空即继承证据）",
)
```

迁移：在 `f3a8c2e1b7d9` 之后新增一个 alembic revision（单列 add_column）。测试库按既有惯例 DROP DATABASE airesearch_test 重建（conftest 用 create_all）。

### 2. 继承逻辑（research/gather_service.py）

新增模块级私有函数：

```python
async def _select_and_inherit(session_db, session_id) -> int
```

执行规则：

1. **入选**：同 `company_id` 的其他会话中，`status='completed'` 会话下的证据。
2. **排序**：按原会话 `updated_at` 倒序（最新完成的会话优先）；同会话内按证据创建时间倒序。
3. **排除**：
   - `inherited_from_session_id` 非空的（幂等：重复 gather 不会二次继承）；
   - 当前会话已有同去重键 `(source_type, source_id, content[:256])` 的证据（避免与本次新搜集内容重复）。
4. **上限**：最多带入 10 条。
5. **写入**：原样复制证据（保留 `evidence_type` / `content_nature` / `reliability` / `data_freshness` / `citation_quality` / `structured_facts` / `classification_source`），写入 `inherited_from_session_id`。**不重新走 LLM 批量分类、事实抽取与交叉验证**——继承证据的分类与抽取在原会话已完成。
6. **事件**：`EventLogger.record` 记 `evidence.inherited`，payload `{count, ticker}`。
7. **返回**：`auto_gather` 响应 dict 增加 `inherited_added: int`。

在 `auto_gather` 中的位置：步骤 3（LLM 批量分类）、4（事实抽取）、5（交叉验证）全部完成之后、返回之前，即作为第 6 步，避免继承证据混入 `collected` 列表被二次处理。

无公司（`session.company_id is None`）或公司无已完成历史会话时：跳过，返回 0，不报错。

### 3. 前端

- `src/stores/api.ts`：Evidence 接口增加 `inherited_from_session_id?: string | null`。
- `src/views/ResearchDetail.vue`：证据卡新增「📥 历史已核实」徽标（与现有 🤖 AI分类、🔢定量/💬定性 徽标同风格，样式走既有 CSS 变量），点击 `router.push('/research/' + inherited_from_session_id)` 跳转原会话。

### 4. 测试（backend/tests/test_research.py）

纯逻辑与集成用例：

1. completed 历史会话 → 新 session `auto_gather` → 继承证据存在且 `inherited_from_session_id` 正确；
2. 重复执行 `auto_gather` → `inherited_added=0`（幂等）；
3. 历史 session 为 draft/研究中的 → 不继承；
4. 当前会话已有同 `(source_type, source_id, content[:256])` 证据 → 跳过；
5. 历史证据 >10 条 → 只带入最新会话优先的 10 条；
6. 无 company_id → 不继承、不报错。

（auto-gather 集成用例沿用现有 test_research 的 mock 方式：mock KnowledgeService.search，避免外部依赖。）

### 5. 明确不改的部分

- 报告双轨与 `[ev:id]` 引用机制：继承证据在本会话拥有自己的 evidence id，天然可被报告内联引用，`report_service` 与 prompt 均不动。
- 报告上下文区块（period/peer/ratio）不动。
- EvidenceService 对外接口不变（继承插入复用其现有能力或同 session 直插，按实现就近选择）。

## 验收标准

- 新会话 auto-gather 后，证据列表可见带「历史已核实」徽标的证据，点击可跳原会话；
- 重复 gather 不产生重复继承；
- 全量测试通过（预存的 4 项 Ollama 环境依赖失败除外）；
- `ruff` / `vue-tsc` / `npm run build` 全绿。
