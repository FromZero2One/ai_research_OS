#!/bin/bash
cd /home/wsm/codes/ai_research_OS/backend
ALL_PROXY= all_proxy= no_proxy="localhost,127.0.0.0/8,::1" PYTHONPATH=. uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
