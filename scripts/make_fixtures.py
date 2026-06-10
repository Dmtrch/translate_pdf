#!/usr/bin/env python3
"""Генерирует тестовые PDF-фикстуры в папке fixtures/:

- text.pdf — текстовый PDF: абзацы, таблица с сеткой, встроенное изображение.
- scan.pdf — «сканированный» PDF: те же страницы, растрированные в картинки.

Запуск: engine/.venv/bin/python scripts/make_fixtures.py
"""

import os

import pymupdf

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(PROJECT_DIR, "fixtures")

PAGE_W, PAGE_H = 595, 842  # A4 в пунктах

PARAGRAPHS = [
    "Annual report of the engineering department. This document describes "
    "the results achieved during the last fiscal year and outlines the "
    "plans for the upcoming period.",
    "The new processing pipeline reduced average latency by 40 percent. "
    "Customer satisfaction surveys show a steady improvement across all "
    "product lines.",
    "Safety remains our top priority. All field engineers completed the "
    "mandatory certification program before the end of the third quarter.",
]

TABLE_ROWS = [
    ["Quarter", "Revenue", "Growth"],
    ["Q1", "1.2M", "5%"],
    ["Q2", "1.4M", "8%"],
    ["Q3", "1.7M", "12%"],
]


def _make_test_image() -> bytes:
    """Рисует простую картинку (цветные прямоугольники) и возвращает PNG."""
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=120)
    page.draw_rect(pymupdf.Rect(0, 0, 200, 120), color=None, fill=(0.2, 0.4, 0.8))
    page.draw_rect(pymupdf.Rect(20, 20, 90, 100), color=None, fill=(0.9, 0.6, 0.1))
    page.draw_circle(pymupdf.Point(145, 60), 35, color=None, fill=(0.1, 0.7, 0.3))
    png = page.get_pixmap(dpi=150).tobytes("png")
    doc.close()
    return png


def _draw_table(page: "pymupdf.Page", origin_y: float) -> float:
    """Рисует таблицу с сеткой, возвращает нижнюю координату."""
    x0, col_w, row_h = 72, 150, 24
    n_cols = len(TABLE_ROWS[0])
    for r, row in enumerate(TABLE_ROWS):
        y = origin_y + r * row_h
        for c, cell in enumerate(row):
            x = x0 + c * col_w
            rect = pymupdf.Rect(x, y, x + col_w, y + row_h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.7)
            page.insert_textbox(
                rect + (4, 5, -4, -2),
                cell,
                fontsize=10,
                fontname="helv" if r else "hebo",
            )
    return origin_y + len(TABLE_ROWS) * row_h


def make_text_pdf(path: str) -> None:
    doc = pymupdf.open()
    image_png = _make_test_image()

    for page_num in range(2):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        y = 72.0
        page.insert_textbox(
            pymupdf.Rect(72, y, PAGE_W - 72, y + 30),
            f"Engineering Report — Page {page_num + 1}",
            fontsize=16,
            fontname="hebo",
        )
        y += 50
        for text in PARAGRAPHS:
            rect = pymupdf.Rect(72, y, PAGE_W - 72, y + 80)
            page.insert_textbox(rect, text, fontsize=11, fontname="helv")
            y += 90

        y = _draw_table(page, y) + 30
        page.insert_image(pymupdf.Rect(72, y, 272, y + 120), stream=image_png)

    doc.save(path)
    doc.close()


def make_scan_pdf(text_pdf_path: str, path: str) -> None:
    """Растрирует страницы text.pdf в картинки — имитация скана."""
    src = pymupdf.open(text_pdf_path)
    doc = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=150)
        out_page = doc.new_page(width=page.rect.width, height=page.rect.height)
        out_page.insert_image(out_page.rect, stream=pix.tobytes("png"))
    doc.save(path)
    doc.close()
    src.close()


def main() -> None:
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    text_path = os.path.join(FIXTURES_DIR, "text.pdf")
    scan_path = os.path.join(FIXTURES_DIR, "scan.pdf")

    make_text_pdf(text_path)
    make_scan_pdf(text_path, scan_path)

    # Самопроверка: файлы открываются, в text.pdf есть текст, в scan.pdf — нет
    text_doc = pymupdf.open(text_path)
    scan_doc = pymupdf.open(scan_path)
    assert text_doc.page_count == 2 and scan_doc.page_count == 2
    assert len(text_doc[0].get_text().strip()) > 100, "text.pdf должен содержать текст"
    assert len(scan_doc[0].get_text().strip()) == 0, "scan.pdf не должен содержать текстовый слой"
    assert text_doc[0].get_image_info(), "text.pdf должен содержать изображение"
    text_doc.close()
    scan_doc.close()

    print(f"OK: {text_path}")
    print(f"OK: {scan_path}")


if __name__ == "__main__":
    main()
