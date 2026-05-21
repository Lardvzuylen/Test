# Webapp-backend (Dataiku Standard webapp -> tab "Python").
# In een Dataiku-webapp is het Flask-object `app` al beschikbaar; niet importeren.
import json

import dataiku
from flask import request, jsonify, Response

from woo import db, redact

INTAKE_FOLDER = "00_intake"
PUBLISHED_FOLDER = "90_published"


@app.route("/cases")
def list_cases():
    status = request.args.get("status") or None
    return jsonify(db.get_cases(status))


@app.route("/pdf/<case_id>")
def get_pdf(case_id):
    case = db.get_case(case_id)
    if not case:
        return ("case niet gevonden", 404)
    folder = dataiku.Folder(INTAKE_FOLDER)
    with folder.get_download_stream(case["folder_path"]) as stream:
        data = stream.read()
    return Response(data, mimetype="application/pdf")


@app.route("/redactions/<case_id>")
def get_redactions(case_id):
    return jsonify(db.get_redactions(case_id))


@app.route("/redactions/<case_id>", methods=["POST"])
def save_redactions(case_id):
    payload = request.get_json(force=True) or {}
    reviewer = payload.get("reviewer", "onbekend")

    for d in payload.get("decisions", []):
        db.update_redaction_decision(d["redaction_id"], d["decision"], reviewer)
    for box in payload.get("added", []):
        db.add_human_redaction(case_id, box, reviewer)

    db.set_case_status(case_id, "IN_REVIEW")
    db.log_audit(case_id, reviewer, "REVIEW_SAVE", json.dumps({
        "decisions": len(payload.get("decisions", [])),
        "added": len(payload.get("added", [])),
    }))
    return jsonify({"ok": True})


@app.route("/approve/<case_id>", methods=["POST"])
def approve_case(case_id):
    payload = request.get_json(silent=True) or {}
    reviewer = payload.get("reviewer", "onbekend")

    case = db.get_case(case_id)
    if not case:
        return ("case niet gevonden", 404)

    src = dataiku.Folder(INTAKE_FOLDER)
    dst = dataiku.Folder(PUBLISHED_FOLDER)
    with src.get_download_stream(case["folder_path"]) as stream:
        pdf_bytes = stream.read()

    accepted = db.get_accepted_redactions(case_id)
    out_bytes = redact.apply_redactions(pdf_bytes, accepted)
    out_path = "/%s_%s" % (case_id, case["filename"])
    dst.upload_data(out_path, out_bytes)

    db.set_case_status(case_id, "PUBLISHED")
    db.log_audit(case_id, reviewer, "APPROVE_PUBLISH",
                 "%d vlakken -> %s" % (len(accepted), out_path))
    return jsonify({"ok": True, "published": out_path, "redactions": len(accepted)})
