-- 0003 sample selection: discovery runs, hits and eligibility reviews (sample_selection).
-- Hits and reviews reference videos with ON DELETE CASCADE: when a video's API data is
-- purged at expiry, its associations go with it (docs/YOUTUBE_POLICY.md, retention).

CREATE TABLE discovery_runs (
    run_id              TEXT PRIMARY KEY CHECK (length(run_id) BETWEEN 1 AND 64),
    dataset             TEXT NOT NULL CHECK (dataset IN ('synthetic', 'live')),
    mode                TEXT NOT NULL CHECK (mode IN ('plan', 'run', 'resume')),
    status              TEXT NOT NULL DEFAULT 'planned'
                            CHECK (status IN ('planned', 'running', 'paused', 'completed', 'failed')),
    manifest_version    TEXT,
    resumed_from_run_id TEXT REFERENCES discovery_runs (run_id) ON DELETE SET NULL,
    started_at_utc      TEXT NOT NULL,
    finished_at_utc     TEXT,
    duplicate_hits      INTEGER NOT NULL DEFAULT 0 CHECK (duplicate_hits >= 0),
    unavailable_results INTEGER NOT NULL DEFAULT 0 CHECK (unavailable_results >= 0),
    retries             INTEGER NOT NULL DEFAULT 0 CHECK (retries >= 0),
    CHECK (finished_at_utc IS NULL OR finished_at_utc >= started_at_utc),
    CHECK (status IN ('planned', 'running', 'paused') OR finished_at_utc IS NOT NULL)
) STRICT;

CREATE TRIGGER discovery_runs_dataset_ins BEFORE INSERT ON discovery_runs
WHEN NOT EXISTS (SELECT 1 FROM db_meta WHERE key = 'dataset' AND value = NEW.dataset)
BEGIN SELECT RAISE(ABORT, 'discovery_runs.dataset does not match db_meta.dataset'); END;

CREATE TABLE discovery_hits (
    hit_id            INTEGER PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES discovery_runs (run_id) ON DELETE CASCADE,
    video_id          TEXT NOT NULL REFERENCES videos (video_id) ON DELETE CASCADE,
    discovery_path    TEXT NOT NULL CHECK (discovery_path IN (
                          'search_relevance', 'search_date', 'search_popularity',
                          'uploads_playlist', 'curated_playlist', 'fixture')),
    query_text        TEXT NOT NULL DEFAULT '',
    page_index        INTEGER NOT NULL DEFAULT 0 CHECK (page_index >= 0),
    era               TEXT,
    locale            TEXT,
    discovered_at_utc TEXT NOT NULL,
    UNIQUE (run_id, video_id, discovery_path, query_text)
) STRICT;

CREATE INDEX discovery_hits_video_idx ON discovery_hits (video_id);

CREATE TABLE eligibility_reviews (
    video_id            TEXT PRIMARY KEY REFERENCES videos (video_id) ON DELETE CASCADE,
    state               TEXT NOT NULL CHECK (state IN ('accepted', 'excluded', 'needs_review')),
    reasons             TEXT,
    base_game           TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (base_game IN ('gta_v', 'gta_iv', 'gta_sa', 'other', 'unknown')),
    offline_confirmed   TEXT NOT NULL DEFAULT 'uncertain'
                            CHECK (offline_confirmed IN ('yes', 'no', 'uncertain')),
    format_verification TEXT NOT NULL DEFAULT 'unknown' CHECK (format_verification IN (
                            'vertical_short', 'standard_upload', 'build_specific', 'unknown')),
    qualification       TEXT NOT NULL CHECK (qualification IN ('human_verified', 'source_qualified')),
    reviewer            TEXT NOT NULL CHECK (length(trim(reviewer)) > 0),
    reviewed_at_utc     TEXT NOT NULL,
    CHECK (state = 'accepted' OR (reasons IS NOT NULL AND length(trim(reasons)) > 0))
) STRICT;
