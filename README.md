# Woo-lakproject (Dataiku) — fictief leerproject

Versnelt het zwart lakken van documenten voor de Wet open overheid (Woo): een
model doet een eerste voorstel welke vlakken (BSN, IBAN, namen, e-mail, telefoon,
adres, …) gelakt moeten worden, een mens controleert en corrigeert in een webapp,
en pas daarna wordt er **écht** gelakt (tekst/pixels worden verwijderd, niet alleen
afgedekt).

## Architectuur

```
[00_intake folder]   Recipe 1: intake     -> cases (NEW)
   PDF's binnen   ->  Recipe 2: verwerken  -> tekst+OCR + PII-detectie -> redactions (voorgesteld)
                      Webapp: review        -> mens bevestigt/corrigeert lak-vlakken
                      Recipe 4 / webapp     -> echt lakken (PyMuPDF) -> [90_published folder]
```

## Wat waar hoort in Dataiku

| Bestand | Plek in Dataiku |
|---|---|
| `code-env-requirements.txt` | Code env > Packages to install (+ spaCy NL-model als wheel-URL) |
| `sql/01_schema.sql` | Referentie; tabellen worden automatisch aangemaakt door `db.py` |
| `python-lib/woo/*.py` | Project > Libraries > python (map `woo/`) |
| `recipes/recipe_01_intake.py` | Python-recipe, input = folder `00_intake` |
| `recipes/recipe_02_process.py` | Python-recipe, input = folder `00_intake` |
| `recipes/recipe_04_publish.py` | Python-recipe, inputs = folders `00_intake` + `90_published` |
| `webapp/backend.py` | Standard webapp, tab Python |
| `webapp/body.html` | Standard webapp, tab HTML |
| `webapp/app.js` | Standard webapp, tab JavaScript |
| `webapp/style.css` | Standard webapp, tab CSS |

> Volg het volledige klik-voor-klik plan in **`docs/STAPPENPLAN.md`**.

## Eenmalige setup (kort)

1. Maak een **code environment** met `code-env-requirements.txt` en het spaCy
   NL-model (als wheel-URL, zie `code-env-requirements.txt`). Voor OCR: Tesseract
   + de `nld` taalpack op de DSS-node.
2. Maak drie **managed folders** (lokale filesystem): `00_intake`, `90_published`,
   `woo_state`.
3. Kopieer `python-lib/woo/` naar de project-library.

De database is standaard **SQLite** (`woo.db` in folder `woo_state`). De tabellen
worden automatisch aangemaakt; je hoeft `sql/01_schema.sql` niet handmatig te draaien.
Wil je later een eigen DB-server? Zet dan project-variabele `woo_db_url` op je
connection-string.

## Uitvoervolgorde

1. Zet een test-PDF in folder `00_intake`.
2. Draai recipe 1 (intake) → de case verschijnt met status `NEW`.
3. Draai recipe 2 (verwerken) → status wordt `READY_FOR_REVIEW`, lak-kandidaten staan klaar.
4. Open de webapp → kies de case, controleer/corrigeer de vlakken, klik
   **Goedkeuren & publiceren**. Het gelakte PDF komt in `90_published`.
   (Of: zet cases op `APPROVED` en draai recipe 4 voor batch-publicatie.)
5. Optioneel: een **scenario** dat recipe 1 + 2 draait bij nieuwe bestanden in `00_intake`.

## Belangrijke ontwerpkeuzes

- **Echt lakken**: `apply_redactions()` verwijdert de onderliggende tekst/pixels.
  Controleer dit door tekst te selecteren in een gepubliceerd PDF — er mag niets
  onder het zwart vandaan komen.
- **Genormaliseerde coordinaten** (0..1, linksboven): browser-overlay en het
  daadwerkelijke lakken matchen exact, ongeacht zoom/DPI.
- **Mens beslist altijd**: modelvoorstellen staan vooraf aan, de reviewer zet
  false positives uit en voegt gemiste vlakken toe. Het model lakt nooit zelf
  definitief.
- **OCR-risico**: cases via OCR krijgen een waarschuwing in de UI; gemiste tekst
  is een datalek, dus daar extra controleren.
- **`text_snippet`** is alleen voor de reviewer en wordt niet meegepubliceerd.

## Aandachtspunten / mogelijke uitbreidingen

- Netwerkbeleid kan de PDF.js-CDN blokkeren; host `pdf.js` dan zelf.
- **SQLite** is prima voor één reviewer; bij gelijktijdig schrijven kan
  `database is locked` optreden. Voor meerdere gebruikers stap je over op een
  DB-server via project-variabele `woo_db_url` (de code is dialect-agnostisch).
- De `woo_state`-folder moet op een **lokale filesystem** staan, anders kan
  `db.py` het pad naar `woo.db` niet bepalen.
- Toegangsbeheer op de webapp (alleen geautoriseerde behandelaars) en bewaartermijnen
  zijn buiten scope van dit leerproject.
