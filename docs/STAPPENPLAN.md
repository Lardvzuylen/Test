# Stappenplan: het Woo-lakproject bouwen in Dataiku

Dit is het concrete "waar-klik-ik" plan. Menu-namen kunnen per Dataiku-versie
licht verschillen; de volgorde en logica blijven gelijk. Reken op ~1-2 uur voor
de eerste keer.

> Voor je begint heb je nodig: toegang tot een Dataiku DSS-instance, een
> PostgreSQL-database (host/poort/db/gebruiker/wachtwoord), en admin-rechten in
> Dataiku om een code environment en connectie aan te maken (of iemand die dat
> voor je doet).

---

## Fase 0 — Project aanmaken

1. Ga naar de Dataiku homepage → **+ NEW PROJECT** → **Blank project**.
2. Naam: bijv. `Woo Lakken`. Open het project.

---

## Fase 1 — Code environment (de Python-omgeving)

Recipes en de webapp draaien straks in deze omgeving.

1. Klik rechtsboven op het **tandwiel/Administration**-icoon → **Code Envs**.
2. **+ NEW PYTHON ENV** → kies Python **3.10 of 3.11** → naam bijv. `woo-env` → maak aan.
3. Open de env → tab **Packages to install** → plak de inhoud van
   `code-env-requirements.txt`.
4. Voeg op een eigen regel ook het **spaCy NL-model als wheel** toe (dit is de
   betrouwbaarste manier in Dataiku; `spacy download` werkt hier niet vanzelf):
   ```
   https://github.com/explosion/spacy-models/releases/download/nl_core_news_lg-3.7.0/nl_core_news_lg-3.7.0-py3-none-any.whl
   ```
   (pas het versienummer aan op je geïnstalleerde spaCy.)
