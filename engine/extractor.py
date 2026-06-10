# -*- coding: utf-8 -*-
"""Извлечение структуры страницы PDF: текстовые блоки, таблицы, признак скана.

Логика адаптирована из референсного проекта pdf->word/converter.py:
- детекция сканированных страниц по количеству значимых символов;
- фильтрация текстовых блоков, попадающих в область таблиц;
- извлечение шрифта/размера/стилей из спанов.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pymupdf

BBox = Tuple[float, float, float, float]

_MIN_TEXT_CHARS = 30  # минимум значимых символов, чтобы считать страницу текстовой


@dataclass
class TextBlock:
    bbox: BBox
    text: str
    font_size: float
    font_name: str = ""
    bold: bool = False
    italic: bool = False
    translated: Optional[str] = None


@dataclass
class TableCellData:
    bbox: BBox
    text: str
    translated: Optional[str] = None


@dataclass
class TableData:
    bbox: BBox
    cells: List[TableCellData] = field(default_factory=list)


@dataclass
class PageContent:
    number: int  # 0-based
    width: float
    height: float
    scanned: bool
    blocks: List[TextBlock] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)

    def text_items(self):
        """Все переводимые элементы страницы (блоки и ячейки таблиц)."""
        items = [b for b in self.blocks if b.text.strip()]
        for table in self.tables:
            items.extend(c for c in table.cells if c.text.strip())
        return items


def is_page_scanned(page: "pymupdf.Page") -> bool:
    text = page.get_text("text")
    return sum(1 for c in text if not c.isspace()) < _MIN_TEXT_CHARS


def _bbox_overlaps(bbox1: BBox, bbox2: BBox) -> bool:
    return not (bbox1[2] < bbox2[0] or bbox1[0] > bbox2[2] or
                bbox1[3] < bbox2[1] or bbox1[1] > bbox2[3])


def _clean_block_text(block: dict) -> str:
    """Склеивает спаны блока в один абзац, убирая переносы строк."""
    lines = []
    for line in block.get("lines", []):
        line_text = "".join(span.get("text", "") for span in line.get("spans", []))
        if line_text.strip():
            lines.append(line_text.strip())
    return " ".join(lines)


def _block_font_info(block: dict) -> Tuple[float, str, bool, bool]:
    """Доминирующий размер шрифта, имя шрифта и стили блока."""
    sizes: Counter = Counter()
    font_name = ""
    bold = italic = False
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            if not span.get("text", "").strip():
                continue
            sizes[round(span.get("size", 11.0), 1)] += len(span["text"])
            if not font_name:
                font_name = span.get("font", "")
                flags = span.get("flags", 0)
                bold = "bold" in font_name.lower() or bool(flags & 16)
                italic = "italic" in font_name.lower() or bool(flags & 2)
    font_size = sizes.most_common(1)[0][0] if sizes else 11.0
    if "+" in font_name:
        font_name = font_name.split("+")[-1]
    return font_size, font_name, bold, italic


def _extract_tables(page: "pymupdf.Page") -> List[TableData]:
    try:
        found = page.find_tables(strategy="lines_strict")
        page_tables = found.tables if found else []
    except Exception:
        return []

    tables: List[TableData] = []
    for table in page_tables:
        rows_text = table.extract()
        cells: List[TableCellData] = []
        for row_obj, row_text in zip(table.rows, rows_text):
            for cell_bbox, cell_text in zip(row_obj.cells, row_text):
                if cell_bbox is None:
                    continue
                cells.append(TableCellData(bbox=tuple(cell_bbox),
                                           text=(cell_text or "").strip()))
        tables.append(TableData(bbox=tuple(table.bbox), cells=cells))
    return tables


def extract_page(page: "pymupdf.Page") -> PageContent:
    """Извлекает структуру страницы. Для сканов блоки заполняет OCR (ocr.py)."""
    content = PageContent(
        number=page.number,
        width=page.rect.width,
        height=page.rect.height,
        scanned=is_page_scanned(page),
    )
    if content.scanned:
        return content

    content.tables = _extract_tables(page)
    table_bboxes = [t.bbox for t in content.tables]

    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        if any(_bbox_overlaps(block["bbox"], tb) for tb in table_bboxes):
            continue  # текст внутри таблицы обрабатывается через ячейки
        text = _clean_block_text(block)
        if not text:
            continue
        font_size, font_name, bold, italic = _block_font_info(block)
        content.blocks.append(TextBlock(
            bbox=tuple(block["bbox"]),
            text=text,
            font_size=font_size,
            font_name=font_name,
            bold=bold,
            italic=italic,
        ))
    return content
