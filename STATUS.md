# STATUS

**Last completed phase:** 02 — SQLite, migrations and data lifecycle (2026-11-17)
**Current phase:** none in progress
**App runnable:** yes, locally: status page with real DB health counts (`scripts\run.ps1 -Build` → `http://127.0.0.1:8765/`). DB maintenance: `uv run --locked python -m gta_lab db migrate|status|purge`

## Implementation vs live verification

| Phase | Implementation | Live verification |
|---|---|---|
| 00 | done | n/a (docs only) |
| 01 | done | n/a (no YouTube or cloud calls by design) |
| 02 | done | n/a (fixture DB and fake clock only; no YouTube calls by design) |
| 03–12 | not started | not started |
| 13 (optional AI) | not started | not started |
| 14 (Vercel readiness) | not started | hosted preview: not deployed / not verified |

## Phase 02 acceptance (run 2026-11-17, Windows 11, SQLite 3.53.1, Python 3.12.13)

| Check | Result | Evidence |
|---|---|---|
| Fresh migration | passed | `test_db_migrations.py`: 0001–0004 applied, the 18 expected tables exist, 4 policy capabilities seeded `off` |
| Repeat migration | passed | Second open and a third `migrate()` apply nothing. Seed rows are not duplicated. CLI `db migrate` twice → `[1,2,3,4]` then `[]` |
| Migration safety | passed | A broken 0005 rolls back fully (no partial table, version stays 4) and then applies once fixed. Edited applied file → rejected. CRLF checkout → same checksum. DB newer than code → rejected. Gaps or bad names → rejected |
| Duplicates | passed | Upsert ×3 → 1 row. Duplicate IDs in a batch, >50 IDs, or returned ⊄ requested → rejected. Same hit in one run → counted in `duplicate_hits`, not stored. A new path or a new run is stored |
| Null semantics | passed | Hidden likes/comments stay `NULL` (`0` stays `0`). States are separated: `not_provided` → "Unavailable", API error without stats → "Unknown", no stats yet → "Not yet collected". Studio blanks stay `NULL` |
| Transaction rollback | passed | A bad record in a batch → nothing written. Hit batch with an unknown video → nothing written and counter unchanged. Nested savepoint rolls back the inner part only. Outer exception rolls back all |
| Fake-clock refresh | passed | Deadlines stored (due day 25, expiry day 30). Not due on day 24, due on day 25. Refresh replaces stats (1 row, new deadlines). API error never extends expiry. Discovery never extends a fresh row |
| Expired data suppressed | passed | Past expiry with a failing refresh: `get_video` → `expired` with no fields; excluded from lists, refresh queue and note refs. Mutation check: removing the read filter, or letting an API error bump the fetch time, fails these tests |
| Fake-clock purge | passed | Day 30 + 1 h: video, stats, hit, review and note ref purged. Copied title/ID redacted from linked note and brief text, authored text kept, unlinked note untouched. Idempotent. WAL truncated. Channels purged too |
| Inaccessible videos | passed | Not returned → tombstone (metadata `NULL`, stats deleted, `not_returned`, not refreshable). Brief view/export shows no link, and the export says "no longer available". Purged at the original expiry. A later return restores it |
| Changed titles/thumbnails | passed | Flagged with `*_changed_at_utc`; old title absent from a full DB dump (no archive) |
| Fixture/live isolation | passed | Separate files. Reopening as the other dataset raises an error. `db_meta.dataset` is immutable. ID shape and endpoint rules apply both ways. Triggers block cross-lineage rows even in raw SQL. Live DB refused in a OneDrive folder |
| No raw bodies / 30-day cap in schema | passed | Schema scan finds no raw/payload/json/description columns. `CHECK` rejects expiry > fetch + 30 d and non-UTC timestamp text |
| `/api/status` + CLI | passed | `data_health` reports counts only (no IDs or titles) and never creates a DB. `db status/migrate/purge` work. Dataset mismatch → exit 1 |

pytest: 91 passed (32 Phase 01 + 59 Phase 02). Full check: `scripts\check.ps1` → 11/11 passed, exit 0 (ruff, pytest, tsc, vitest, sentinel build/scan, real-server runs, npm audit 0 vulns, pip-audit no known vulns; these are point-in-time results).

**Not run:** concurrent multi-process writers (one local writer is assumed for now). Real YouTube responses (Phase 03).

## Gates

| Gate | Status |
|---|---|
| 1 BUILD — APP READY | not run (needs Phases 03–12) |
| 2 LIVE DATA — LIVE SAMPLE READY | not run (will need `YOUTUBE_KEY`) |
| 3 APPROVAL-ONLY — ADVANCED ANALYTICS | off (no approval; all 4 capability rows `off`) |
| 4 OPTIONAL AI | not run |
| 5 VERCEL READINESS | not run |

## Open capability blocks

- `YOUTUBE_KEY`: needed for the Phase 03 live smoke test. Enable YouTube Data API v3 on a personal Google Cloud project, create a key restricted to that API, and set `YOUTUBE_API_KEY` in `%LOCALAPPDATA%\EngineerTestsGTA\private.env` (not the repo `.env`). Never paste it into chat. Without it, Phase 03 completes its mocked/fixture work and records the live smoke test as **blocked**.

## Notes for Phase 03

- Feed parsed `VideoRecord`/`ChannelRecord` objects only (never raw JSON) into `SourceRepository.apply_videos_list` / `apply_channels_list` (≤ 50 IDs), `store_discovered` (search/playlist), and `record_refresh_error` for API errors (do not treat errors as "not returned").
- Live IDs must not contain `:`. Fixtures must contain it.
- Purge and refresh are not scheduled yet: run `db purge` by hand; reads already suppress expired data.
- Starlette's TestClient `httpx` deprecation warning is still harmless; review it at the next dependency upgrade.
- Nothing is committed yet. Commit only when the user asks.

## Next action (exactly one)

Open a fresh agent session in this folder and paste:

```text
Execute Phase 03 only from docs/phases/03.md. Start with CLAUDE.md (or AGENTS.md),
STATUS.md, the current phase file, and only the spec sections the phase references.
Check git status and the previous acceptance gate. Report any failing prerequisite with
evidence, fix only what falls inside this phase, and otherwise stop at the blocker.
Implement the phase, run its acceptance tests, and update STATUS.md and PROMPT_HISTORY.md
with exact results and the next command. Do not start the next phase.
```
