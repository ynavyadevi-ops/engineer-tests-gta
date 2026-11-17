# Prompt history (append-only)

Each entry: phase ID, date, changed files, test evidence, blocker or deferral. Read only the latest entry.

---

## Phase 00 — 2026-11-17

- **Changed files (created):** `AGENTS.md`, `CLAUDE.md`, `APP.md`, `STATUS.md`, `PROMPT_HISTORY.md`, `README.md`, `.gitignore`, `docs/{GATES,SYSTEM_DESIGN,DATA_CONTRACT,SAMPLING,YOUTUBE_POLICY,ANALYTICS,DESIGN,CONTENT_PLAYBOOK,SECURITY,DECISIONS}.md`, `docs/phases/00.md`–`14.md`. Ran `git init -b main` in the project folder.
- **Untouched:** `MASTER_PACK.md.md` (user file).
- **Evidence:** a script extracted all 15 phase blocks verbatim from the master pack, and its assertion that exactly phases 00–14 were found passed. Toolchain: Git 2.56.0, Windows PowerShell 5.1, Python 3.12.10/3.14.5, uv 0.12.0, Node v24.13.1 LTS, npm 11.10.0; `pwsh` missing (optional).
- **Not run:** live re-verification of the YouTube/Vercel/Gemini URLs (deferred to the phases that use them).
- **Blockers:** none for Phase 01.

## Phase 01 — 2026-11-17

- **Changed files (created):** `pyproject.toml`, `uv.lock`, `.python-version` (3.12), `.env.example` (placeholders only), `backend/gta_lab/{__init__,config,app,__main__}.py`, `tests/{__init__,conftest,test_config,test_app,test_cli}.py`, `frontend/{package.json,package-lock.json,tsconfig.json,vite.config.ts,env-guard.ts,env-guard.test.ts,index.html}`, `frontend/src/{main.tsx,App.tsx,StatusView.tsx,api.ts,styles.css,smoke.test.tsx}`, `frontend/scripts/scan-bundle.mjs`, `scripts/{_common,bootstrap,dev,run,check}.ps1`.
- **Changed files (edited):** `README.md` (install/run/keys), `docs/SYSTEM_DESIGN.md` (run commands, settings, pinned runtimes, secret controls), `STATUS.md`.
- **Decisions inside the phase:** the default data dir is `%LOCALAPPDATA%\EngineerTestsGTA\data` (outside OneDrive). The private config is `%LOCALAPPDATA%\EngineerTestsGTA\private.env`, and the repo `.env` is never read. Dependencies resolve only from releases before 2026-11-10 (7-day release-age cutoff). Frontend smoke tests use SSR in Vitest, with no jsdom or testing-library, to keep the dependency tree small.
- **Evidence:** `scripts\check.ps1` 11/11 passed, exit 0 (uv lock check, ruff lint and format, pytest 32 passed, tsc, vitest 8 passed, sentinel build plus bundle scan, keyless real-server start, sentinel real-server no-leak, npm audit 0 vulns, pip-audit no known vulns). `bootstrap.ps1 -Clean` exit 0 with lockfile hashes unchanged. Nonzero exits confirmed for a bad host and a missing tool. Dev proxy and packaged same-origin runs checked by hand.
- **Not run:** `scripts\dev.ps1` as a single wrapper (interactive); its components were run directly.
- **Blockers:** none. Nothing committed.

## Phase 02 — 2026-11-17

- **Changed files (created):** `migrations/0001_foundation.sql`, `0002_youtube_sources.sql`, `0003_sample_selection.sql`, `0004_editorial.sql`; `backend/gta_lab/clock.py`; `backend/gta_lab/db/{__init__,connection,migrate,sources,runs,editorial,planning,retention,health}.py`; `tests/{db_support,test_db_migrations,test_db_isolation,test_db_lifecycle,test_db_semantics,test_db_app}.py`.
- **Changed files (edited):** `backend/gta_lab/app.py` (`/api/status` gains a read-only `data_health` count block), `backend/gta_lab/__main__.py` (`db migrate|status|purge`), `docs/DATA_CONTRACT.md` (field definitions, runner rules, lifecycle), `STATUS.md`.
- **Decisions inside the phase:** STRICT tables with UTC text timestamps. The 30-day cap is enforced in SQL `CHECK`s as well as in code. Fixture IDs must contain `:`. The DB is bound to its dataset on first open. The live DB is refused in cloud-synced folders. Inaccessible videos are kept as metadata-free tombstones until their original expiry. Failed refreshes never extend expiry. Lapsed rows are purged before being rewritten. Purge redacts the current title, channel title and ID from linked notes and briefs. Writing copied titles into notes is refused. Added the supporting tables `plans`, `note_source_refs`, `brief_source_refs` and `db_meta`. The gated history table is not created.
- **Evidence:** pytest 91 passed (59 new). Two mutation checks (expiry read filter removed; API error bumps fetch time) were each caught by the tests, then reverted. `scripts\check.ps1` 11/11 passed, exit 0.
- **Not run:** concurrent multi-process writers; real YouTube responses (Phase 03).
- **Blockers:** none for Phase 03's fixture work. `YOUTUBE_KEY` is still needed for its live smoke test. Nothing committed.
