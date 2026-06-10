# -*- coding: utf-8 -*-
"""Разовая проверка MLX-модели HY-MT1.5: скачивание, генерация, скорость.

Запуск: .venv/bin/python test_mlx.py
При первом запуске модель (~2 ГБ) скачается в кэш HuggingFace.
"""

import time

from mlx_lm import load, generate

MODEL = "mlx-community/HY-MT1.5-1.8B-8bit"

print(f"Загрузка модели {MODEL} (при первом запуске — скачивание ~2 ГБ)...")
t0 = time.monotonic()
model, tokenizer = load(MODEL)
print(f"Модель загружена за {time.monotonic() - t0:.1f} с")

messages = [{
    "role": "user",
    "content": "Translate the following text from English into Russian. "
               "Output only the translation.\n\nGood morning, dear friends!",
}]
prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True)

t0 = time.monotonic()
text = generate(model, tokenizer, prompt=prompt, max_tokens=100, verbose=True)
print(f"\nИтого генерация: {time.monotonic() - t0:.1f} с")
print(f"Перевод: {text}")
