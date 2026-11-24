# Codebase Notes — learned 2026-11-24 (learn-codebase full read)

Every source file under `backend/` and `frontend/src/` was read in full (six parallel readers + project docs). This file is the consolidated, fact-grounded reference. See also `README.md`, `USAGE.md`, `backend/README.md`, and the progress snapshot in this directory.

## What the system is

Personal AI value-investment screener for A-shares. **"Screener First, not AI First"**: data + deterministic rules do the screening; the LLM only does evidence-backed deep judgement of qualitative criteria. 2026-11-24 slimming deleted research/portfolio/AI-center/dashboard code (DB tables kept).

Stack: FastAPI (`backend/`, uv venv at `backend/.venv`) + Vue 3/Vite (`frontend/`). Infra: Postgres :5432, Qdrant :6333, Redis :6380. One Postgres schema per module: `company`, `market`, `document`, `core`, `screener` (+ leftover research/portfolio/ai schemas, code deleted). LLM = DeepSeek via OpenAI-compatible endpoint (`LLM_PROVIDER=openai` in `.env`); embedding = Ollama `bge-m3` (1024-dim, `OLLAMA_NUM_PARALLEL=4`). No auth by design (single-user local tool).

**Dependency rule: up only.** company → market/document → knowledge → screener. Knowledge has no own schema (reuses `document` tables). Market is the ONLY source of numbers; documents/knowledge carry qualitative text only; `structured_facts`-style cross-validation is not on the report path (research module gone).

## Startup & wiring

- `start-dev.cmd` = docker deps + backend :8000 (`--reload`, SelectorEventLoop — required on Windows, Proactor dies with WinError 64) + frontend :5173.
- `api/app.py`: `clean_proxy_env()` runs at import line 15 BEFORE httpx-importing modules (httpx caches proxy config at import). Registers all model modules, lifespan: DB check → optional embedding prewarm → import `screener.service`/`screener.backtest_service`/`core.performance_schedule` (registers task handlers) → `_recover_interrupted_tasks()` → `_task_worker_loop()` asyncio task → 5 APScheduler jobs (Asia/Shanghai cron) → shutdown disposes engine.
- Exception handlers: NotFound→404, ValidationError→422, DuplicateError→409, AuthN→401, AuthZ→403, ExternalServiceError→502, base→500, DomainError→http_status. **`ConfigurationError` and `DocumentParsingError` have no handler → default 500.**
- All routers under `/api/v1`; docs at :8000/docs.

## core/

