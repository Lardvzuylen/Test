"""PII-detectie met Microsoft Presidio + Nederlandse custom-recognizers.

detect_on_page(words) draait Presidio op de paginatekst, mapt de gevonden
char-spans terug naar de woord-bounding-boxes en levert per regel een lak-vlak op
(in genormaliseerde coordinaten, oorsprong linksboven).
"""
from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider

# Welke entiteiten we standaard laten lakken. DATE_TIME bewust weggelaten
# (te veel onschuldige datums); voeg toe als jouw documenten dat vereisen.
DEFAULT_ENTITIES = [
    "PERSON", "LOCATION", "EMAIL_ADDRESS", "IBAN_CODE", "CREDIT_CARD",
    "PHONE_NUMBER", "NL_BSN", "NL_PHONE", "NL_POSTCODE",
]


class BsnRecognizer(PatternRecognizer):
    """Burgerservicenummer: 9 cijfers met 11-proef-validatie."""
    def __init__(self):
        super().__init__(
            supported_entity="NL_BSN",
            patterns=[Pattern("bsn", r"\b[0-9]{9}\b", 0.4)],
            context=["bsn", "burgerservicenummer", "sofinummer", "sofi"],
            supported_language="nl",
        )

    def validate_result(self, pattern_text):
        digits = [int(c) for c in pattern_text if c.isdigit()]
        if len(digits) != 9 or all(d == 0 for d in digits):
            return False
        total = sum((9 - i) * d for i, d in enumerate(digits[:8])) - digits[8]
        return total % 11 == 0


class DutchPostcodeRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(
            supported_entity="NL_POSTCODE",
            patterns=[Pattern("nl_postcode", r"\b[1-9][0-9]{3}\s?[A-Za-z]{2}\b", 0.3)],
            context=["postcode", "adres", "woonplaats"],
            supported_language="nl",
        )


class DutchPhoneRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(
            supported_entity="NL_PHONE",
            patterns=[Pattern("nl_phone", r"\b(?:\+31|0031|0)\s?[1-9](?:[\s-]?[0-9]){8}\b", 0.4)],
            context=["tel", "telefoon", "mobiel", "gsm", "nummer"],
            supported_language="nl",
        )


@lru_cache(maxsize=1)
def get_analyzer():
    nlp_engine = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "nl", "model_name": "nl_core_news_lg"}],
    }).create_engine()

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(languages=["nl"], nlp_engine=nlp_engine)
    for rec in (BsnRecognizer(), DutchPostcodeRecognizer(), DutchPhoneRecognizer()):
        registry.add_recognizer(rec)

    return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry, supported_languages=["nl"])


def _build_text(words):
    """Plak woorden tot paginatekst en onthoud per woord de char-span."""
    parts, spans, pos = [], [], 0
    for w in words:
        t = w["text"]
        spans.append((pos, pos + len(t)))
        parts.append(t)
        pos += len(t) + 1  # +1 voor de spatie waarmee we joinen
    return " ".join(parts), spans


def detect_on_page(words, score_threshold=0.35, entities=None):
    if not words:
        return []
    entities = entities or DEFAULT_ENTITIES
    text, spans = _build_text(words)

    results = get_analyzer().analyze(
        text=text, language="nl", entities=entities, score_threshold=score_threshold,
    )

    boxes = []
    for res in results:
        hit_idx = [i for i, (s, e) in enumerate(spans) if s < res.end and e > res.start]
        if not hit_idx:
            continue
        # Per tekstregel een eigen vlak (entiteit kan over regels heen lopen).
        by_line = {}
        for i in hit_idx:
            by_line.setdefault(words[i]["line_id"], []).append(words[i])
        for line_words in by_line.values():
            boxes.append({
                "nx0": min(w["x0"] for w in line_words),
                "ny0": min(w["y0"] for w in line_words),
                "nx1": max(w["x1"] for w in line_words),
                "ny1": max(w["y1"] for w in line_words),
                "entity_type": res.entity_type,
                "text_snippet": " ".join(w["text"] for w in line_words),
                "confidence": round(float(res.score), 3),
            })
    return boxes
