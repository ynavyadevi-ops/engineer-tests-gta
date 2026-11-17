-- 0004 editorial and own-channel data: notes, briefs, plans, calendar slots, publishing
-- ledger, manual Studio checkpoints.
--
-- * editor_note rows are independently authored text. Links to YouTube videos live only in
--   the *_source_refs association tables, which cascade-delete when the video is purged.
--   The retention purge also redacts copied API fragments from associated text.
-- * own_channel rows (publishing_log, owner_metric_entries) never hold third-party stats.
-- * Instagram is an output lane only: no metrics may be recorded for it.

CREATE TABLE editor_notes (
    note_id         INTEGER PRIMARY KEY,
    kind            TEXT NOT NULL CHECK (kind IN (
                        'watched_observation', 'own_gameplay', 'idea', 'packaging_note')),
    body            TEXT NOT NULL CHECK (length(trim(body)) > 0),
    -- Set only when a human actually watched; required for watched observations.
    watched_at_utc  TEXT,
    author          TEXT NOT NULL CHECK (length(trim(author)) > 0),
    created_at_utc  TEXT NOT NULL,
    updated_at_utc  TEXT NOT NULL,
    redacted_at_utc TEXT,
    CHECK ((kind = 'watched_observation') = (watched_at_utc IS NOT NULL))
) STRICT;

CREATE TABLE note_source_refs (
    note_id  INTEGER NOT NULL REFERENCES editor_notes (note_id) ON DELETE CASCADE,
    video_id TEXT NOT NULL REFERENCES videos (video_id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, video_id)
) STRICT;

CREATE INDEX note_source_refs_video_idx ON note_source_refs (video_id);

-- Brief template (docs/CONTENT_PLAYBOOK.md). Completeness is enforced by the planner;
-- the store allows drafts, so only identity fields are NOT NULL here.
CREATE TABLE briefs (
    brief_id               INTEGER PRIMARY KEY,
    working_title          TEXT NOT NULL CHECK (length(trim(working_title)) > 0),
    alternate_title        TEXT,
    pillar                 TEXT NOT NULL CHECK (pillar IN (
                               'systems_myth_tests', 'map_world_hidden_details',
                               'missions_useful_discoveries')),
    format                 TEXT NOT NULL CHECK (format IN ('long_form', 'short', 'reel')),
    viewer_question        TEXT,
    original_angle         TEXT,
    first_frame            TEXT,
    cold_open              TEXT,
    shot_checklist         TEXT,
    verification_plan      TEXT,
    thumbnail_hypothesis_a TEXT,
    thumbnail_hypothesis_b TEXT,
    cover_design           TEXT,
    payoff_beat            TEXT,
    rough_duration_seconds INTEGER CHECK (rough_duration_seconds IS NULL OR rough_duration_seconds > 0),
    spoiler_level          TEXT CHECK (spoiler_level IS NULL OR spoiler_level IN ('none', 'light', 'heavy')),
    time_cost_hours        REAL CHECK (time_cost_hours IS NULL OR time_cost_hours >= 0),
    fallback_plan          TEXT,
    reel_adaptation        TEXT,
    success_measure        TEXT,
    review_at_utc          TEXT,
    capture_id             TEXT,
    gta_vi_status          TEXT NOT NULL DEFAULT 'unknown'
                               CHECK (gta_vi_status IN ('unknown', 'verified_in_own_gameplay')),
    created_at_utc         TEXT NOT NULL,
    updated_at_utc         TEXT NOT NULL,
    redacted_at_utc        TEXT
) STRICT;

CREATE TABLE brief_source_refs (
    brief_id INTEGER NOT NULL REFERENCES briefs (brief_id) ON DELETE CASCADE,
    video_id TEXT NOT NULL REFERENCES videos (video_id) ON DELETE CASCADE,
    role     TEXT NOT NULL DEFAULT 'example' CHECK (role IN ('example', 'evidence')),
    PRIMARY KEY (brief_id, video_id)
) STRICT;

CREATE INDEX brief_source_refs_video_idx ON brief_source_refs (video_id);

