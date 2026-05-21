# Recipe 1 - INTAKE
# Plak in een Python-recipe met als input de managed folder "00_intake".
# Registreert nieuwe PDF's als case (status NEW). Idempotent: al bekende
# bestanden worden overgeslagen.
import uuid

import dataiku
from woo import db

INTAKE_FOLDER = "00_intake"

folder = dataiku.Folder(INTAKE_FOLDER)
known = db.get_known_paths()

new_count = 0
for path in folder.list_paths_in_partition():
    if not path.lower().endswith(".pdf") or path in known:
        continue
    case_id = str(uuid.uuid4())
    filename = path.lstrip("/").split("/")[-1]
    db.upsert_case(case_id, filename, path)
    db.log_audit(case_id, "system", "INTAKE", "Nieuw bestand: %s" % filename)
    print("Geregistreerd:", filename, "->", case_id)
    new_count += 1

print("Klaar. %d nieuwe case(s)." % new_count)
