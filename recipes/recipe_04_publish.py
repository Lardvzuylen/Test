# Recipe 4 - PUBLICEREN (batch)
# Plak in een Python-recipe met inputs: managed folders "00_intake" en
# "90_published" (output). Lakt alle goedgekeurde cases echt en schrijft het
# resultaat naar de publicatie-folder.
#
# Let op: de webapp kan ook direct publiceren bij goedkeuren (zie webapp/backend.py).
# Deze recipe is handig voor batch-verwerking of via een scenario.
import dataiku
from woo import db, redact

INTAKE_FOLDER = "00_intake"
PUBLISHED_FOLDER = "90_published"

src = dataiku.Folder(INTAKE_FOLDER)
dst = dataiku.Folder(PUBLISHED_FOLDER)

cases = db.get_cases_by_status("APPROVED")
print("Te publiceren cases:", len(cases))

for case in cases:
    case_id = case["case_id"]
    with src.get_download_stream(case["folder_path"]) as stream:
        pdf_bytes = stream.read()

    accepted = db.get_accepted_redactions(case_id)
    out_bytes = redact.apply_redactions(pdf_bytes, accepted)
    out_path = "/%s_%s" % (case_id, case["filename"])
    dst.upload_data(out_path, out_bytes)

    db.set_case_status(case_id, "PUBLISHED")
    db.log_audit(case_id, "system", "PUBLISH",
                 "%d vlakken gelakt -> %s" % (len(accepted), out_path))
    print("Gepubliceerd:", out_path, "(%d vlakken)" % len(accepted))
