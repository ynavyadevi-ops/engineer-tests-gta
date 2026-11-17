# STATUS

**Last completed phase:** 03 — YouTube client and small live smoke test (2026-11-17). The implementation is done, but the **live smoke test is blocked** on `YOUTUBE_KEY`
**Current phase:** none in progress
**App runnable:** yes, locally (`scripts\run.ps1 -Build` → `http://127.0.0.1:8765/`). Commands: `uv run --locked python -m gta_lab db migrate|status|purge` and `... youtube smoke [--max-videos 5-15] [--dry-run]`

## Implementation vs live verification

| Phase | Implementation | Live verification |
|---|---|---|
| 00–02 | done | n/a (no YouTube calls by design) |
| 03 | done | **blocked**: no `YOUTUBE_API_KEY` configured (`youtube smoke` → exit 3 `blocked`) |
| 04–12 | not started | not started |
| 13 (optional AI) | not started | not started |
| 14 (Vercel readiness) | not started | hosted preview: not deployed / not verified |

## Phase 03 acceptance (run 2026-11-17, Windows 11, Python 3.12.13; mocked transport, no network)

| Check | Result | Evidence |
|---|---|---|
| Seed normalization | passed | `test_youtube_ids.py`: watch/youtu.be/shorts/embed/live/channel/@handle/playlist links and bare IDs normalize. Rejected: other hosts, look-alike hosts, credentials, ports, bad schemes, multiple `v=`, malformed IDs. Nothing is fetched. `/shorts/` gives a plain video seed |
| Batch | passed | 122 IDs (2 duplicates) → 3 `videos.list` calls of 50/50/20 and 3 units. Not-returned IDs reported. Batches >50, duplicates or bad IDs are refused before sending (0 units). No `maxResults` sent with `id` |
| Partial fields | passed | Exact `part`/`fields` masks asserted. No description, comment, caption, file, player or tag fields. Search is `part=id,type=video`, IDs only |
| Malformed | passed | 15 malformed bodies (not JSON, wrong types, bad, duplicate or unrequested IDs, negative, text or boolean counts, bad timestamp) → `MalformedResponseError` with 1 request and no retry. Odd optional fields drop to `None` and are counted. Pagination with a repeating token stops |
| Missing metrics | passed | Hidden likes/comments → `None` and listed in `missing_stats`. `0` stays `0`. Missing `statistics` → `None` |
| No Shorts inference | passed | A 30 s video gets no Shorts-like field |
| Retry | passed | Timeout, network, 500, 503, 429 and 403 rate-limit reasons are retried with full jitter (0–0.5 s, then 0–1 s). Capped at 4 attempts. `Retry-After` honoured up to 8 s |
| No-retry stops | passed | Bad key (3 forms + 401) → `bad_key`. `quotaExceeded`/`dailyLimitExceeded` → `quota_exhausted` (resumable). Other 403 → `permission`. 404 and 400 → clean stops. Each makes exactly 1 request |
| Quota | passed | Cost table pinned to the docs verified 2026-11-17: search 1/call in its own bucket; videos/channels/playlistItems 1 unit each; every attempt charged. The local budget refuses before sending. Search and units buckets are separate. Resume works by remaining IDs or page token |
| Secret redaction | passed | A key-shaped sentinel is absent from exceptions (str/repr/traceback/vars), logs, client repr, smoke report and CLI output across 8 failure types. Mutation checks (URL added to a log line; 403 made retryable) were caught, then reverted |
| Live smoke (5–15 videos) | **blocked** | `YOUTUBE_API_KEY` not configured. `youtube smoke` printed `blocked` and exited 3. Planned cost: 1 search call + 1 unit (`--dry-run`) |
| Console quotas | **blocked** | No Cloud project yet. The docs' defaults are recorded in `docs/YOUTUBE_POLICY.md` |

pytest: 217 passed (91 earlier + 126 Phase 03). `scripts\check.ps1` → 11/11 passed, exit 0 (ruff, pytest, tsc, vitest, sentinel build/scan, real-server runs, npm audit 0 vulns, pip-audit no known vulns; point-in-time). No new dependencies (stdlib `urllib` transport).

**Not run:** real API responses, so the error-reason mapping for invalid key, `accessNotConfigured` and rate limits is unconfirmed against live output. The adapter is not wired to the DB/collector yet (Phase 04).

## Gates

| Gate | Status |
|---|---|
| 1 BUILD — APP READY | not run (needs Phases 04–12) |
| 2 LIVE DATA — LIVE SAMPLE READY | not run (will need `YOUTUBE_KEY`) |
| 3 APPROVAL-ONLY — ADVANCED ANALYTICS | off (no approval; all 4 capability rows `off`) |
| 4 OPTIONAL AI | not run |
| 5 VERCEL READINESS | not run |

## Open capability blocks

- `YOUTUBE_KEY`: needed for the Phase 03 live smoke test. Enable YouTube Data API v3 on a personal Google Cloud project, create a key restricted to that API, and set `YOUTUBE_API_KEY` in `%LOCALAPPDATA%\EngineerTestsGTA\private.env` (not the repo `.env`). Never paste it into chat. Without it, Phase 03 completes its mocked/fixture work and records the live smoke test as **blocked**.

## Notes for Phase 04

- Use `YouTubeClient` (`backend/gta_lab/youtube/`). Feed `Hydration.batches` into `SourceRepository.apply_videos_list(requested, page.records)` and IDs from search/playlist into `store_discovered`. A stop (`transient`/`malformed` on a batch) goes to `record_refresh_error`, never to "not returned".
- Resume points: `Hydration.remaining_ids` and `PagedIds.resume_token`. Resumable stop kinds are `quota_exhausted` and `budget_exhausted`.
- Run `youtube smoke` first once a key exists, and record its counts here (Phase 03 live item).
- Purge and refresh are still unscheduled. Starlette's TestClient `httpx` warning is harmless. Nothing is committed yet; commit only when the user asks.

## Next action (exactly one)

Open a fresh agent session in this folder and paste the command below. Once you have a key, run `uv run --locked python -m gta_lab youtube smoke --max-videos 10` yourself first. That closes the blocked Phase 03 live item.

```text
Execute Phase 04 only from docs/phases/04.md. Start with CLAUDE.md (or AGENTS.md),
STATUS.md, the current phase file, and only the spec sections the phase references.
Check git status and the previous acceptance gate. Report any failing prerequisite with
evidence, fix only what falls inside this phase, and otherwise stop at the blocker.
Implement the phase, run its acceptance tests, and update STATUS.md and PROMPT_HISTORY.md
with exact results and the next command. Do not start the next phase.
```
