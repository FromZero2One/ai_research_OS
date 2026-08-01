#!/usr/bin/env python3
"""Export FastAPI OpenAPI schema to JSON for frontend type generation.

Usage:
    python scripts/generate_openapi.py

Output: ../frontend/openapi.json (used by openapi-typescript)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure we can import from the backend package
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Must strip proxy env before any imports
from core.proxy_cleanup import clean_proxy_env  # noqa: E402

clean_proxy_env()

from api.app import create_app  # noqa: E402

app = create_app()
openapi = app.openapi()

# Sort keys for deterministic output
output_path = backend_dir.parent / "frontend" / "openapi.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(openapi, f, indent=2, ensure_ascii=False)

print(f"✅ OpenAPI schema written to {output_path}")
print(f"   {len(openapi.get('paths', {}))} paths")
print(f"   {len(openapi.get('components', {}).get('schemas', {}))} schemas")
