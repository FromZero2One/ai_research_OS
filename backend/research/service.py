"""
DEPRECATED: ResearchService has been split into focused services.

Use the new imports instead:
    from research.session_service import SessionService
    from research.evidence_service import EvidenceService
    from research.report_service import ReportService
    from research.gather_service import GatherService
    from research.thesis_service import ThesisService
    from research.planner import ResearchPlanner, PLAN_KEY
"""
# Imports below intentionally happen after the deprecation warning.
# ruff: noqa: E402

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "research.service is deprecated — import from the specific submodules "
    "(session_service, evidence_service, report_service, gather_service, "
    "thesis_service, planner)",
    DeprecationWarning,
    stacklevel=2,
)

from research.planner import PLAN_KEY, ResearchPlanner  # noqa: F401
from research.session_service import SessionService as ResearchService  # noqa: F401
