# -*- coding: utf-8 -*-
"""Тесты сборки PDF: текст заменён, картинка и сетка таблицы не пострадали."""
import pymupdf

from extractor import extract_page
from renderer import find_unicode_font, render_scanned_page, render_text_page


def _image_pixels(doc, page_num, bbox):
    """Растрирует область картинки для попиксельного сравнения."""
    clip = pymupdf.Rect(bbox)
    return doc[page_num].get_pixmap(clip=clip, dpi=72).samples


def test_render_text_page(text_pdf, tmp_path):
    fontfile = find_unicode_font()
    doc = pymupdf.open(text_pdf)
    page = doc[0]

    image_bbox = page.get_image_info()[0]["bbox"]
    pixels_before = _image_pixels(doc, 0, image_bbox)

    content = extract_page(page)
    for block in content.blocks:
        block.translated = "Переведённый текст блока — кириллица для проверки шрифта."
    for cell in content.tables[0].cells:
        cell.translated = "Ячейка"

    render_text_page(page, content, fontfile)
    out = str(tmp_path / "out.pdf")
    doc.save(out)
    doc.close()

    result = pymupdf.open(out)
    text = result[0].get_text()
    # Старый текст удалён, новый вставлен
    assert "Annual report" not in text
    assert "Переведённый текст блока" in text
    assert "Ячейка" in text
    # Картинка на месте: попиксельное совпадение области
    assert _image_pixels(result, 0, image_bbox) == pixels_before
    # Сетка таблицы сохранилась: на странице остались линии
    drawings = result[0].get_drawings()
    assert drawings, "Линии сетки таблицы исчезли после redaction"
    result.close()


def test_render_scanned_page(scan_pdf, tmp_path):
    from extractor import TextBlock

    fontfile = find_unicode_font()
    doc = pymupdf.open(scan_pdf)
    page = doc[0]

    blocks = [TextBlock(bbox=(72, 72, 400, 92), text="Engineering Report",
                        font_size=14.0, translated="Инженерный отчёт")]
    render_scanned_page(page, blocks, fontfile)
    out = str(tmp_path / "scan_out.pdf")
    doc.save(out)
    doc.close()

    result = pymupdf.open(out)
    assert "Инженерный отчёт" in result[0].get_text()
    # Исходное изображение страницы осталось
    assert result[0].get_image_info()
    result.close()


def test_font_autoshrink(text_pdf, tmp_path):
    """Длинный перевод в маленьком bbox — шрифт уменьшается, текст не теряется."""
    from renderer import _insert_fitted_text, MIN_FONT_SIZE

    fontfile = find_unicode_font()
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    long_text = "Очень длинный переведённый текст, который заведомо не помещается " * 4
    used = _insert_fitted_text(page, (72, 72, 220, 100), long_text, 12.0, fontfile)
    assert used >= MIN_FONT_SIZE
    # Весь текст вставлен (последнее слово присутствует)
    assert "помещается" in page.get_text()
    doc.close()
