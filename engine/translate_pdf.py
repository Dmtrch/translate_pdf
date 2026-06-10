#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI-оркестратор перевода PDF. Точка входа для SwiftUI-приложения.

Пишет в stdout события JSON-lines (по одному JSON-объекту на строку):
  {"event":"stage_start","stage":"parse|ocr|translate|render"}
  {"event":"progress","stage":...,"done":N,"total":M,"eta_sec":S,"tps":T}
  {"event":"done","output":"/path/out.pdf"}
  {"event":"error","code":"...","message":"..."}

Пример:
  .venv/bin/python translate_pdf.py input.pdf -o out.pdf --to ru --model bob-hymt:latest
"""

import argparse
import json
import os
import sys
import time
from typing import List, Optional

import pymupdf

import sysinfo
from extractor import PageContent, extract_page
from ocr import ocr_page
from renderer import find_unicode_font, render_scanned_page, render_text_page
from translator import LANG_NAMES, OllamaError, OllamaTranslator

DEFAULT_MODEL = "bob-hymt:latest"

# JSON-протокол идёт в настоящий stdout; sys.stdout перенаправляется в stderr,
# чтобы print из библиотек (например, реклама pymupdf_layout в find_tables)
# не ломал поток событий
_PROTOCOL_STDOUT = sys.stdout


def emit(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False), file=_PROTOCOL_STDOUT, flush=True)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Перевод PDF с сохранением вёрстки (локально, через Ollama)")
    parser.add_argument("input", help="Исходный PDF")
    parser.add_argument("-o", "--output", help="Выходной PDF (по умолчанию <имя>_translated.pdf)")
    parser.add_argument("--from", dest="src", default="auto",
                        choices=["auto"] + list(LANG_NAMES.keys()),
                        help="Язык оригинала (по умолчанию auto)")
    parser.add_argument("--to", dest="dst", required=True,
                        choices=list(LANG_NAMES.keys()), help="Язык перевода")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Модель Ollama (по умолчанию {DEFAULT_MODEL})")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--parallel", type=int, default=4,
                        help="Число параллельных запросов перевода "
                             "(0 = авто по свободной памяти)")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> str:
    if not os.path.exists(args.input):
        raise RuntimeError(f"Файл не найден: {args.input}")
    output = args.output or os.path.splitext(args.input)[0] + "_translated.pdf"

    # Ранняя проверка прав на запись — до многоминутного перевода
    out_dir = os.path.dirname(os.path.abspath(output))
    if not os.access(out_dir, os.W_OK):
        raise RuntimeError(f"Нет прав на запись в папку: {out_dir}")

    translator = OllamaTranslator(args.model, url=args.ollama_url)
    translator.check()  # ранняя проверка: сервер доступен, модель существует
    fontfile = find_unicode_font()

    try:
        doc = pymupdf.open(args.input)
    except Exception as e:
        raise RuntimeError(f"Не удалось открыть PDF: {e}")
    if doc.page_count == 0:
        raise RuntimeError("PDF не содержит страниц")

    # --- Этап 1: парсинг структуры -----------------------------------------
    emit({"event": "stage_start", "stage": "parse"})
    contents: List[PageContent] = []
    t0 = time.monotonic()
    for page in doc:
        contents.append(extract_page(page))
        done = page.number + 1
        per_page = (time.monotonic() - t0) / done
        emit({"event": "progress", "stage": "parse", "done": done,
              "total": doc.page_count,
              "eta_sec": round(per_page * (doc.page_count - done), 1)})

    # --- Этап 1б: OCR сканированных страниц --------------------------------
    scanned_pages = [c for c in contents if c.scanned]
    if scanned_pages:
        emit({"event": "stage_start", "stage": "ocr"})
        t0 = time.monotonic()
        for i, content in enumerate(scanned_pages, start=1):
            content.blocks = ocr_page(doc[content.number], src_lang=args.src)
            per_page = (time.monotonic() - t0) / i
            emit({"event": "progress", "stage": "ocr", "done": i,
                  "total": len(scanned_pages),
                  "eta_sec": round(per_page * (len(scanned_pages) - i), 1)})

    # --- Этап 2: перевод -----------------------------------------------------
    items = [item for content in contents for item in content.text_items()]
    total_chars = sum(len(item.text) for item in items) or 1
    emit({"event": "stage_start", "stage": "translate"})
    t0 = time.monotonic()
    parallel = args.parallel
    if parallel <= 0:
        free_gb = sysinfo.available_memory_gb()
        parallel = sysinfo.recommended_parallelism(
            free_gb, unloaded_model_gb=translator.unloaded_model_size_gb())
        event = {"event": "info", "parallel": parallel}
        if free_gb is not None:
            event["free_mem_gb"] = round(free_gb, 1)
        emit(event)
    progress = {"done": 0, "chars": 0}

    def on_progress(index: int) -> None:
        # Вызывается из основного потока (см. translate_batch)
        progress["done"] += 1
        progress["chars"] += len(items[index].text)
        elapsed = time.monotonic() - t0
        rate = progress["chars"] / elapsed if elapsed > 0 else 0  # символов/сек
        eta = (total_chars - progress["chars"]) / rate if rate > 0 else 0
        event = {"event": "progress", "stage": "translate",
                 "done": progress["done"], "total": len(items),
                 "eta_sec": round(eta, 1)}
        tps = translator.tokens_per_second()  # агрегат по всем потокам
        if tps:
            event["tps"] = round(tps, 1)
        emit(event)

    translations = translator.translate_batch(
        [item.text for item in items], src=args.src, dst=args.dst,
        concurrency=parallel, on_progress=on_progress)
    for item, translated in zip(items, translations):
        item.translated = translated

    # --- Этап 3: сборка PDF ---------------------------------------------------
    emit({"event": "stage_start", "stage": "render"})
    for i, content in enumerate(contents, start=1):
        page = doc[content.number]
        if content.scanned:
            render_scanned_page(page, content.blocks, fontfile)
        else:
            render_text_page(page, content, fontfile)
        emit({"event": "progress", "stage": "render", "done": i,
              "total": len(contents), "eta_sec": 0})

    try:
        doc.save(output, garbage=3, deflate=True)
    except Exception as e:
        raise RuntimeError(f"Не удалось сохранить результат: {e}")
    finally:
        doc.close()
    return output


def main() -> None:
    sys.stdout = sys.stderr  # см. комментарий у _PROTOCOL_STDOUT
    args = _parse_args()
    try:
        output = run(args)
    except OllamaError as e:
        emit({"event": "error", "code": e.code, "message": str(e)})
        sys.exit(1)
    except Exception as e:
        emit({"event": "error", "code": "engine_error", "message": str(e)})
        sys.exit(1)
    emit({"event": "done", "output": output})


if __name__ == "__main__":
    main()
