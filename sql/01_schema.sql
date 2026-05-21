-- Woo-lakproject: operationele status-tabellen.
--
-- LET OP: je hoeft dit normaal NIET handmatig te draaien. De library
-- python-lib/woo/db.py maakt deze tabellen automatisch aan bij het eerste
-- gebruik (in het SQLite-bestand woo.db in de managed folder 'woo_state').
--
-- Dit bestand staat hier alleen ter referentie, of voor als je later een eigen
-- database-server (bijv. PostgreSQL) wilt gebruiken. De DDL hieronder is in
-- SQLite-vorm; voor PostgreSQL kun je INTEGER PRIMARY KEY AUTOINCREMENT
-- vervangen door BIGSERIAL en REAL door DOUBLE PRECISION.

CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    folder_path TEXT NOT NULL UNIQUE,       -- pad binnen de intake-folder
    intake_ts   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'NEW',-- NEW > PROCESSING > READY_FOR_REVIEW > IN_REVIEW > APPROVED > PUBLISHED / ERROR
    page_count  INTEGER,
    used_ocr    INTEGER DEFAULT 0,          -- 1 = via OCR verwerkt -> reviewer extra opletten
    assigned_to TEXT,
    updated_ts  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS redactions (
    redaction_id TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL,
    page_no      INTEGER NOT NULL,           -- 0-based
    -- Genormaliseerde coordinaten (0..1), oorsprong linksboven.
    nx0 REAL NOT NULL, ny0 REAL NOT NULL, nx1 REAL NOT NULL, ny1 REAL NOT NULL,
    entity_type  TEXT,                        -- NL_BSN, IBAN_CODE, PERSON, ...
    text_snippet TEXT,                        -- alleen voor de reviewer; NIET meepubliceren
    confidence   REAL,
    source       TEXT NOT NULL DEFAULT 'model',   -- model | human
    decision     TEXT NOT NULL DEFAULT 'accepted',-- accepted | rejected | pending
    reviewer     TEXT,
    decision_ts  TEXT
);
CREATE INDEX IF NOT EXISTS idx_redactions_case ON redactions(case_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    case_id TEXT,
    actor   TEXT,
    action  TEXT,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_log(case_id);
