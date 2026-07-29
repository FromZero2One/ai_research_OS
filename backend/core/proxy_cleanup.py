"""Proxy environment variable cleanup — no import-time side effects.

Usage:
    from core.proxy_cleanup import clean_proxy_env
    clean_proxy_env()       # call BEFORE any httpx client is created

The server entry point (``api/app.py``) calls this at module level *before*
importing any router or adapter modules, which ensures httpx never sees
the problematic proxy vars.

Scripts that use adapters directly should also call ``clean_proxy_env()``
at the top of their entry point.
"""

from __future__ import annotations

import os as _os


def clean_proxy_env() -> None:
    """Strip proxy env vars that interfere with local connections.

    httpx caches proxy configuration at its own *import* time, so this
    must be called **before** any module that imports httpx is loaded.
    """
    for _var in (
        "all_proxy", "ALL_PROXY",
        "http_proxy", "HTTP_PROXY",
        "https_proxy", "HTTPS_PROXY",
        "ftp_proxy", "FTP_PROXY",
    ):
        _os.environ.pop(_var, None)
    _os.environ.setdefault("no_proxy", "localhost,127.0.0.0/8,::1")
    _os.environ.setdefault("NO_PROXY", "localhost,127.0.0.0/8,::1")
