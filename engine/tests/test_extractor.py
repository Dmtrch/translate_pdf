# -*- coding: utf-8 -*-
import pymupdf

from extractor import extract_page, is_page_scanned


def test_text_page_not_scanned(text_pdf):
    doc = pymupdf.open(text_pdf)
    assert not is_page_scanned(doc[0])
    doc.close()


def test_scan_page_detected(scan_pdf):
    doc = pymupdf.open(scan_pdf)
    assert is_page_scanned(doc[0])
    content = extract_page(doc[0])
    assert content.scanned and not content.blocks
    doc.close()


def test_extract_blocks_table_image(text_pdf):
    doc = pymupdf.open(text_pdf)
    page = doc[0]
    content = extract_page(page)

    # Текстовые блоки найдены с координатами в пределах страницы
    assert len(content.blocks) >= 3  # заголовок + 3 абзаца (минус попавшие в таблицу)
    for block in content.blocks:
        x0, y0, x1, y1 = block.bbox
        assert 0 <= x0 < x1 <= content.width
        assert 0 <= y0 < y1 <= content.height
        assert block.text.strip()
        assert block.font_size > 0

    # Заголовок распознан жирным
    header = next(b for b in content.blocks if "Engineering Report" in b.text)
    assert header.bold

    # Таблица 4x3 найдена, все ячейки с текстом и bbox
    assert len(content.tables) == 1
    cells = content.tables[0].cells
    assert len(cells) == 12
    assert any(c.text == "Quarter" for c in cells)
    assert any(c.text == "1.2M" for c in cells)

    # Блоки таблицы не продублированы в текстовых блоках
    assert not any("Quarter" in b.text for b in content.blocks)

    # Изображение присутствует на странице (его не извлекаем — оно остаётся в PDF)
    assert page.get_image_info()
    doc.close()
