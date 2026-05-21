"""PDF-tekstextractie met automatische digitaal/gescand-detectie.

- Digitale PDF (tekstlaag aanwezig): woorden + coordinaten direct uit PyMuPDF.
- Gescande PDF (alleen beeld): OCR via Tesseract (pytesseract).

Alle coordinaten worden GENORMALISEERD teruggegeven (0..1), oorsprong linksboven.
Zo zijn ze onafhankelijk van schaal/DPI en matchen de browser-overlay exact met
het echte lakken (PyMuPDF gebruikt eveneens oorsprong linksboven).

extract_pages() geeft terug: (pages, used_ocr_any)
  pages = [ { "page_no": int, "width": float, "height": float,
              "used_ocr": bool,
              "words": [ {"x0","y0","x1","y1","text","line_id"} , ... ] }, ... ]
"""
import fitz  # PyMuPDF


def _norm(x0, y0, x1, y1, w, h):
    return x0 / w, y0 / h, x1 / w, y1 / h


def _extract_digital(page):
    w, h = page.rect.width, page.rect.height
    out = []
    # (x0, y0, x1, y1, "woord", block_no, line_no, word_no)
    for x0, y0, x1, y1, word, block, line, _ in page.get_text("words"):
        nx0, ny0, nx1, ny1 = _norm(x0, y0, x1, y1, w, h)
        out.append({"x0": nx0, "y0": ny0, "x1": nx1, "y1": ny1,
                    "text": word, "line_id": "%d-%d" % (block, line)})
    return out


def _extract_ocr(page, dpi, lang):
    import pytesseract
    from PIL import Image

    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)

    out = []
    n = len(data["text"])
    W, H = float(pix.width), float(pix.height)
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        x, y = data["left"][i], data["top"][i]
        bw, bh = data["width"][i], data["height"][i]
        out.append({
            "x0": x / W, "y0": y / H, "x1": (x + bw) / W, "y1": (y + bh) / H,
            "text": txt, "line_id": "%d-%d" % (data["block_num"][i], data["line_num"][i]),
        })
    return out


def extract_pages(pdf_bytes, ocr_min_chars=20, ocr_dpi=200, ocr_lang="nld"):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    used_ocr_any = False
    try:
        for page_no in range(len(doc)):
            page = doc[page_no]
            words = _extract_digital(page)
            has_text_layer = sum(len(w["text"]) for w in words) >= ocr_min_chars
            if has_text_layer:
                used_ocr = False
            else:
                words = _extract_ocr(page, ocr_dpi, ocr_lang)
                used_ocr = True
                used_ocr_any = True
            pages.append({
                "page_no": page_no,
                "width": page.rect.width,
                "height": page.rect.height,
                "used_ocr": used_ocr,
                "words": words,
            })
    finally:
        doc.close()
    return pages, used_ocr_any
