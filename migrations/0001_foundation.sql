-- 0001 foundation: database identity and fail-closed policy capabilities.
-- Applied once, inside one transaction, by gta_lab.db.migrate. Never edit after release;
-- add a new numbered file instead (the runner rejects checksum changes).

-- Which dataset this file holds. Written once by open_database(); immutable afterwards,
-- so a fixture database can never be reopened as live (or the reverse).
CREATE TABLE db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    CHECK (key <> 'dataset' OR value IN ('synthetic', 'live'))
) STRICT;

CREATE TRIGGER db_meta_dataset_immutable_update
BEFORE UPDATE ON db_meta WHEN OLD.key = 'dataset'
BEGIN
    SELECT RAISE(ABORT, 'db_meta.dataset is immutable');
END;

CREATE TRIGGER db_meta_dataset_immutable_delete
BEFORE DELETE ON db_meta WHEN OLD.key = 'dataset'
BEGIN
    SELECT RAISE(ABORT, 'db_meta.dataset is immutable');
END;

-- Approval-only capabilities (docs/YOUTUBE_POLICY.md, gate 3). Off by default.
-- 'on' requires a recorded proof source and date; a config flag is never proof.
CREATE TABLE policy_capabilities (
    capability     TEXT PRIMARY KEY CHECK (capability IN (
                       'cohort_analytics', 'statistical_history',
                       'api_taxonomy_enrichment', 'predictive_model')),
    status         TEXT NOT NULL DEFAULT 'off' CHECK (status IN ('off', 'on')),
    proof_source   TEXT,
    proof_date     TEXT,
    updated_at_utc TEXT NOT NULL,
    CHECK (status = 'off' OR (proof_source IS NOT NULL AND proof_date IS NOT NULL))
) STRICT;

INSERT INTO policy_capabilities (capability, status, updated_at_utc) VALUES
    ('cohort_analytics',        'off', strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ('statistical_history',     'off', strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ('api_taxonomy_enrichment', 'off', strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ('predictive_model',        'off', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
