"""Market Center API route modules.

Use ``from market.routes import router`` to get the aggregate router that
mounts every sub-router (backwards compatible with the old single
``market/routes.py``). Each sub-router is also importable directly.
"""

from __future__ import annotations

from market.routes.aggregate import router

__all__ = ["router"]
