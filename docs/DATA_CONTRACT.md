# Data contract

This file fixes the canonical rules. The field-level definitions (Phase 02) at the end mirror `migrations/0001`–`0004`. If the two ever disagree, the SQL files are authoritative.

## Core entities

`videos`, `channels`, `playlist_sources`, `discovery_runs`, `discovery_hits`, `eligibility_reviews`, `public_statistics_current`, `editor_notes`, `briefs`, `calendar_slots`, `publishing_log`, `owner_metric_entries`, `policy_capabilities`. Phase 02 added these supporting tables: `plans` (parent of calendar slots), `note_source_refs` and `brief_source_refs` (the only links from authored text to videos), `db_meta` (dataset identity) and `schema_migrations` (runner bookkeeping).

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

Local runner (`backend/gta_lab/db/migrate.py`): files are named `NNNN_name.sql` and numbered contiguously from `0001`. Each pending file runs in one transaction together with its `schema_migrations` row (version, name, SHA-256, `applied_at_utc`), so a failure leaves no partial schema. A repeat run is a no-op. If an applied file's checksum changed (CRLF is normalised first), or the DB knows a version the code does not ship, the runner stops. Never edit an applied migration; add a new file.

## Field definitions (Phase 02)

Conventions for every table:

- SQLite `STRICT` tables. Timestamps are UTC text `YYYY-MM-DDTHH:MM:SSZ`, checked by `GLOB`, so they sort chronologically. Calendar dates are `YYYY-MM-DD`.
- Every YouTube-derived row has `lineage_class` (`youtube_api` in the live DB, `synthetic` in the fixture DB), `source_endpoint`, `fetched_at_utc`, `refresh_due_at_utc` and `expires_at_utc`. A `CHECK` holds `expires_at_utc` to at most 30 days after `fetched_at_utc`.
- Fixture IDs contain `:` (for example `fixture:vid-001`), so they can never be real YouTube IDs. Live IDs must match `[A-Za-z0-9_-]`. Triggers reject any row whose lineage disagrees with `db_meta.dataset`.
- No column stores raw API response bodies, descriptions, comment text or JSON payloads. A test scans the schema to confirm this.

### Identity and policy (`0001_foundation`)

| Table | Fields |
|---|---|
| `db_meta` | `key`, `value`. The `dataset` key (`synthetic`/`live`) is written once on first open and is immutable (triggers block updates and deletes) |
| `policy_capabilities` | `capability` (`cohort_analytics`, `statistical_history`, `api_taxonomy_enrichment`, `predictive_model`), `status` `off`/`on` (default `off`), `proof_source`, `proof_date`, `updated_at_utc`. `on` requires both proof fields. No code path sets `on` |

### YouTube-derived sources (`0002_youtube_sources`)

| Table | Fields | Null / state meaning |
|---|---|---|
| `videos` | `video_id` PK, `lineage_class`, `access_state` (`available`/`inaccessible`), `channel_id`, `channel_title`, `title`, `published_at_utc`, `duration_iso`, `category_id`, `default_language`, `thumbnail_url`, `embeddable` (0/1), `source_endpoint` (`videos.list`, `search.list`, `playlistItems.list`, `fixture`), `fetched_at_utc`, `refresh_due_at_utc`, `expires_at_utc`, `last_refresh_attempt_utc`, `last_refresh_outcome` (`ok`/`api_error`/`not_returned`), `last_error_code`, `title_changed_at_utc`, `thumbnail_changed_at_utc` | Metadata `NULL` = not provided. An `inaccessible` row is a tombstone: a `CHECK` forces every metadata field to `NULL`. `*_changed_at_utc` records when a refresh saw a different title or thumbnail. The old value is **not** kept |
| `channels` | `channel_id` PK, `lineage_class`, `access_state`, `title`, `uploads_playlist_id`, `source_endpoint` (`channels.list`, `search.list`, `fixture`), the lineage/deadline columns, refresh-outcome columns | Same as `videos` |
| `public_statistics_current` | `video_id` PK → `videos` (cascade), `lineage_class`, `view_count`, `like_count`, `comment_count` (each `NULL` or ≥ 0), `source_endpoint`, `fetched_at_utc`, `expires_at_utc` | `NULL` count = YouTube did not provide it (for example hidden likes). Never 0. One row per video, replaced on refresh. A trigger allows stats only for an available video |
| `playlist_sources` | `playlist_id` PK, `kind` (`uploads`/`curated`), `label` (editor-written), `enabled`, `added_at_utc` | Editor configuration. Holds no API metadata |