CREATE TABLE plans (
    plan_id             INTEGER PRIMARY KEY,
    title               TEXT NOT NULL CHECK (length(trim(title)) > 0),
    -- Local calendar date chosen by the creator; never a hardcoded launch date.
    start_date          TEXT NOT NULL CHECK (start_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    timezone            TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    weekly_budget_hours REAL NOT NULL DEFAULT 11 CHECK (weekly_budget_hours > 0),
    status              TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'archived')),
    created_at_utc      TEXT NOT NULL,
    updated_at_utc      TEXT NOT NULL
) STRICT;

CREATE TABLE calendar_slots (
    slot_id        INTEGER PRIMARY KEY,
    plan_id        INTEGER NOT NULL REFERENCES plans (plan_id) ON DELETE CASCADE,
    day_index      INTEGER NOT NULL CHECK (day_index BETWEEN 1 AND 30),
    lane           TEXT NOT NULL CHECK (lane IN (
                       'youtube_long_form', 'youtube_short', 'instagram_reel', 'none')),
    action         TEXT NOT NULL CHECK (action IN ('film', 'edit', 'publish', 'review', 'rest', 'buffer')),
    brief_id       INTEGER REFERENCES briefs (brief_id) ON DELETE SET NULL,
    capture_id     TEXT,
    pinned         INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
    status         TEXT NOT NULL DEFAULT 'planned'
                       CHECK (status IN ('planned', 'done', 'skipped', 'replaced')),
    slot_note      TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    CHECK (action NOT IN ('film', 'edit', 'publish') OR lane <> 'none')
) STRICT;

CREATE INDEX calendar_slots_plan_day_idx ON calendar_slots (plan_id, day_index);

-- Own-channel publishing ledger and weekly review verdicts.
CREATE TABLE publishing_log (
    entry_id          INTEGER PRIMARY KEY,
    brief_id          INTEGER REFERENCES briefs (brief_id) ON DELETE SET NULL,
    lane              TEXT NOT NULL CHECK (lane IN ('youtube_long_form', 'youtube_short', 'instagram_reel')),
    published_at_utc  TEXT,
    own_video_ref     TEXT,
    title_variant     TEXT,
    thumbnail_variant TEXT,
    hypothesis        TEXT,
    capture_minutes   INTEGER CHECK (capture_minutes IS NULL OR capture_minutes >= 0),
    edit_minutes      INTEGER CHECK (edit_minutes IS NULL OR edit_minutes >= 0),
    change_log        TEXT,
    verdict           TEXT CHECK (verdict IS NULL OR verdict IN ('promising', 'retest', 'retire')),
    verdict_rationale TEXT,
    outcome_notes     TEXT,
    created_at_utc    TEXT NOT NULL,
    updated_at_utc    TEXT NOT NULL,
    CHECK (verdict IS NULL OR (verdict_rationale IS NOT NULL AND length(trim(verdict_rationale)) > 0))
) STRICT;

-- Optional manual YouTube Studio checkpoints (own channel only). NULL = left blank.
CREATE TABLE owner_metric_entries (
    metric_id                 INTEGER PRIMARY KEY,
    entry_id                  INTEGER NOT NULL REFERENCES publishing_log (entry_id) ON DELETE CASCADE,
    checkpoint                TEXT NOT NULL CHECK (checkpoint IN ('24h', '7d')),
    views                     INTEGER CHECK (views IS NULL OR views >= 0),
    likes                     INTEGER CHECK (likes IS NULL OR likes >= 0),
    comments                  INTEGER CHECK (comments IS NULL OR comments >= 0),
    avg_view_duration_seconds INTEGER CHECK (avg_view_duration_seconds IS NULL OR avg_view_duration_seconds >= 0),
    impressions_ctr_percent   REAL CHECK (impressions_ctr_percent IS NULL
                                          OR impressions_ctr_percent BETWEEN 0 AND 100),
    source                    TEXT NOT NULL DEFAULT 'studio_manual' CHECK (source = 'studio_manual'),
    entered_at_utc            TEXT NOT NULL,
    UNIQUE (entry_id, checkpoint)
) STRICT;

CREATE TRIGGER owner_metrics_no_instagram BEFORE INSERT ON owner_metric_entries
WHEN (SELECT lane FROM publishing_log WHERE entry_id = NEW.entry_id) = 'instagram_reel'
BEGIN SELECT RAISE(ABORT, 'Instagram metrics are out of scope'); END;
