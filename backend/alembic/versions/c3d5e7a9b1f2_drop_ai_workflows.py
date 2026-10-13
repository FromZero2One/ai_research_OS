# ruff: noqa: E501
"""drop ai.ai_workflows — remove AI workflow feature

单用户工具用不上多步工作流编排（前端零引用），整体移除：
模型、服务方法、API 端点已删，此迁移删表。

Revision ID: c3d5e7a9b1f2
Revises: b8e2f7a1c3d5
Create Date: 2026-10-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3d5e7a9b1f2"
down_revision: str | None = "b8e2f7a1c3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('DROP TABLE IF EXISTS ai.ai_workflows CASCADE')


def downgrade() -> None:
    # 功能已移除，不提供建表回滚（如需恢复请回退到 b8e2f7a1c3d5 之前的代码）
    raise NotImplementedError("AI workflow feature was removed; restore from git history")
