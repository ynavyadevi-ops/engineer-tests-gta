# Decisions

These canonical decisions were set in Phase 00 from the master pack. Change one only by adding a new entry that supersedes it.

| ID | Decision | Where it binds |
|---|---|---|
| D-001 | Local-first single-user Windows 11 app. No multi-user product, billing or automation | APP.md |
| D-002 | The **official YouTube Data API is the only external data source**. No scraping or downloads | YOUTUBE_POLICY.md |
| D-003 | **Instagram Reels is an output format only**, never a data source or proxy | APP.md, CONTENT_PLAYBOOK.md |
| D-004 | Stack: Python + `uv` + FastAPI + `httpx` + stdlib SQLite with plain-SQL migrations; React + TypeScript + Vite; no ORM, Docker or Redis | SYSTEM_DESIGN.md |
| D-005 | Servers bind `127.0.0.1`. Secrets are backend-only (env or gitignored private config), never `VITE_*` | SYSTEM_DESIGN.md, SECURITY.md |
| D-006 | **Standard retention:** refresh or delete API data within 30 days, replace current stats, no snapshot archive, suppress expired data | YOUTUBE_POLICY.md, DATA_CONTRACT.md |
| D-007 | Sample: **2,500 GTA V target, 2,000 floor**; GTA IV and San Andreas each 100–200, kept separate | SAMPLING.md |
| D-008 | Three pillars and three lanes. Starter mix 4/12/8. Days 29–30 review/buffer. Default TZ `Asia/Kolkata` | CONTENT_PLAYBOOK.md |
| D-009 | **Deterministic planner.** Editorial priority score 25/25/20/15/15 from editorial inputs only. No API-derived ranking by default | ANALYTICS.md |
| D-010 | Advanced analytics, derived metrics and stat history are **approval-only and fail closed** | GATES.md, YOUTUBE_POLICY.md |
| D-011 | No paid model API in core. AI is optional (Phase 13), one provider, `AI_MODE=off` by default, no YouTube data sent | SECURITY.md |
| D-012 | **Five separate gates**: build, live data, approval-only, optional AI, Vercel readiness. Independent work continues past capability blocks | GATES.md |
| D-013 | `AGENTS.md` is the single canonical agent file. `CLAUDE.md` only imports it (`@AGENTS.md`) | AGENTS.md |
| D-014 | One phase per session using the phase runner command; `STATUS.md` holds exactly one next action | AGENTS.md, STATUS.md |
| D-015 | Vercel is readiness only (Phase 14): same-origin FastAPI + static Vite if verified, no Next.js rewrite; hosted live requires auth + managed Postgres; **no deploy by the agent** | phases/14.md |
| D-016 | The Git repo was initialized in this folder only, on branch `main`, with no commits made by the agent | — |
| D-017 | The master pack stays in the repo root as `MASTER_PACK.md.md` (user's file name, untouched). It is not read after Phase 00 | AGENTS.md |
