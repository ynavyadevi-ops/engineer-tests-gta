# Data contract

Field-level definitions are added in Phase 02, alongside the migrations. This file fixes the canonical rules those definitions must follow.

## Core entities

`videos`, `channels`, `playlist_sources`, `discovery_runs`, `discovery_hits`, `eligibility_reviews`, `public_statistics_current`, `editor_notes`, `briefs`, `calendar_slots`, `publishing_log`, `owner_metric_entries`, `policy_capabilities`.

Audit-eligible statistical history lives in a **separately gated table that is disabled by default** (requires `YOUTUBE_APPROVAL`, see `docs/GATES.md`).

## Required lineage on every YouTube-derived record

- Source resource and endpoint (e.g. `videos.list`).
- `fetched_at_utc`.
- Refresh/delete deadline (the default is at most 30 calendar days after fetch).
- A lineage or ownership class (see data separation below).

## Null and missing semantics

- Nullable values stay `NULL`. Never write zero for convenience.
- Distinguish **API error** (unknown, retry later) from **missing/not provided** (e.g. likes hidden) and from **inaccessible** (deleted, private, removed).
- The UI renders `Unavailable`, `Unknown` or `Not yet collected`. It never infers views from a missing record.
- Read and UI logic must **suppress expired data even when a refresh fails**.
- Stats are stored as **current values** and replaced on refresh. No permanent snapshot archive by default.

## Source hierarchy (UI makes it obvious)

1. **YouTube API**: numbers and metadata.
2. **Editor's firsthand observation**: watched on YouTube or in an official player, with a timestamp.
3. **Own gameplay notes and original drafts.**
4. **Synthetic fixtures**: no real IDs or metrics.

- Human packaging notes are not platform metrics.
- A current thumbnail URL or title is not evidence of the original launch thumbnail or title.
- "Watched" is written only when a human watched it. Human-verified and source-qualified records are labeled differently.

## Data separation (ownership classes)

| Class | Contents | Rule |
|---|---|---|
| `youtube_api` | Refreshable public metadata and stats | Expires; never copied into notes, logs, exports, fixtures, prompts or Git |
| `sample_selection` | Discovery runs, hits, eligibility reviews | Kept with policy-permitted fields only |
| `editor_note` | Independently authored observations and briefs | Survives purge only if it contains no copied API data |
| `own_channel` | Publishing ledger, manually entered Studio metrics | Never mixed with third-party stats |
| `synthetic` | Fixtures and demo data | Clearly labeled; never called real |

Fixture and live databases use separate paths. Persistence goes through repository interfaces (`docs/SYSTEM_DESIGN.md`).

## Migrations

Versioned, plain SQL in `migrations/`. Fresh and repeat runs must be safe. Batch writes are transactional and bounded. Hosted (Postgres) migrations, added in Phase 14, run by a deliberate one-time command, never automatically on a cold start.
