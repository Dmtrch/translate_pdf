# -*- coding: utf-8 -*-
import pymupdf

from ocr import ocr_page


def test_ocr_scan_page(scan_pdf):
    doc = pymupdf.open(scan_pdf)
    page = doc[0]
    blocks = ocr_page(page, src_lang="en")

    assert blocks, "OCR не вернул ни одной строки"

    full_text = " ".join(b.text for b in blocks)
    assert "Engineering Report" in full_text
    assert "Quarter" in full_text

    for block in blocks:
        x0, y0, x1, y1 = block.bbox
        assert 0 <= x0 < x1 <= page.rect.width
        assert 0 <= y0 < y1 <= page.rect.height
        assert block.font_size >= 6.0

    # Строки отсортированы сверху вниз: заголовок должен идти первым
    assert "Engineering Report" in blocks[0].text
    doc.close()
