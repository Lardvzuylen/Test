# Recipe 2 - VERWERKEN (extractie + PII-detectie)
# Plak in een Python-recipe met als input de managed folder "00_intake".
# Voor elke case met status NEW: tekst extraheren (auto digitaal/OCR),
# PII detecteren en de lak-kandidaten wegschrijven. Modelvoorstellen staan
# standaard AAN (decision='accepted'); de reviewer hoeft alleen te controleren.
import dataiku
from woo import db, pdf_utils, pii

INTAKE_FOLDER = "00_intake"

folder = dataiku.Folder(INTAKE_FOLDER)
cases = db.get_cases_by_status("NEW")
print("Te verwerken cases:", len(cases))

for case in cases:
    case_id = case["case_id"]
    path = case["folder_path"]
    db.set_case_status(case_id, "PROCESSING")
    try:
        with folder.get_download_stream(path) as stream:
            pdf_bytes = stream.read()

        pages, used_ocr = pdf_utils.extract_pages(pdf_bytes)
        db.delete_model_redactions(case_id)

        total = 0
        for page in pages:
            boxes = pii.detect_on_page(page["words"])
            rows = [dict(b, page_no=page["page_no"], source="model", decision="accepted")
                    for b in boxes]
            db.insert_redactions(case_id, rows)
            total += len(rows)

        db.set_case_status(case_id, "READY_FOR_REVIEW",
                           used_ocr=used_ocr, page_count=len(pages))
        db.log_audit(case_id, "model", "DETECT",
                     "%d kandidaten, ocr=%s" % (total, used_ocr))
        print(case_id, "->", total, "kandidaten (ocr=%s)" % used_ocr)
    except Exception as exc:  # noqa: BLE001
        db.set_case_status(case_id, "ERROR")
        db.log_audit(case_id, "system", "ERROR", str(exc))
        print("FOUT bij", case_id, ":", exc)
        raise
