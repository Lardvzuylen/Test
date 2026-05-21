"""Echt lakken met PyMuPDF.

Belangrijk: add_redact_annot() + apply_redactions() VERWIJDERT de onderliggende
tekst en beeld-pixels. Een zwarte rechthoek tekenen is GEEN redactie -- de tekst
zou er dan nog onder zitten en kopieerbaar zijn.
"""
import fitz  # PyMuPDF


def apply_redactions(pdf_bytes, redactions):
    """redactions: lijst van dicts met page_no en genormaliseerde nx0,ny0,nx1,ny1."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        by_page = {}
        for r in redactions:
            by_page.setdefault(int(r["page_no"]), []).append(r)

        for page_no, items in by_page.items():
            if page_no < 0 or page_no >= len(doc):
                continue
            page = doc[page_no]
            w, h = page.rect.width, page.rect.height
            for r in items:
                rect = fitz.Rect(
                    float(r["nx0"]) * w, float(r["ny0"]) * h,
                    float(r["nx1"]) * w, float(r["ny1"]) * h,
                )
                page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()  # verwijdert tekst/beeld onder de vlakken

        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()
