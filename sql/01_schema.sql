-- Woo-lakproject: operationele status-tabellen (PostgreSQL).
-- Draai dit eenmalig op de PostgreSQL-connectie die je in Dataiku gebruikt.
-- Deze tabellen zijn de "source of truth" voor cases en lak-vlakken; de recipes
-- vullen ze en de webapp werkt ze per rij bij.

CREATE TABLE IF NOT EXISTS cases (
    case_id      TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    folder_path  TEXT NOT NULL UNIQUE,          -- pad binnen de intake-folder
    intake_ts    TIMESTAMP NOT NULL DEFAULT now(),
    status       TEXT NOT NULL DEFAULT 'NEW',    -- NEW > PROCESSING > READY_FOR_REVIEW > IN_REVIEW > APPROVED > PUBLISHED / ERROR
    page_count   INTEGER,
    used_ocr     BOOLEAN DEFAULT FALSE,          -- TRUE = via OCR verwerkt -> reviewer extra opletten
    assigned_to  TEXT,
    updated_ts   TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS redactions (
    redaction_id TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    page_no      INTEGER NOT NULL,               -- 0-based
    -- Genormaliseerde coordinaten (0..1), oorsprong linksboven. Onafhankelijk
    -- van schaal/DPI, zodat browser-overlay en het echte lakken exact matchen.
    nx0 DOUBLE PRECISION NOT NULL,
    ny0 DOUBLE PRECISION NOT NULL,
    nx1 DOUBLE PRECISION NOT NULL,
    ny1 DOUBLE PRECISION NOT NULL,
    entity_type  TEXT,                            -- NL_BSN, IBAN_CODE, PERSON, ...
    text_snippet TEXT,                            -- alleen voor de reviewer; NIET meepubliceren
    confidence   DOUBLE PRECISION,
    source       TEXT NOT NULL DEFAULT 'model',   -- model | human
    decision     TEXT NOT NULL DEFAULT 'accepted',-- accepted | rejected | pending
    reviewer     TEXT,
    decision_ts  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_redactions_case ON redactions(case_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id      BIGSERIAL PRIMARY KEY,
    ts      TIMESTAMP NOT NULL DEFAULT now(),
    case_id TEXT,
    actor   TEXT,
    action  TEXT,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_log(case_id);
