-- 0002 YouTube-derived source data (ownership class youtube_api, or synthetic in fixture DBs).
--
-- Rules enforced here (docs/DATA_CONTRACT.md, docs/YOUTUBE_POLICY.md):
-- * Every row carries lineage: source endpoint, fetched_at_utc, refresh_due_at_utc and
--   expires_at_utc. expires_at_utc is at most 30 calendar days after fetched_at_utc.
-- * Current values only. A refresh replaces the row; nothing here is a history archive.
-- * No raw response bodies: only typed, policy-permitted columns exist.
-- * NULL means "not provided by the API" (for example hidden likes). Never write 0 for it.
-- * Inaccessible (deleted/private/removed) videos keep a tombstone with no metadata.
-- * Fixture rows ('synthetic') use IDs containing ':' so they can never look like real IDs,
--   and triggers stop a row's lineage from disagreeing with db_meta.dataset.
--
-- All timestamps are UTC text in the fixed form YYYY-MM-DDTHH:MM:SSZ (sorts as time).

CREATE TABLE channels (
    channel_id               TEXT PRIMARY KEY,
    lineage_class            TEXT NOT NULL CHECK (lineage_class IN ('youtube_api', 'synthetic')),
    access_state             TEXT NOT NULL DEFAULT 'available'
                                 CHECK (access_state IN ('available', 'inaccessible')),
    title                    TEXT,
    uploads_playlist_id      TEXT,
    source_endpoint          TEXT NOT NULL
                                 CHECK (source_endpoint IN ('channels.list', 'search.list', 'fixture')),
    fetched_at_utc           TEXT NOT NULL,
    refresh_due_at_utc       TEXT NOT NULL,
    expires_at_utc           TEXT NOT NULL,
    last_refresh_attempt_utc TEXT,
    last_refresh_outcome     TEXT NOT NULL DEFAULT 'ok'
                                 CHECK (last_refresh_outcome IN ('ok', 'api_error', 'not_returned')),
    last_error_code          TEXT,
    CHECK (fetched_at_utc GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'),
    CHECK (expires_at_utc GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'),
    CHECK (refresh_due_at_utc GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'),
    CHECK (expires_at_utc > fetched_at_utc),
    CHECK (expires_at_utc <= strftime('%Y-%m-%dT%H:%M:%SZ', fetched_at_utc, '+30 days')),
    CHECK (refresh_due_at_utc <= expires_at_utc),
    CHECK ((lineage_class = 'synthetic') = (source_endpoint = 'fixture')),
    CHECK (lineage_class <> 'synthetic' OR instr(channel_id, ':') > 0),
    CHECK (lineage_class <> 'youtube_api' OR channel_id NOT GLOB '*[^A-Za-z0-9_-]*'),
    CHECK (access_state = 'available' OR (title IS NULL AND uploads_playlist_id IS NULL))
) STRICT;

CREATE TABLE videos (
    video_id                 TEXT PRIMARY KEY,
    lineage_class            TEXT NOT NULL CHECK (lineage_class IN ('youtube_api', 'synthetic')),
    access_state             TEXT NOT NULL DEFAULT 'available'
                                 CHECK (access_state IN ('available', 'inaccessible')),
    channel_id               TEXT,
    channel_title            TEXT,
    title                    TEXT,
    published_at_utc         TEXT,
    duration_iso             TEXT,
    category_id              TEXT,
    default_language         TEXT,
    thumbnail_url            TEXT,
    embeddable               INTEGER CHECK (embeddable IN (0, 1)),
    source_endpoint          TEXT NOT NULL CHECK (source_endpoint IN (
                                 'videos.list', 'search.list', 'playlistItems.list', 'fixture')),
    fetched_at_utc           TEXT NOT NULL,
    refresh_due_at_utc       TEXT NOT NULL,
    expires_at_utc           TEXT NOT NULL,
    last_refresh_attempt_utc TEXT,
    last_refresh_outcome     TEXT NOT NULL DEFAULT 'ok'
                                 CHECK (last_refresh_outcome IN ('ok', 'api_error', 'not_returned')),
    last_error_code          TEXT,
    title_changed_at_utc     TEXT,
    thumbnail_changed_at_utc TEXT,
    CHECK (fetched_at_utc GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'),
    CHECK (expires_at_utc GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'),
    CHECK (refresh_due_at_utc GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'),
    CHECK (expires_at_utc > fetched_at_utc),
    CHECK (expires_at_utc <= strftime('%Y-%m-%dT%H:%M:%SZ', fetched_at_utc, '+30 days')),
    CHECK (refresh_due_at_utc <= expires_at_utc),
    CHECK ((lineage_class = 'synthetic') = (source_endpoint = 'fixture')),
    CHECK (lineage_class <> 'synthetic' OR instr(video_id, ':') > 0),
    CHECK (lineage_class <> 'youtube_api' OR video_id NOT GLOB '*[^A-Za-z0-9_-]*'),
    CHECK (access_state = 'available' OR (
        channel_id IS NULL AND channel_title IS NULL AND title IS NULL
        AND published_at_utc IS NULL AND duration_iso IS NULL AND category_id IS NULL
        AND default_language IS NULL AND thumbnail_url IS NULL AND embeddable IS NULL))
) STRICT;

CREATE INDEX videos_expires_idx ON videos (expires_at_utc);
CREATE INDEX videos_refresh_due_idx ON videos (refresh_due_at_utc);

-- Current public statistics, one row per video, replaced on refresh (no snapshots).
CREATE TABLE public_statistics_current (
    video_id        TEXT PRIMARY KEY REFERENCES videos (video_id) ON DELETE CASCADE,
    lineage_class   TEXT NOT NULL CHECK (lineage_class IN ('youtube_api', 'synthetic')),
    view_count      INTEGER CHECK (view_count IS NULL OR view_count >= 0),
    like_count      INTEGER CHECK (like_count IS NULL OR like_count >= 0),
    comment_count   INTEGER CHECK (comment_count IS NULL OR comment_count >= 0),
    source_endpoint TEXT NOT NULL CHECK (source_endpoint IN ('videos.list', 'fixture')),
    fetched_at_utc  TEXT NOT NULL,
    expires_at_utc  TEXT NOT NULL,
    CHECK (fetched_at_utc GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'),
    CHECK (expires_at_utc GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'),
    CHECK (expires_at_utc > fetched_at_utc),
    CHECK (expires_at_utc <= strftime('%Y-%m-%dT%H:%M:%SZ', fetched_at_utc, '+30 days')),
    CHECK ((lineage_class = 'synthetic') = (source_endpoint = 'fixture'))
) STRICT;

CREATE INDEX public_statistics_expires_idx ON public_statistics_current (expires_at_utc);

-- Editor-configured discovery sources (sample_selection). Holds no API metadata.
CREATE TABLE playlist_sources (
    playlist_id    TEXT PRIMARY KEY,
    kind           TEXT NOT NULL CHECK (kind IN ('uploads', 'curated')),
    label          TEXT NOT NULL CHECK (length(trim(label)) > 0),
    enabled        INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    added_at_utc   TEXT NOT NULL
) STRICT;

-- Lineage must agree with the database's dataset (fixture/live isolation).
CREATE TRIGGER channels_lineage_ins BEFORE INSERT ON channels
WHEN NOT EXISTS (SELECT 1 FROM db_meta WHERE key = 'dataset'
                 AND value = CASE NEW.lineage_class WHEN 'synthetic' THEN 'synthetic' ELSE 'live' END)
BEGIN SELECT RAISE(ABORT, 'lineage_class does not match db_meta.dataset'); END;

CREATE TRIGGER channels_lineage_upd BEFORE UPDATE OF lineage_class ON channels
WHEN NOT EXISTS (SELECT 1 FROM db_meta WHERE key = 'dataset'
                 AND value = CASE NEW.lineage_class WHEN 'synthetic' THEN 'synthetic' ELSE 'live' END)
BEGIN SELECT RAISE(ABORT, 'lineage_class does not match db_meta.dataset'); END;

CREATE TRIGGER videos_lineage_ins BEFORE INSERT ON videos
WHEN NOT EXISTS (SELECT 1 FROM db_meta WHERE key = 'dataset'
                 AND value = CASE NEW.lineage_class WHEN 'synthetic' THEN 'synthetic' ELSE 'live' END)
BEGIN SELECT RAISE(ABORT, 'lineage_class does not match db_meta.dataset'); END;

CREATE TRIGGER videos_lineage_upd BEFORE UPDATE OF lineage_class ON videos
WHEN NOT EXISTS (SELECT 1 FROM db_meta WHERE key = 'dataset'
                 AND value = CASE NEW.lineage_class WHEN 'synthetic' THEN 'synthetic' ELSE 'live' END)
BEGIN SELECT RAISE(ABORT, 'lineage_class does not match db_meta.dataset'); END;

CREATE TRIGGER stats_lineage_ins BEFORE INSERT ON public_statistics_current
WHEN NOT EXISTS (SELECT 1 FROM db_meta WHERE key = 'dataset'
                 AND value = CASE NEW.lineage_class WHEN 'synthetic' THEN 'synthetic' ELSE 'live' END)
BEGIN SELECT RAISE(ABORT, 'lineage_class does not match db_meta.dataset'); END;

CREATE TRIGGER stats_lineage_upd BEFORE UPDATE OF lineage_class ON public_statistics_current
WHEN NOT EXISTS (SELECT 1 FROM db_meta WHERE key = 'dataset'
                 AND value = CASE NEW.lineage_class WHEN 'synthetic' THEN 'synthetic' ELSE 'live' END)
BEGIN SELECT RAISE(ABORT, 'lineage_class does not match db_meta.dataset'); END;

-- Statistics may only exist for an available video.
CREATE TRIGGER stats_require_available_video BEFORE INSERT ON public_statistics_current
WHEN (SELECT access_state FROM videos WHERE video_id = NEW.video_id) <> 'available'
BEGIN SELECT RAISE(ABORT, 'statistics require an available video'); END;