- **container.py**: `Container(session)` — 11 lazy service properties with inline imports (circular-import avoidance); reranker gated on `find_spec("sentence_transformers")` (not installed on this machine). Routes get it via `Depends(get_container)`.
- **task_manager.py**: persistent queue `core.task_records` (`pending→running→completed|failed`, attempts default 3, dedup on (task_type, task_key) against pending/running). Worker loop: poll 1s, execute handler outside pick-transaction; handler signature `fn(payload) -> dict|None`, manages own session via `managed_session()`. Startup recovery: running→pending "Interrupted by server restart". Note: `import asyncio` at bottom of file.
- **scheduler.py**: registry + AsyncIOScheduler; 5 jobs: `market_data_update` (0 18 * * 1-5), `financial_data_update` (15 3 * * 1-5), `screener_schedule` (30 16 * * 1-5), `performance_snapshot` (10 17 * * 1-5), `event_log_cleanup` (0 3 * * 1, 90d retention). `GET /scheduler/status`, `POST /scheduler/run/{job}`.
- **market_sync.py**: full-market A-share daily snapshot from Sina (`Market_Center.getHQNodeData`, 80/page, 0.3s throttle) — NOT is_active companies; bulk `on_conflict_do_nothing` on (ticker,date).
- **financial_sync.py**: 3 SAVEPOINT-isolated loaders from `screener.ingest` per latest report period.
- **screener_schedule.py**: per `SCREENER_SCHEDULE_PRESETS` tag → active builtin preset by style_tag; skip if any active run; runs screen, writes diff md, webhook; also registers task handler `screener_schedule` for manual run.
- **event_log.py/service/routes**: write-once audit trail (exception: company thesis READS `thesis.updated` events — thesis is stored as an event!). `GET /events*` endpoints.
- **adapters/**: `OllamaLLM` (num_ctx 8192, `think` off, structured = prompt-JSON + json.loads), `OpenAILLM` (json_object mode); both record usage into in-memory `llm_usage` (resets on restart). `OllamaEmbedding` auto-discovers dim, returns zero vectors on API failure (logged). `QdrantVectorStore` search returns [] on missing collection. `PyMuPDFParser` raises PDFEncrypted/PDFScanned (no OCR in V1). `RedisCache` lazy. Proxy env explicitly disabled per-client (`proxy=None`).
- **interfaces.py**: runtime-checkable Protocols for all adapters/services (business modules never import adapters directly).
- **config.py**: full env table — DB/Qdrant/embedding/LLM/Redis/UPLOAD_DIR/CHUNK_SIZE=512/OVERLAP=64/BM25_MAX_CHUNKS=0(unlimited)/AKSHARE_MCP_DIR (Linux path, must be set in local .env)/BACKTEST_MYSQL_URL/backtest costs/screener limits (min_turnover .05, min_mcap 1e9, max_per_industry 8, min_confidence 0, judge_concurrency 8)/all cron schedules/webhook config/CORS.

## company/

`Company` (ticker unique, is_active=watchlist, priority/target_price/reason) + `CompanyTag`. Thesis lives in `core.event_log` entries (`thesis.updated`, source=company, entity_id=ticker). Routes: CRUD + `POST /companies/watch` + `GET/POST /companies/by-ticker/{t}/thesis` + workspace (recent_research hardcoded empty).

## market/ (numbers single source of truth)

Tables: `stock_prices` (uq ticker+date), `financial_metrics` (ticker/year/period/metric; `announcement_date` = PIT field), `data_freshness` (per ticker+type, ok/stale/error/never_fetched), `valuation_history` (uq ticker+trade_date, PE/PB percentile source), `stock_industry` (uq ticker).
- **akshare_executor.py**: subprocess in separate `akshare_mcp` venv (`uv run --directory`); ticker passed via env var only + regex allowlist (code-injection safe; tested); protocol `__R__:<json>` / `__E__:`; no retries anywhere; cloud-MCP layer for prices/news optional.
- Services: prices (PG → local akshare → cloud MCP; cache reads never refresh freshness), financials (A-stock: `stock_financial_abstract`; HK report API), profile (`stock_profile_cninfo`/HK), news (no persistence), search (own company universe ILIKE only), freshness (thresholds prices 24h/fin 168h/profile 168h/news 6h; coverage matrix incl. qualitative dimension from document mda/risk chunks — only file importing document).
- **ratio_service.py**: pure compute_ratios/percentile_rank; valuation_percentile pulls `stock_a_indicator_lg` into `valuation_history` when <2 local rows.
- Routes return plain dicts; `schemas.py` is dead code.

## document/ + knowledge/

- Document: `documents` (extra_metadata JSONB = indexing progress) + `document_chunks` (content_type mda/risk/notes/announcement/other; embedding_id = uuid5 of doc id + chunk index). Chunker: 512/64 sliding window, table-aware (whole markdown table kept in one chunk). `table_extractor.py`: rebuilds ruling-line-less bank-report tables from word coordinates; group headers (集团/母公司) folded into column headers. Classifier: pure keyword rules.
- Pipeline: upload (writes file, no parse) → background task `document_index` → parse (pdfplumber per page, table pages replaced by markdown, PyMuPDF fallback; NUL-byte sanitize) → chunk → classify → batch embed (64; failed texts skipped, not zero-vector) → Qdrant upsert. Idempotent re-index deletes chunks+vectors first.
- Knowledge: hybrid = dense Qdrant + BM25 (jieba, stopwords, query expansion 营收→营业收入 etc., module-level cache TTL 300s) → RRF (k=60) → optional cross-encoder rerank → snippet with table-header-aware windows. `min_score` param accepted but never applied. `ask` = retrieval → citation-enforced prompt (temp 0.2, max 1024) → answer + sources; prompt is a hardcoded constant (DB prompt templates deleted). search_by_document: dense + ILIKE fallback.

## screener/ (the core; ~97% complete per README)

Tables: `screener_runs` (**partial unique index on active statuses → DB-guaranteed single active run**), `screener_judgements` (verdict recommend/reject/insufficient/failed), `criteria_presets`, `metric_defs`, `screener_rules` (LLM translation cache by doc_hash), `backtest_runs`, `portfolios`, `performance_snapshots` (uq run_id+as_of).

Pipeline (`service.run_screener`): trigger (409 if active run; immediate commit for POST→GET race; persistent task `screener_run`) → compose rules (presets: pure `compose.compose_rules`; freeform: LLM `translate` cached by hash) → **deterministic screening**: Sina full-market spot (Redis-cached per trading day), pool hygiene (ST/suspended/turnover/mcap/board), industry attach (`market.stock_industry`), financial_type (bank/insurance via F10 field presence), data pre-flight (`required_data_metrics` expands derived → market-wide ingest loaders, SAVEPOINT-isolated; zero-coverage required metric = run failure), load only latest period, industry percentiles, rule evaluation (missing+exclude→excluded; score=hits/rules; near-misses=exactly 1 failed rule; union mode per-preset scope filtering) → cap 50 → LLM deep judge (skip entirely if no qualitative criteria: `_auto_pass_judgement`) → report md + webhook.

**Judge** (`judge.py`): per-criterion retrieval (`_retrieve_per_criterion`: ≤6 criteria × top_k=2, concurrent, round-robin interleave, cap 8 snippets × 500 chars); company-scoped (no cross-company contamination); context with CN units + margin anomaly notes; evidence guard: hit=true must cite `[n]`, no-snippets doc-only criteria auto-false, numeric criteria require a digit; downgrade → verdict=insufficient, recommend=False, confidence ≤0.4; semaphore 8; cancellation polls per candidate; failures isolated (status=failed). `judge_eval.py` + `eval/judge_cases.jsonl` (10 cases) = offline eval, script-only (no CI).

**Backtest**: universe from external MySQL (`BACKTEST_MYSQL_URL`, includes delisted); qfq daily bars resumable (≥200 bars skip); rebalance = first trading day after disclosure deadline; April uses prior-year annual report; PIT via `announcement_date ≤ asof` with deadline clamping; costs (万3 commission, 0.05% stamp, 0.1% slippage); suspended (volume 0) → 0 return; stats NAV/CAGR/vol/Sharpe/Sortino/Calmar/win-rate/max-DD + half-sample split; CSI300 benchmark; markdown report with disclaimers. No LLM.

Also: 36 metric defs + 8 builtin presets in `seeds.py` (insert_builtin_seeds shared by migration + tests); portfolio construction (equal/score/confidence, shrink-only constraints, leftover = cash) + rebalance (lot rounding, stale-price hold); performance tracking (T+1 entry, 1/3/6/12m + CSI300 excess) + daily snapshots (17:10 job); diff vs same-rules-signature baseline (preset edit invalidates); webhook notify (generic/wecom/feishu/dingtalk); CSV export UTF-8 BOM; in-process cancellation (`cancel.py`).

Task types: `screener_run`, `screener_backtest` (handlers in module), `screener_schedule` (handler in core).

## Tests

`tests/conftest.py`: creates `airesearch_test` DB idempotently (create_all, NOT alembic; presets via `insert_builtin_seeds`); **hard refusal if DB name == dev DB**; autouse truncate of 16 tables per test (replica role, 5s lock timeout); Qdrant forced to `documents_test`; background tasks monkeypatched to no-op; screener spot-cache no-op'd; NullPool async engine; client + async_client + test_session fixtures. 53 test files — screener is the bulk (42). Known-failing: none as of 2026-11-24. NOTE: model changes require DROP DATABASE airesearch_test (create_all doesn't migrate).

## Tools/scripts (all under `backend/tools/`, psycopg2 `tools/_db.py`)

Data: `ingest_main_board_batch.py` (sharded), `ingest_recommended.py`, `prefill_periods.py`, `run_market_sync.py`. KB: `fetch_cninfo_reports.py` → `upload_reports.py` → `index_pending_parallel.py` (6 workers). Screener: `run_presets_live.py`, `run_backtest_queue.py`, `reset_stuck_runs.py --apply` (also fails the task — prevents auto-retry). Diagnostics: `show_run/show_judgement/show_holdings`, `run_status`, `check_tasks`, `check_pg_activity`, `confidence_dist`, `check_kb_hit`, `kb_status`, `final_report.py`. `tools/archive/` = retired one-offs (README still mentions rewrite_presets_qualitative.py as active — mismatch).

## Frontend (Vue 3 + TS + Element Plus + TanStack Query + ECharts)

- Data access exclusively via `src/stores/api.ts` (~60 hooks; fetchApi wrapper; useList/useGet/useCreate/useUpdate/useDelete + domain hooks; polling: doc status 2s, run/backtest 3s, scheduler/usage 30s, coverage/data-quality 60s). Despite the folder name, no Pinia stores. `npm run build` (vue-tsc) is the typecheck gate.
- Routes: `/` → `/screener`, companies, company detail, market, documents, knowledge, system. No 404 route, no guards. Vite proxy `/api` → `:8000`, rewritten to `/api/v1`.
- `Screener.vue` (1178 lines): trigger presets/freeform, run adoption after refresh (auto-adopt in-flight run), report/diff/detail/portfolio/performance panels, backtest panel, PresetManager drawer. Markdown always DOMPurify-sanitized.
- `CompanyDetail.vue`: tabs overview/thesis/financials/docs; StockChart (raw echarts, lazy init for hidden tabs), FinancialBars, ratios, valuation percentile. `Market.vue`: coverage matrix + auto-ingest on empty prices. `Knowledge.vue`: search (plain fn, not Query) + ask with model picker. `Documents.vue`: upload + indexing status polling; doc-type filter is non-reactive (query key lacks docType — known wart).
- **`ReportCharts.vue` is dead code** (leftover from deleted research module — imported by nothing).
- `.npmrc` legacy-peer-deps=true required (Element Plus + Vue 3.5).

## Quirks & gotchas (machine/env)

- Proxy env vars break localhost httpx — `clean_proxy_env()` at app import; standalone scripts must clear too.
- `.env` must stay UTF-8 (PowerShell Add-Content ANSI corrupts it).
- Hardcoded Linux paths in `.env.example`/Makefile/`run_dev.sh` — use `start-dev.cmd` + real `.env`.
- Editing anything under `backend/` restarts uvicorn --reload → kills an in-flight screening run; put throwaway scripts outside backend/ during runs.
- `BACKTEST_MYSQL_URL` configured here → backtests usable. KB populated: 103 reports / 55,135 chunks.
- Lint debt: repo-wide ruff fails (~200 errors) — only lint touched files; mypy scoped to core/market-domain/repositories; pre-commit runs ruff --fix + format on changed files + scoped mypy.

## Known gaps (from README/memory, 2026-11-24)

- Fact-like qualitative criteria (audit opinion, litigation, cash coverage) should become deterministic checks, not LLM prompts — deep-value preset still judges 0/50.
- `confidence` uncalibrated (0.95/0.92/0.85 buckets) — ordering only.
- Judge eval has no CI/history panel.
- Small debts: Documents.vue doc-type filter non-reactivity, ReportCharts.vue dead file, market schemas.py dead, tools/README/archive mismatch, README 覆盖网格 column hardcode.
