"""Database-helpers voor de operationele status-tabellen (PostgreSQL).

De DB-URL wordt gelezen uit (in volgorde):
  1. Dataiku project-variabele 'woo_db_url'
  2. omgevingsvariabele WOO_DB_URL
Formaat: postgresql://gebruiker:wachtwoord@host:5432/databasenaam
"""
import os
import json
import uuid
import datetime as _dt

from sqlalchemy import create_engine, text

_engine = None


def _resolve_url():
    try:
        import dataiku
        variables = dataiku.get_custom_variables() or {}
        if variables.get("woo_db_url"):
            return variables["woo_db_url"]
    except Exception:
        pass
    url = os.environ.get("WOO_DB_URL")
    if not url:
        raise RuntimeError(
            "Geen database-URL gevonden. Zet de Dataiku project-variabele "
            "'woo_db_url' of de omgevingsvariabele WOO_DB_URL, bijv. "
            "postgresql://user:pw@host:5432/dbnaam"
        )
    return url


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_resolve_url(), pool_pre_ping=True)
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
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO cases (case_id, filename, folder_path, page_count)
            VALUES (:cid, :fn, :fp, :pc)
            ON CONFLICT (folder_path) DO NOTHING
        """), {"cid": case_id, "fn": filename, "fp": folder_path, "pc": page_count})


def set_case_status(case_id, status, used_ocr=None, page_count=None):
    sets = ["status = :st", "updated_ts = now()"]
    params = {"cid": case_id, "st": status}
    if used_ocr is not None:
        sets.append("used_ocr = :ocr")
        params["ocr"] = bool(used_ocr)
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
            SET decision = :dec, reviewer = :rev, decision_ts = now()
            WHERE redaction_id = :rid
        """), {"dec": decision, "rev": reviewer, "rid": redaction_id})


def add_human_redaction(case_id, box, reviewer):
    rid = str(uuid.uuid4())
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO redactions
              (redaction_id, case_id, page_no, nx0, ny0, nx1, ny1,
               entity_type, text_snippet, confidence, source, decision, reviewer, decision_ts)
            VALUES
              (:rid, :cid, :pg, :nx0, :ny0, :nx1, :ny1,
               'HANDMATIG', NULL, 1.0, 'human', 'accepted', :rev, now())
        """), {
            "rid": rid, "cid": case_id, "pg": int(box["page_no"]),
            "nx0": float(box["nx0"]), "ny0": float(box["ny0"]),
            "nx1": float(box["nx1"]), "ny1": float(box["ny1"]),
            "rev": reviewer,
        })
    return rid


# -------------------------------------------------------------- audit

def log_audit(case_id, actor, action, details=""):
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_log (case_id, actor, action, details)
            VALUES (:cid, :actor, :action, :details)
        """), {"cid": case_id, "actor": actor, "action": action, "details": details})
