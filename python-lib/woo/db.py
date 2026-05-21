"""Database-helpers voor de operationele status-tabellen.

Standaard wordt een lokaal SQLite-bestand 'woo.db' gebruikt in de managed folder
'woo_state' -- geen database-server, connectie of admin-rechten nodig. De tabellen
worden bij het eerste gebruik automatisch aangemaakt.

De DB-URL wordt bepaald in deze volgorde:
  1. Dataiku project-variabele 'woo_db_url'   (optioneel, voor een eigen server)
  2. omgevingsvariabele WOO_DB_URL            (idem)
  3. SQLite-bestand in managed folder 'woo_state'  (standaard)

Werkt zowel met SQLite als met PostgreSQL (timestamps gaan als parameter mee, dus
geen DB-specifieke now()-aanroepen).
"""
import os
import uuid
import datetime as _dt

from sqlalchemy import create_engine, text

STATE_FOLDER = "woo_state"   # managed folder waarin het SQLite-bestand komt
_engine = None


def _now():
    return _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _resolve_url():
    # 1) expliciete override via project-variabele of omgevingsvariabele
    try:
        import dataiku
        variables = dataiku.get_custom_variables() or {}
        if variables.get("woo_db_url"):
            return variables["woo_db_url"]
    except Exception:
        pass
    if os.environ.get("WOO_DB_URL"):
        return os.environ["WOO_DB_URL"]

    # 2) standaard: SQLite-bestand in de managed folder 'woo_state'
    try:
        import dataiku
        base = dataiku.Folder(STATE_FOLDER).get_path()
        return "sqlite:///" + os.path.join(base, "woo.db")
    except Exception as exc:
        raise RuntimeError(
            "Kon geen database bepalen. Maak een managed folder '%s' aan op een "
            "lokale-filesystem-connectie, of zet project-variabele 'woo_db_url'. "
            "Detail: %s" % (STATE_FOLDER, exc)
        )


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS cases (
        case_id     TEXT PRIMARY KEY,
        filename    TEXT NOT NULL,
        folder_path TEXT NOT NULL UNIQUE,
        intake_ts   TEXT NOT NULL,
        status      TEXT NOT NULL DEFAULT 'NEW',
        page_count  INTEGER,
        used_ocr    INTEGER DEFAULT 0,
        assigned_to TEXT,
        updated_ts  TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS redactions (
        redaction_id TEXT PRIMARY KEY,
        case_id      TEXT NOT NULL,
        page_no      INTEGER NOT NULL,
        nx0 REAL NOT NULL, ny0 REAL NOT NULL, nx1 REAL NOT NULL, ny1 REAL NOT NULL,
        entity_type  TEXT,
        text_snippet TEXT,
        confidence   REAL,
        source       TEXT NOT NULL DEFAULT 'model',
        decision     TEXT NOT NULL DEFAULT 'accepted',
        reviewer     TEXT,
        decision_ts  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS audit_log (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        ts      TEXT NOT NULL,
        case_id TEXT,
        actor   TEXT,
        action  TEXT,
        details TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_redactions_case ON redactions(case_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_log(case_id)",
]


def _init_schema(engine):
    with engine.begin() as conn:
        for stmt in _SCHEMA:
            conn.execute(text(stmt))


def get_engine():
    global _engine
    if _engine is None:
        url = _resolve_url()
        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            # check_same_thread=False: de webapp-backend kan meerdere threads gebruiken.
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(url, **kwargs)
        _init_schema(_engine)
    return _engine


def _rows(result):
    cols = result.keys()
    return [dict(zip(cols, row)) for row in result.fetchall()]


# ---------------------------------------------------------------- cases

def get_known_paths():
    with get_engine().connect() as conn:
        res = conn.execute(text("SELECT folder_path FROM cases"))
        return {r[0] for r in res.fetchall()}


def upsert_case(case_id, filename, folder_path, page_count=None):
    now = _now()
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO cases (case_id, filename, folder_path, page_count, intake_ts, updated_ts)
            VALUES (:cid, :fn, :fp, :pc, :ts, :ts)
            ON CONFLICT (folder_path) DO NOTHING
        """), {"cid": case_id, "fn": filename, "fp": folder_path, "pc": page_count, "ts": now})


def set_case_status(case_id, status, used_ocr=None, page_count=None):
    sets = ["status = :st", "updated_ts = :uts"]
    params = {"cid": case_id, "st": status, "uts": _now()}
    if used_ocr is not None:
        sets.append("used_ocr = :ocr")
        params["ocr"] = 1 if used_ocr else 0
    if page_count is not None:
        sets.append("page_count = :pc")
        params["pc"] = int(page_count)
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE cases SET " + ", ".join(sets) + " WHERE case_id = :cid"), params)


def get_case(case_id):
    with get_engine().connect() as conn:
        res = conn.execute(text("SELECT * FROM cases WHERE case_id = :cid"), {"cid": case_id})
        rows = _rows(res)
        return rows[0] if rows else None


def get_cases(status=None):
    sql = "SELECT * FROM cases"
    params = {}
    if status:
        sql += " WHERE status = :st"
        params["st"] = status
    sql += " ORDER BY intake_ts DESC"
    with get_engine().connect() as conn:
        return _rows(conn.execute(text(sql), params))


def get_cases_by_status(status):
    return get_cases(status)


# ------------------------------------------------------------ redactions

def delete_model_redactions(case_id):
    """Verwijder eerdere modelvoorstellen (handmatige blijven staan), zodat
    een case opnieuw verwerkt kan worden zonder dubbele rijen."""
    with get_engine().begin() as conn:
        conn.execute(text(
            "DELETE FROM redactions WHERE case_id = :cid AND source = 'model'"
        ), {"cid": case_id})


def insert_redactions(case_id, rows):
    if not rows:
        return
    with get_engine().begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO redactions
                  (redaction_id, case_id, page_no, nx0, ny0, nx1, ny1,
                   entity_type, text_snippet, confidence, source, decision)
                VALUES
                  (:rid, :cid, :pg, :nx0, :ny0, :nx1, :ny1,
                   :et, :snip, :conf, :src, :dec)
            """), {
                "rid": r.get("redaction_id") or str(uuid.uuid4()),
                "cid": case_id,
                "pg": int(r["page_no"]),
                "nx0": float(r["nx0"]), "ny0": float(r["ny0"]),
                "nx1": float(r["nx1"]), "ny1": float(r["ny1"]),
                "et": r.get("entity_type"),
                "snip": r.get("text_snippet"),
                "conf": r.get("confidence"),
                "src": r.get("source", "model"),
                "dec": r.get("decision", "accepted"),
            })


def get_redactions(case_id):
    with get_engine().connect() as conn:
        res = conn.execute(text(
            "SELECT * FROM redactions WHERE case_id = :cid ORDER BY page_no"
        ), {"cid": case_id})
        return _rows(res)


def get_accepted_redactions(case_id):
    with get_engine().connect() as conn:
        res = conn.execute(text(
            "SELECT * FROM redactions WHERE case_id = :cid AND decision = 'accepted'"
        ), {"cid": case_id})
        return _rows(res)


def update_redaction_decision(redaction_id, decision, reviewer):
    with get_engine().begin() as conn:
        conn.execute(text("""
            UPDATE redactions
            SET decision = :dec, reviewer = :rev, decision_ts = :dts
            WHERE redaction_id = :rid
        """), {"dec": decision, "rev": reviewer, "dts": _now(), "rid": redaction_id})


def add_human_redaction(case_id, box, reviewer):
    rid = str(uuid.uuid4())
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO redactions
              (redaction_id, case_id, page_no, nx0, ny0, nx1, ny1,
               entity_type, text_snippet, confidence, source, decision, reviewer, decision_ts)
            VALUES
              (:rid, :cid, :pg, :nx0, :ny0, :nx1, :ny1,
               'HANDMATIG', NULL, 1.0, 'human', 'accepted', :rev, :dts)
        """), {
            "rid": rid, "cid": case_id, "pg": int(box["page_no"]),
            "nx0": float(box["nx0"]), "ny0": float(box["ny0"]),
            "nx1": float(box["nx1"]), "ny1": float(box["ny1"]),
            "rev": reviewer, "dts": _now(),
        })
    return rid


# -------------------------------------------------------------- audit

def log_audit(case_id, actor, action, details=""):
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_log (case_id, actor, action, details, ts)
            VALUES (:cid, :actor, :action, :details, :ts)
        """), {"cid": case_id, "actor": actor, "action": action,
               "details": details, "ts": _now()})
