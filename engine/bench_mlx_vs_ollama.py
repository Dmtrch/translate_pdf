# -*- coding: utf-8 -*-
"""Бенчмарк этапа 3: in-process MLX против Ollama с параллелизмом.

Берёт текстовые блоки из PDF (как настоящий конвейер), переводит их
обоими бэкендами и печатает время, скорость и примеры переводов.

Запуск: .venv/bin/python bench_mlx_vs_ollama.py ../test.pdf
"""

import sys
import time

import pymupdf

import sysinfo
from extractor import extract_page
from translator import OllamaTranslator

OLLAMA_MODEL = "bob-hymt:latest"
MLX_MODEL = "mlx-community/HY-MT1.5-1.8B-8bit"
SYSTEM_PROMPT = ("You are a professional translator. Translate the user's "
                 "text from English into Russian. Preserve numbers, units and "
                 "proper names. Output ONLY the translated text without any "
                 "explanations, comments or quotes.")


def collect_blocks(pdf_path):
    doc = pymupdf.open(pdf_path)
    items = []
    for page in doc:
        items.extend(item.text for item in extract_page(page).text_items())
    doc.close()
    return items


def bench_ollama(texts):
    tr = OllamaTranslator(OLLAMA_MODEL)
    tr.check()
    parallel = sysinfo.recommended_parallelism(
        sysinfo.available_memory_gb(),
        unloaded_model_gb=tr.unloaded_model_size_gb())
    print(f"[Ollama] модель {OLLAMA_MODEL}, parallel={parallel}")
    tr.translate("warm up", src="en", dst="ru")  # прогрев: загрузка модели
    t0 = time.monotonic()
    results = tr.translate_batch(texts, src="en", dst="ru",
                                 concurrency=parallel)
    elapsed = time.monotonic() - t0
    return results, elapsed, tr.tokens_per_second()


def bench_mlx(texts):
    from mlx_lm import load, generate
    print(f"[MLX] загрузка {MLX_MODEL}...")
    t0 = time.monotonic()
    model, tokenizer = load(MLX_MODEL)
    load_sec = time.monotonic() - t0
    print(f"[MLX] модель загружена за {load_sec:.1f} с")
    results = []
    t0 = time.monotonic()
    for text in texts:
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}]
        prompt = tokenizer.apply_chat_template(messages,
                                               add_generation_prompt=True)
        results.append(generate(model, tokenizer, prompt=prompt,
                                max_tokens=2048).strip())
    elapsed = time.monotonic() - t0
    return results, elapsed, load_sec


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "../test.pdf"
    texts = collect_blocks(pdf_path)
    total_chars = sum(len(t) for t in texts)
    print(f"Блоков: {len(texts)}, символов: {total_chars}\n")

    mlx_results, mlx_sec, mlx_load_sec = bench_mlx(texts)
    print(f"[MLX] перевод: {mlx_sec:.1f} с "
          f"({total_chars / mlx_sec:.0f} симв/с), "
          f"+{mlx_load_sec:.1f} с загрузка модели\n")

    ollama_results, ollama_sec, ollama_tps = bench_ollama(texts)
    print(f"[Ollama] перевод: {ollama_sec:.1f} с "
          f"({total_chars / ollama_sec:.0f} симв/с), tps={ollama_tps:.1f}\n")

    print("=== Сравнение примеров (первые 3 блока) ===")
    for i in range(min(3, len(texts))):
        print(f"\n--- Оригинал: {texts[i][:120]}")
        print(f"    MLX:      {mlx_results[i][:120]}")
        print(f"    Ollama:   {ollama_results[i][:120]}")

    ratio = mlx_sec / ollama_sec if ollama_sec else 0
    print(f"\nИтог: MLX {'медленнее' if ratio > 1 else 'быстрее'} "
          f"Ollama в {max(ratio, 1 / ratio) if ratio else 0:.2f}× "
          f"(без учёта {mlx_load_sec:.0f} с загрузки MLX-модели)")


if __name__ == "__main__":
    main()
