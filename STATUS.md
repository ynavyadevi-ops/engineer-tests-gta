# STATUS

**Last completed phase:** 01 — Windows scaffold and reproducible run loop (2026-11-17)
**Current phase:** none in progress
**App runnable:** yes, locally: status smoke page only (`scripts\run.ps1 -Build` → `http://127.0.0.1:8765/`)

## Implementation vs live verification

| Phase | Implementation | Live verification |
|---|---|---|
| 00 | done | n/a (docs only) |
| 01 | done | n/a (no YouTube or cloud calls by design) |
| 02–12 | not started | not started |
| 13 (optional AI) | not started | not started |
| 14 (Vercel readiness) | not started | hosted preview: not deployed / not verified |

## Phase 01 acceptance (run 2026-11-17, Windows 11, PS 5.1)

| Check | Result | Evidence |
|---|---|---|
| Locked installs repeat | passed | `bootstrap.ps1 -Clean` exit 0 (Python 3.12.13; npm ci, 46 pkgs, 0 vulns); run twice. `sha256sum -c` shows `uv.lock` and `package-lock.json` unchanged |
| `uv.lock` in sync | passed | `uv lock --check` in `check.ps1` |
| Backend smoke tests | passed | pytest: 32 passed (config, `/api/status`, host/origin guards, headers, packaged UI, CLI); non-loopback network blocked in tests |
| Frontend smoke tests | passed | `tsc --noEmit` clean; vitest: 2 files, 8 tests passed (SSR render of shell, status, error and warning states; payload validation; env guard) |
| Lint/format | passed | `ruff check` and `ruff format --check` clean |
| App starts without any key | passed | `check.ps1` real process with `YOUTUBE_API_KEY` removed → `/api/status` 200, `mode=demo`, `youtube_api_key=not configured` |
| No secret in `/api/status` | passed | Real process with a synthetic sentinel key → `configured`, sentinel absent from the body; pytest also checks body, headers and CLI output |
| No secret in frontend bundle | passed | Build with the sentinel in env, then `scan-bundle.mjs`: 3 files, 4 patterns, 2 env values, 0 hits. Negative controls: `VITE_YOUTUBE_API_KEY` aborts the build (exit 1); a planted sentinel fails the scan (exit 1) |
| Scripts exit nonzero on failure | passed | `run.ps1` with `GTA_LAB_HOST=0.0.0.0` → exit 1; `check.ps1` without uv on PATH → exit 1 |
| Paths with spaces | passed | Repo path itself; tests and `check.ps1` use data and dist dirs with spaces |
| Dev proxy run | passed | Vite 5173 → FastAPI 8765: `/api/status` JSON through the proxy; both listen on 127.0.0.1 only |
| Packaged same-origin run | passed | FastAPI served the built UI and `/api` on one port; page rendered in the browser with no console errors under the CSP |
| Dependency audits | passed | `npm audit --audit-level=high`: 0 vulnerabilities; `pip-audit`: no known vulnerabilities (local `gta-lab` skipped as editable). These are point-in-time results, not a safety guarantee |
| `scripts\dev.ps1` wrapper end-to-end | not run | Interactive and long-running. Its two components were run directly, as above |

Full check: `scripts\check.ps1` → 11/11 passed, exit 0.

## Gates

| Gate | Status |
|---|---|
| 1 BUILD — APP READY | not run (needs Phases 02–12) |
| 2 LIVE DATA — LIVE SAMPLE READY | not run (will need `YOUTUBE_KEY`) |
| 3 APPROVAL-ONLY — ADVANCED ANALYTICS | off (no approval) |
| 4 OPTIONAL AI | not run |
| 5 VERCEL READINESS | not run |

## Open capability blocks

- `YOUTUBE_KEY`: not yet needed. Required before the Phase 03 live smoke test. Enable YouTube Data API v3 on a personal Google Cloud project, create a key restricted to that API, and set `YOUTUBE_API_KEY` in `%LOCALAPPDATA%\EngineerTestsGTA\private.env` (not the repo `.env`). Never paste it into chat.

## Notes for Phase 02

- DB paths already exist in settings: `Settings.demo_db_path` / `live_db_path` / `active_db_path` under `GTA_LAB_DATA_DIR` (default `%LOCALAPPDATA%\EngineerTestsGTA\data`, not synced).
- `/api/status` reports `database: not yet created`. Phase 02 should switch it to real health counts.
- Starlette warns that `httpx` in its TestClient is deprecated (it suggests `httpx2`). Harmless now; review it at the next dependency upgrade.
- Nothing is committed yet. Commit only when the user asks.

## Next action (exactly one)

Open a fresh agent session in this folder and paste:

```text
Execute Phase 02 only from docs/phases/02.md. Start with CLAUDE.md (or AGENTS.md),
STATUS.md, the current phase file, and only the spec sections the phase references.
Check git status and the previous acceptance gate. Report any failing prerequisite with
evidence, fix only what falls inside this phase, and otherwise stop at the blocker.
Implement the phase, run its acceptance tests, and update STATUS.md and PROMPT_HISTORY.md
with exact results and the next command. Do not start the next phase.
```