### Sample selection (`0003_sample_selection`)

| Table | Fields |
|---|---|
| `discovery_runs` | `run_id` PK, `dataset` (must equal `db_meta.dataset`), `mode` (`plan`/`run`/`resume`), `status` (`planned`, `running`, `paused`, `completed`, `failed`), `manifest_version`, `resumed_from_run_id`, `started_at_utc`, `finished_at_utc` (required once completed or failed), counters `duplicate_hits`, `unavailable_results`, `retries` |
| `discovery_hits` | `hit_id`, `run_id` → runs (cascade), `video_id` → videos (cascade), `discovery_path` (`search_relevance`, `search_date`, `search_popularity`, `uploads_playlist`, `curated_playlist`, `fixture`), `query_text` (curated query, default `''`), `page_index`, `era`, `locale`, `discovered_at_utc`. `UNIQUE(run_id, video_id, discovery_path, query_text)`: a repeat inside one run is counted in `duplicate_hits`, not stored |
| `eligibility_reviews` | `video_id` PK → videos (cascade), `state` (`accepted`/`excluded`/`needs_review`), `reasons` (required unless accepted), `base_game` (`gta_v`, `gta_iv`, `gta_sa`, `other`, `unknown`), `offline_confirmed` (`yes`/`no`/`uncertain`), `format_verification` (`vertical_short`, `standard_upload`, `build_specific`, `unknown`), `qualification` (`human_verified`/`source_qualified`), `reviewer`, `reviewed_at_utc` |

### Editorial and own channel (`0004_editorial`)

| Table | Fields |
|---|---|
| `editor_notes` | `note_id`, `kind` (`watched_observation`, `own_gameplay`, `idea`, `packaging_note`), `body`, `watched_at_utc` (required for, and only for, `watched_observation`), `author`, `created_at_utc`, `updated_at_utc`, `redacted_at_utc` |
| `note_source_refs`, `brief_source_refs` | Owner ID plus `video_id` as the PK, both with cascade. `brief_source_refs.role` is `example`/`evidence` |
| `briefs` | `brief_id`, `working_title` (required), `alternate_title`, `pillar` (`systems_myth_tests`, `map_world_hidden_details`, `missions_useful_discoveries`), `format` (`long_form`/`short`/`reel`), `viewer_question`, `original_angle`, `first_frame`, `cold_open`, `shot_checklist`, `verification_plan`, `thumbnail_hypothesis_a`, `thumbnail_hypothesis_b`, `cover_design`, `payoff_beat`, `rough_duration_seconds`, `spoiler_level` (`none`/`light`/`heavy`), `time_cost_hours`, `fallback_plan`, `reel_adaptation`, `success_measure`, `review_at_utc`, `capture_id`, `gta_vi_status` (`unknown`/`verified_in_own_gameplay`), timestamps, `redacted_at_utc`. Drafts are allowed. The planner (Phase 09) enforces template completeness |
| `plans` | `plan_id`, `title`, `start_date` (chosen by the creator, never hardcoded), `timezone` (default `Asia/Kolkata`), `weekly_budget_hours` (default 11), `status` (`draft`/`active`/`archived`), timestamps |
| `calendar_slots` | `slot_id`, `plan_id` (cascade), `day_index` 1–30, `lane` (`youtube_long_form`, `youtube_short`, `instagram_reel`, `none`), `action` (`film`, `edit`, `publish`, `review`, `rest`, `buffer`; film/edit/publish need a lane), `brief_id` (set null), `capture_id`, `pinned`, `status` (`planned`, `done`, `skipped`, `replaced`), `slot_note`, timestamps |
| `publishing_log` | `entry_id`, `brief_id` (set null), `lane`, `published_at_utc`, `own_video_ref`, `title_variant`, `thumbnail_variant`, `hypothesis`, `capture_minutes`, `edit_minutes`, `change_log`, `verdict` (`promising`/`retest`/`retire`, requires `verdict_rationale`), `outcome_notes`, timestamps |
| `owner_metric_entries` | `metric_id`, `entry_id` (cascade), `checkpoint` (`24h`/`7d`, unique per entry), `views`, `likes`, `comments`, `avg_view_duration_seconds`, `impressions_ctr_percent` (all `NULL` = left blank), `source` = `studio_manual`, `entered_at_utc`. A trigger rejects any row for an `instagram_reel` entry |

