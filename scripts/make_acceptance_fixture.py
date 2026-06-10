#!/usr/bin/env python3
"""Генерирует fixtures/big.pdf для приёмочного теста 1 из PRD:
10 страниц, 3 таблицы, 5 изображений, текстовые абзацы.

Запуск: engine/.venv/bin/python scripts/make_acceptance_fixture.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_fixtures import PAGE_H, PAGE_W, PARAGRAPHS, _draw_table, _make_test_image

import pymupdf

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(PROJECT_DIR, "fixtures", "big.pdf")

TABLE_PAGES = {1, 4, 7}   # 3 таблицы
IMAGE_PAGES = {0, 2, 4, 6, 8}  # 5 изображений


def main() -> None:
    doc = pymupdf.open()
    image_png = _make_test_image()

    for page_num in range(10):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        y = 72.0
        page.insert_textbox(
            pymupdf.Rect(72, y, PAGE_W - 72, y + 30),
            f"Chapter {page_num + 1}: Operations Overview",
            fontsize=16, fontname="hebo",
        )
        y += 50
        for text in PARAGRAPHS:
            page.insert_textbox(pymupdf.Rect(72, y, PAGE_W - 72, y + 80),
                                text, fontsize=11, fontname="helv")
            y += 90

        if page_num in TABLE_PAGES:
            y = _draw_table(page, y) + 30
        if page_num in IMAGE_PAGES:
            page.insert_image(pymupdf.Rect(72, y, 272, y + 120), stream=image_png)

    doc.save(OUT)
    doc.close()

    check = pymupdf.open(OUT)
    n_images = sum(1 for p in check for _ in p.get_image_info())
    n_tables = sum(1 for p in check if p.find_tables(strategy="lines_strict").tables)
    assert check.page_count == 10 and n_images == 5 and n_tables == 3, \
        f"pages={check.page_count} images={n_images} tables={n_tables}"
    check.close()
    print(f"OK: {OUT} (10 страниц, 3 таблицы, 5 изображений)")


if __name__ == "__main__":
    main()
