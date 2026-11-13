-- FROZEN v1.0 SQLite schema (approved design Page, section 5 "Database").
-- Owner: Stream 2 (backend). The pipeline NEVER writes to this database.
-- Columns marked "REC" are OUR RECOMMENDATION (not on the Page), kept minimal.
-- Requires SQLite with FTS5 (Python 3.13's sqlite3 3.46 has it).

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS assets (
    id               TEXT PRIMARY KEY,                     -- 'a_<hex>'
    filename         TEXT NOT NULL,
    kind             TEXT NOT NULL CHECK (kind IN ('video', 'document')),
    bytes            INTEGER NOT NULL CHECK (bytes >= 0),  -- measured original size
    sha256           TEXT NOT NULL,                        -- file SHA-256, computed at upload
    source_system    TEXT NOT NULL CHECK (source_system IN ('sharepoint', 'onedrive', 'ericsson_play')),
    source_simulated INTEGER NOT NULL DEFAULT 1 CHECK (source_simulated IN (0, 1)),
    owner            TEXT NOT NULL,
    metadata_json    TEXT NOT NULL DEFAULT '{}',           -- AssetMetadata JSON from the manifest
    status           TEXT NOT NULL DEFAULT 'uploaded'
                     CHECK (status IN ('uploaded', 'queued', 'processing', 'ready', 'failed')),
    original_path    TEXT NOT NULL,                        -- REC: relative to data/, e.g. originals/a_01/deck.pdf
    manifest_bytes   INTEGER,                              -- REC: measured size of manifest.json at ingest
    pipeline_json    TEXT,                                 -- REC: PipelineInfo JSON from the manifest
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))  -- REC
);
CREATE INDEX IF NOT EXISTS idx_assets_sha256 ON assets (sha256);
CREATE INDEX IF NOT EXISTS idx_assets_owner ON assets (owner);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    asset_id    TEXT NOT NULL REFERENCES assets (id),
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    progress    REAL NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 1),
    stage       TEXT,                                      -- REC
    error       TEXT,
    started_at  TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_asset ON jobs (asset_id);

-- segments / frames / slides use the manifest's per-asset local ids, so the key is (asset_id, id).
CREATE TABLE IF NOT EXISTS segments (
    asset_id TEXT NOT NULL REFERENCES assets (id),
    id       TEXT NOT NULL,                                -- 's<n>'
    "start"  REAL NOT NULL,
    "end"    REAL NOT NULL,
    text     TEXT NOT NULL,
    frame_id TEXT,                                         -- local frame id in the same asset
    speaker  TEXT,                                         -- always NULL in the MVP
    PRIMARY KEY (asset_id, id)
);

CREATE TABLE IF NOT EXISTS frames (
    asset_id         TEXT NOT NULL REFERENCES assets (id),
    id               TEXT NOT NULL,                        -- 'f<n>'
    t_start          REAL NOT NULL,
    t_end            REAL NOT NULL,
    path             TEXT NOT NULL,                        -- relative to data/derived/<asset_id>/
    bytes            INTEGER NOT NULL,
    phash            TEXT NOT NULL,
    matched_slide_id TEXT,                                 -- STRETCH: global ref '<asset_id>:p<n>'
    PRIMARY KEY (asset_id, id)
);

CREATE TABLE IF NOT EXISTS slides (
    asset_id    TEXT NOT NULL REFERENCES assets (id),
    id          TEXT NOT NULL,                             -- 'p<page>'
    page        INTEGER NOT NULL,
    text        TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    phash       TEXT NOT NULL,
    path        TEXT NOT NULL,
    bytes       INTEGER NOT NULL,
    PRIMARY KEY (asset_id, id)
);
CREATE INDEX IF NOT EXISTS idx_slides_text_sha ON slides (text_sha256);

-- Every derived file kept on disk (from manifest.derived_files). Storage report sums these + assets.manifest_bytes.
CREATE TABLE IF NOT EXISTS derived_files (
    asset_id TEXT NOT NULL REFERENCES assets (id),
    path     TEXT NOT NULL,
    kind     TEXT NOT NULL CHECK (kind IN ('transcript', 'frame', 'page_image', 'page_text', 'audio', 'other')),
    bytes    INTEGER NOT NULL CHECK (bytes >= 0),
    PRIMARY KEY (asset_id, path)
);

-- Duplicate engine output. a_id / b_id are global refs:
--   level='file'  -> '<asset_id>'            (type is always 'exact')
--   level='slide' -> '<asset_id>:p<page>'    (type 'exact' | 'shared' | 'similar')
-- REC: store each pair once with a_id < b_id; never match an item with its own asset.
CREATE TABLE IF NOT EXISTS matches (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,            -- REC
    a_id     TEXT NOT NULL,
    b_id     TEXT NOT NULL,
    level    TEXT NOT NULL CHECK (level IN ('file', 'slide')),
    type     TEXT NOT NULL CHECK (type IN ('exact', 'shared', 'similar')),
    method   TEXT NOT NULL,                                -- 'sha256' | 'text_sha256+phash' | 'phash' | 'text_ratio'
    score    REAL NOT NULL,                                -- 1.0 for exact
    evidence TEXT NOT NULL DEFAULT '{}',                   -- DuplicateEvidence JSON
    CHECK (a_id < b_id),
    UNIQUE (a_id, b_id, level)
);

-- Full-text search over segments.text and slides.text (one row per segment or slide).
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5 (
    text,
    asset_id  UNINDEXED,
    item_type UNINDEXED,                                   -- 'segment' | 'slide' | 'asset' (REC v1.1: title + file name + metadata)
    item_id   UNINDEXED,                                   -- local id 's12' / 'p4' / 'meta'
    tokenize = 'unicode61 remove_diacritics 2'             -- REC: handles Swedish/English mix
);

-- REC v1.1: labels a library file as GENERATED test/sample data (e.g. made by pipeline/scripts/make_samples.py),
-- so it is never presented as customer data. The default storage report leaves these files out.
-- Separate table (not a new assets column) so existing databases pick it up with CREATE IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS asset_labels (
    asset_id  TEXT PRIMARY KEY REFERENCES assets (id),
    test_data INTEGER NOT NULL DEFAULT 0 CHECK (test_data IN (0, 1)),
    note      TEXT
);
