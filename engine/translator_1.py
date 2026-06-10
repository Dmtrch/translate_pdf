# -*- coding: utf-8 -*-
"""Экспериментальный клиент Ollama: перевод блоков пачками.

Вместо одного запроса на блок склеивает несколько блоков в один запрос
с маркерами границ. Это сокращает число запросов на порядок и не платит
prefill системного промпта за каждый блок. Чистая скорость генерации
(bandwidth-bound) не меняется — выигрыш только на накладных расходах.

Интерфейс совместим с translator.OllamaTranslator: для включения достаточно
заменить импорт в translate_pdf.py на
    from translator_1 import BatchedOllamaTranslator as OllamaTranslator

Если модель ломает маркеры в ответе, пачка автоматически переводится
поблочно (fallback на родительский translate) — корректность не страдает.
"""

import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, List, Optional, Sequence, Tuple

from translator import LANG_NAMES, OllamaError, OllamaTranslator

# Бюджет на склейку: суммарная длина текстов в пачке (символы) и максимум
# блоков. Промпт + перевод должны помещаться в слот сервера (обычно 4096
# токенов); ~6000 символов ≈ 1500 токенов на вход и столько же на выход.
MAX_CHUNK_CHARS = 6000
MAX_CHUNK_BLOCKS = 12

# Маркер границы блока: на отдельной строке до и в ответе модели.
_MARKER = "[[{n}]]"
_MARKER_RE = re.compile(r"\[\[(\d+)\]\]")


def _split_chunks(texts: Sequence[str]) -> List[List[int]]:
    """Группирует индексы непустых блоков в пачки по бюджету символов."""
    chunks: List[List[int]] = []
    current: List[int] = []
    size = 0
    for i, text in enumerate(texts):
        if not text.strip():
            continue
        if current and (size + len(text) > MAX_CHUNK_CHARS
                        or len(current) >= MAX_CHUNK_BLOCKS):
            chunks.append(current)
            current, size = [], 0
        current.append(i)
        size += len(text)
    if current:
        chunks.append(current)
    return chunks


class BatchedOllamaTranslator(OllamaTranslator):

    def _batch_system_prompt(self, src: str, dst: str) -> str:
        dst_name = LANG_NAMES.get(dst, dst)
        if src == "auto":
            src_part = "the source language (detect it automatically)"
        else:
            src_part = LANG_NAMES.get(src, src)
        return (
            f"You are a professional translator. The user's text contains "
            f"several segments, each preceded by a marker line like [[7]]. "
            f"Translate every segment from {src_part} into {dst_name}. "
            f"Preserve numbers, units and proper names. Reproduce each "
            f"marker line EXACTLY as is, followed by the translation of its "
            f"segment. Output ONLY markers and translations, nothing else."
        )

    def _translate_chunk(self, texts: Sequence[str], indices: List[int],
                         src: str, dst: str) -> List[Tuple[int, str]]:
        """Переводит одну пачку. Возвращает [(индекс блока, перевод), ...]."""
        joined = "\n".join(
            f"{_MARKER.format(n=k)}\n{texts[i]}"
            for k, i in enumerate(indices)
        )
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": self._batch_system_prompt(src, dst)},
                {"role": "user", "content": joined},
            ],
        }
        try:
            resp = self._session().post(f"{self.url}/api/chat", json=payload,
                                        timeout=self.timeout)
            resp.raise_for_status()
        except Exception:
            # Сетевые/HTTP ошибки обрабатывает поблочный fallback ниже —
            # он бросит OllamaError с понятным кодом, если сервер недоступен
            return self._fallback(texts, indices, src, dst)

        data = resp.json()
        with self._stats_lock:
            self.total_eval_count += data.get("eval_count", 0)
            self.total_eval_duration_ns += data.get("eval_duration", 0)

        content = data.get("message", {}).get("content", "")
        parsed = self._parse(content, len(indices))
        if parsed is None:
            # Модель сломала маркеры — переводим эту пачку поблочно
            return self._fallback(texts, indices, src, dst)
        return [(indices[k], translated) for k, translated in enumerate(parsed)]

    @staticmethod
    def _parse(content: str, expected: int) -> Optional[List[str]]:
        """Разбирает ответ по маркерам. None — если структура нарушена."""
        parts = _MARKER_RE.split(content)
        # split даёт [преамбула, n1, текст1, n2, текст2, ...]
        if len(parts) < 2 * expected + 1:
            return None
        result: List[Optional[str]] = [None] * expected
        for k in range(1, len(parts) - 1, 2):
            n = int(parts[k])
            if 0 <= n < expected and result[n] is None:
                result[n] = parts[k + 1].strip()
        if any(r is None for r in result):
            return None
        return result  # type: ignore[return-value]

    def _fallback(self, texts: Sequence[str], indices: List[int],
                  src: str, dst: str) -> List[Tuple[int, str]]:
        return [(i, self.translate(texts[i], src, dst)) for i in indices]

    def translate_batch(self, texts: List[str], src: str = "auto",
                        dst: str = "en", concurrency: int = 4,
                        on_progress: Optional[Callable[[int], None]] = None,
                        ) -> List[str]:
        """Переводит список текстов пачками, сохраняя исходный порядок.

        Интерфейс идентичен OllamaTranslator.translate_batch: on_progress(i)
        вызывается для каждого блока по мере готовности его пачки.
        """
        if not texts:
            return []
        results: List[str] = list(texts)  # пустые блоки остаются как есть
        chunks = _split_chunks(texts)
        if not chunks:
            return results
        concurrency = max(1, min(concurrency, len(chunks)))
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            pending = {
                pool.submit(self._translate_chunk, texts, chunk, src, dst)
                for chunk in chunks
            }
            try:
                while pending:
                    finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        for i, translated in future.result():
                            results[i] = translated
                            if on_progress is not None:
                                on_progress(i)
            except BaseException:
                for future in pending:
                    future.cancel()
                raise
        return results