5. Klik **SAVE AND UPDATE**. Wacht tot de build klaar is.
6. **OCR (optioneel, voor gescande PDF's):** Tesseract + de taalpack `nld` moeten
   als systeempakket op de DSS-node staan (`apt-get install tesseract-ocr tesseract-ocr-nld`).
   Zonder OCR werken digitale PDF's prima; gescande niet.

---

## Fase 2 — Database: geen setup nodig (SQLite)

Je hebt **geen database-server, connectie of admin-rechten** nodig. Het project
gebruikt standaard een lokaal SQLite-bestand (`woo.db`) dat in de managed folder
**`woo_state`** komt te staan (die maak je in Fase 6).

- De tabellen (`cases`, `redactions`, `audit_log`) worden **automatisch** aangemaakt
  bij het eerste gebruik door `woo/db.py`. Je hoeft `sql/01_schema.sql` dus niet
  handmatig te draaien — dat bestand staat er alleen ter referentie.
- Wil je later toch een eigen server (bijv. PostgreSQL)? Zet dan de project-variabele
  `woo_db_url` (via **"..." → Variables**) op je connection-string; `db.py` gebruikt
  die dan in plaats van SQLite.

> SQLite is perfect voor één reviewer die aan het leren is. Voor veel gelijktijdige
> gebruikers stap je later over op een echte database-server.

---

## Fase 3 — Managed folders

1. Ga naar de **Flow**.
2. **+ DATASET** (of rechtsklik op het canvas) → kies **Folder / Managed folder**.
   Kies een **lokale-filesystem-connectie** → naam **`00_intake`**.
3. Herhaal voor **`90_published`** (de gelakte PDF's).
4. Herhaal voor **`woo_state`** — hierin komt het SQLite-bestand `woo.db`.
   (Gebruik ook hier de lokale filesystem; anders kan `db.py` het pad niet vinden.)

---

## Fase 4 — Project-library plaatsen

1. Bovenin **</> Code** → **Libraries**.
2. Open de map **`python/`** en maak daarin een map **`woo`**.
3. Maak in `python/woo/` de bestanden aan en plak de inhoud uit dit project:
   `__init__.py`, `db.py`, `pdf_utils.py`, `pii.py`, `redact.py`.
4. Test snel in een **Python notebook** (kies code env `woo-env`):
   ```python
   from woo import db
   print(db.get_cases())   # maakt de tabellen aan en geeft [] -> alles werkt
   ```
   Geen foutmelding = de SQLite-database in `woo_state` is aangemaakt.

---

## Fase 5 — De recipes bouwen

> Stel bij elke recipe rechtsonder/Advanced de **code env** in op `woo-env`.

### Recipe 1 — Intake
1. Klik in de Flow op folder **`00_intake`** → rechterpaneel **Actions** →
   onder *Code recipes* → **Python**.
2. **Inputs:** `00_intake`. **Outputs:** maak een nieuw managed dataset
   **`intake_status`** (op de filesystem-connectie). Create recipe.
3. Plak de inhoud van `recipes/recipe_01_intake.py`. **Run**.

### Recipe 2 — Verwerken (extractie + PII-detectie)
1. Selecteer weer **`00_intake`** → **Python recipe**.
2. **Inputs:** `00_intake`. **Outputs:** nieuw managed dataset **`process_status`**.
3. Plak `recipes/recipe_02_process.py`. **Run** (na een test-PDF, zie Fase 7).

### Recipe 4 — Publiceren (batch, optioneel naast de webapp)
1. Selecteer **`00_intake`** → **Python recipe**.
2. **Inputs:** `00_intake`. **Outputs:** folder **`90_published`**.
3. Plak `recipes/recipe_04_publish.py`.

---

## Fase 6 — De webapp bouwen

1. Bovenin **</> Code** → **Webapps** → **+ NEW WEBAPP** → **Code webapp** →
   **Standard (HTML / CSS / JS + Python backend)**. Naam bijv. `Woo Review`.
2. Vul de tabs:
   - **HTML** ← `webapp/body.html`
   - **CSS** ← `webapp/style.css`
   - **JavaScript** ← `webapp/app.js`
   - **Python** ← `webapp/backend.py`
3. Tab **Settings**: zet **Backend enabled** aan en kies **code env** `woo-env`.
4. Klik **SAVE** en **START BACKEND** → open de **View**.

> Blokkeert je netwerk de PDF.js-CDN? Dan laadt de viewer niet. Host `pdf.min.js`
> en `pdf.worker.min.js` dan in een managed folder en pas de URL's in
> `body.html` / `app.js` aan.

---

## Fase 7 — End-to-end testen

1. Open folder **`00_intake`** → **Upload your files** → upload een test-PDF
   (begin met een digitale PDF mét tekstlaag).
2. **Run recipe 1** → controleer in een Python-notebook: `from woo import db;
   print(db.get_cases())` → status `NEW`.
3. **Run recipe 2** → status wordt `READY_FOR_REVIEW`; `db.get_redactions(case_id)`
   toont de lak-kandidaten.
4. Open de **webapp** → kies de case → controleer de vlakken (klik = aan/uit,
   sleep = zelf toevoegen) → **Goedkeuren & publiceren**.
5. Open folder **`90_published`** → download het PDF → **probeer de gelakte tekst
   te selecteren/kopiëren**. Er mag niets onder het zwart vandaan komen. ✅

---

## Fase 8 — Automatiseren (optioneel)

1. Bovenin **Scenarios** → **+ NEW SCENARIO** → naam `Auto-intake`.
2. **Trigger:** "Trigger on dataset/folder change" op `00_intake` (of op een tijd).
3. **Steps:** "Build / Run" → recipe 1, daarna recipe 2 (of build dataset
   `process_status`, wat beide recipes triggert).
4. Activeer het scenario. Nieuwe PDF's komen nu vanzelf op `READY_FOR_REVIEW`.

---

## Snelle probleemoplossing

| Symptoom | Oorzaak / oplossing |
|---|---|
| `Kon geen database bepalen` | Managed folder `woo_state` ontbreekt of staat niet op de lokale filesystem (Fase 3). |
| `ModuleNotFoundError: woo` | Library staat niet in `python/woo/` (Fase 4). |
| `No module named presidio/fitz` | Recipe/webapp gebruikt niet code env `woo-env`. |
| Webapp toont lege/zwarte viewer | PDF.js-CDN geblokkeerd → zelf hosten (Fase 6). |
| Geen kandidaten op een gescande PDF | OCR niet geïnstalleerd (Tesseract + `nld`, Fase 1.6). |
| `database is locked` | Twee processen schrijven tegelijk in SQLite; probeer opnieuw of stap over op een DB-server. |
| Vlakken staan verschoven | Niet aan de orde bij genormaliseerde coördinaten; check dat je `app.js`/`redact.py` niet hebt aangepast. |
