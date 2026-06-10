# -*- coding: utf-8 -*-
"""Сборка итогового PDF с сохранением вёрстки.

Текстовые страницы: исходный текст удаляется redaction-аннотациями строго
по bbox блоков (изображения и линии сетки таблиц не затрагиваются), затем
перевод вставляется в те же bbox с автоподбором размера шрифта (до 6pt).

Сканированные страницы: поверх изображения рисуется белая подложка по bbox
распознанной строки, сверху — переведённый текст.
"""

import os
from typing import List, Optional

import pymupdf

from extractor import BBox, PageContent, TextBlock

MIN_FONT_SIZE = 6.0
_FONT_STEP = 0.5
_FONT_NAME = "UniEmb"  # имя для встраиваемого юникод-шрифта

# Юникод-шрифты macOS, покрывающие кириллицу и CJK (PRD: 8 языков)
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]


def find_unicode_font() -> str:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    raise RuntimeError(
        "Не найден юникод-шрифт (Arial Unicode). Проверьте /System/Library/Fonts/Supplemental/"
    )


def _insert_fitted_text(page: "pymupdf.Page", bbox: BBox, text: str,
                        font_size: float, fontfile: str, align: int = 0) -> float:
    """Вставляет текст в bbox, уменьшая шрифт, пока текст не поместится.

    Возвращает фактически использованный размер шрифта.
    insert_textbox не вставляет текст при нехватке места (возвращает
    отрицательное значение) — этим пользуемся для подбора размера.
    """
    rect = pymupdf.Rect(bbox)
    size = max(font_size, MIN_FONT_SIZE)
    while size >= MIN_FONT_SIZE:
        leftover = page.insert_textbox(
            rect, text,
            fontsize=size,
            fontname=_FONT_NAME,
            fontfile=fontfile,
            align=align,
            lineheight=1.08,
        )
        if leftover >= 0:
            return size
        size -= _FONT_STEP

    # Не влезло даже при 6pt: расширяем прямоугольник вниз на недостающую
    # высоту (PRD допускает минимум 6pt; обрезать текст нельзя)
    leftover = page.insert_textbox(
        rect, text, fontsize=MIN_FONT_SIZE, fontname=_FONT_NAME,
        fontfile=fontfile, align=align, lineheight=1.08,
    )
    if leftover < 0:
        rect.y1 += -leftover + 2
        page.insert_textbox(
            rect, text, fontsize=MIN_FONT_SIZE, fontname=_FONT_NAME,
            fontfile=fontfile, align=align, lineheight=1.08,
        )
    return MIN_FONT_SIZE


def render_text_page(page: "pymupdf.Page", content: PageContent,
                     fontfile: str) -> None:
    """Заменяет текст на текстовой странице, не сдвигая картинки и сетку таблиц."""
    has_redactions = False
    for block in content.blocks:
        if block.translated:
            page.add_redact_annot(pymupdf.Rect(block.bbox))
            has_redactions = True
    for table in content.tables:
        for cell in table.cells:
            if cell.translated:
                page.add_redact_annot(pymupdf.Rect(cell.bbox))
                has_redactions = True

    if has_redactions:
        # images=NONE — картинки не затираются; graphics=NONE — линии
        # (сетка таблиц, рамки) остаются нетронутыми
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        )

    for block in content.blocks:
        if block.translated:
            _insert_fitted_text(page, block.bbox, block.translated,
                                block.font_size, fontfile)
    for table in content.tables:
        for cell in table.cells:
            if cell.translated:
                # лёгкий внутренний отступ, чтобы текст не лёг на линии сетки
                rect = pymupdf.Rect(cell.bbox) + (2, 2, -2, -2)
                _insert_fitted_text(page, tuple(rect), cell.translated,
                                    10.0, fontfile)


def render_scanned_page(page: "pymupdf.Page", blocks: List[TextBlock],
                        fontfile: str) -> None:
    """Накладывает перевод поверх изображения скана (белая подложка + текст)."""
    for block in blocks:
        if not block.translated:
            continue
        rect = pymupdf.Rect(block.bbox)
        page.draw_rect(rect, color=None, fill=(1, 1, 1))
    for block in blocks:
        if block.translated:
            _insert_fitted_text(page, block.bbox, block.translated,
                                block.font_size, fontfile)