The gated statistical-history table is **not created**. It needs `YOUTUBE_APPROVAL` and its own migration.

## Lifecycle implementation (Phase 02)

Code lives in `backend/gta_lab/db/` (`connection`, `migrate`, `sources`, `runs`, `editorial`, `planning`, `retention`, `health`). The clock is in `backend/gta_lab/clock.py`.

- **Read guard.** Every repository read filters `expires_at_utc > now`, so stale data is never read into Python, whatever the last refresh outcome. Expired-but-unpurged videos read as `expired`, with no fields.
- **Refresh.** `apply_videos_list` takes ≤ 50 parsed records. Returned IDs are fully replaced (metadata and current stats, new deadlines). Requested-but-not-returned IDs become `inaccessible` tombstones: metadata and stats are dropped immediately, and the tombstone keeps its original expiry. An already-expired row that is touched again is purged (with redaction) before anything new is written. `record_refresh_error` sets `api_error` and never changes data, fetch time or expiry. `store_discovered` (search/playlist candidates) never overwrites a fresh row, so it cannot extend the life of older fields.
- **Proactive refresh.** `RetentionPolicy` defaults to a 30-day expiry with a 5-day lead (`refresh_due_at_utc` = expiry − 5 days). `due_for_refresh` lists available, unexpired rows past their due time. Values above 30 days are rejected.
- **Display states.** `StatValue` is `value`, `not_provided` (shown as Unavailable), `unknown` (API error and no current stats), `not_yet_collected` or `unavailable` (inaccessible/expired).
- **Purge.** `purge_expired` deletes expired videos, channels and stats in one transaction. Cascades remove hits, eligibility reviews and source references. Before that, the current title, channel title and video ID of each purged video are redacted from linked note and brief text, and `redacted_at_utc` is set. `secure_delete` is on, and the WAL is checkpointed with `TRUNCATE` afterwards.
- **Copy guard.** Notes and briefs that contain the current title or channel title of a referenced video are refused. References can only be written to available, unexpired videos. Known limit: redaction covers only text linked to the purged video, and only exact title, channel-title and ID matches. Paraphrases and unlinked copies are not detected.
- **Exports.** `export_brief_text` and `export_plan_text` contain authored text only, plus watch links for references that are still eligible. Other references are counted as "no longer available". No titles, thumbnails or metrics are exported.
- **Isolation and backups.** Demo and live use separate files. The dataset is bound on first open, and reopening as the other dataset raises an error. The live DB refuses to open inside a cloud-synced folder, because a synced copy is an uncontrolled backup. No backup or DB-export feature exists.
- **Commands.** `uv run --locked python -m gta_lab db migrate|status|purge [--mode demo|live] [--data-dir PATH]`. `status` opens the DB read-only and prints counts only. `/api/status` includes the same `data_health` counts and never creates the database. Purge runs only when invoked; reads suppress expired data in the meantime. Scheduling the purge and the refresh is a later phase.
