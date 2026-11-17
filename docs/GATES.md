# Gates and blocking rules

## Status vocabulary

Every check and gate is recorded with exactly one of these statuses:

- **passed**: ran, with evidence (command plus result summary).
- **failed**: ran and did not meet the criterion.
- **not run**: in scope, but it was not executed yet.
- **blocked**: cannot run until a named capability exists (see below).

Implementation status and verification status are always recorded separately. "Code written" never means "verified live".

## Independent work vs capability blocks

**Independent work** needs nothing outside the repo and the installed toolchain: code, migrations, fixture/demo mode, mocked API tests, UI, synthetic data, docs. It must be completed even when live work is blocked.

A **capability block** is a step that cannot run until something outside the agent's control exists. Each has an exact unblock action owned by the user.

| Capability | Blocks | Unblocked by (user action) |
|---|---|---|
| `YOUTUBE_KEY` | Phase 03 live smoke, Phase 04 live collection, Phase 05 live audit | Enable YouTube Data API v3 on a personal Google Cloud project, create a key restricted to that API, and place it in the private local config (never in chat) |
| `YOUTUBE_QUOTA` | Live collection beyond the current daily allocation | Wait for the next quota window or get an authorized extension. Never use extra projects or keys to get around limits |
| `HUMAN_REVIEW` | Watched observations, packaging audit, eligibility adjudication | A human watches and records it |
| `YOUTUBE_APPROVAL` | Any advanced analytics, derived metrics, extended retention, API-derived enrichment | Written YouTube API compliance approval for the exact use case (`docs/YOUTUBE_POLICY.md`) |
| `OWN_CHANNEL_DATA` | Own-channel checkpoints (Phase 10) | The creator publishes and enters Studio numbers by hand |
| `AI_KEY` | Phase 13 live provider test only | User adds one Gemini **or** Anthropic API key in server-only config |
| `HOSTED_INFRA` | Phase 14 hosted Postgres or preview tests | User-provisioned test Postgres or Vercel project. The agent never provisions |

**Rule:** when a capability is missing, finish all independent work in labeled fixture mode. Record the exact blocked task (command, phase, capability). Never fake the blocked result.

## The five gates (reported separately)

| # | Gate | Passes when | Never implied by |
|---|---|---|---|
| 1 | **BUILD — APP READY** | Locked installs repeat. Fixture-driven backend, frontend and browser tests pass. App starts with no key. The Phase 11 quality and security checks pass | — |
| 2 | **LIVE DATA — LIVE SAMPLE READY** | At least **2,000** distinct qualified, hydrated GTA V rows are present and externally verified through the documented YouTube pipeline (aim 2,500). Comparator and manual-observation coverage are stated separately. Data is within retention | Gate 1 |
| 3 | **APPROVAL-ONLY — ADVANCED ANALYTICS READY** | Each claimed feature has scope-specific YouTube approval (proof source and date recorded) and passes its own evidence gate. Default: **not applicable / off** | Gates 1–2, or any config flag |
| 4 | **OPTIONAL AI — AI OPTIONAL** | Core passes with no model key. If Phase 13 is built, its prohibited-field, timeout and editability tests pass. Default: **skipped** | — |
| 5 | **VERCEL READINESS** | Reported as three statuses: (a) deployment config/build verified locally; (b) hosted preview **not deployed / not verified** unless the user deployed it and it was tested; (c) hosted live prerequisites outstanding unless actually tested | Existence of a config file |

Phase-level acceptance criteria are in each `docs/phases/NN.md`. Gates 1–4 are declared in Phase 12 and gate 5 in Phase 14.
