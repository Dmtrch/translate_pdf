# -*- coding: utf-8 -*-
"""Клиент Ollama для перевода текстовых блоков.

Работает только с localhost — тексты не покидают машину пользователя.
Накапливает статистику генерации (eval_count/eval_duration) для расчёта
скорости в токенах/сек, используемой в ETA.
"""

import re
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, List, Optional

import requests

DEFAULT_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 600  # сек на один блок; большие модели бывают медленными

LANG_NAMES = {
    "en": "English",
    "ru": "Russian",
    "zh": "Chinese",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "es": "Spanish",
    "ja": "Japanese",
}

# Размышления reasoning-моделей (deepseek-r1, qwen3 и т.п.) вырезаем из ответа
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class OllamaError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class OllamaTranslator:
    def __init__(self, model: str, url: str = DEFAULT_URL,
                 timeout: float = DEFAULT_TIMEOUT):
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.total_eval_count = 0
        self.total_eval_duration_ns = 0
        self._stats_lock = threading.Lock()
        self._tls = threading.local()  # своя HTTP-сессия на поток

    def _session(self) -> requests.Session:
        session = getattr(self._tls, "session", None)
        if session is None:
            session = requests.Session()
            self._tls.session = session
        return session

    # -- подключение -------------------------------------------------------

    def list_models(self) -> List[str]:
        try:
            resp = requests.get(f"{self.url}/api/tags", timeout=5)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise OllamaError(
                "ollama_unreachable",
                "Ошибка подключения к Ollama. Убедитесь, что сервис запущен на порту 11434.",
            )
        except requests.exceptions.RequestException as e:
            raise OllamaError("ollama_error", f"Ошибка Ollama API: {e}")
        return [m["name"] for m in resp.json().get("models", [])]

    def check(self) -> None:
        """Проверяет доступность сервера и наличие выбранной модели."""
        models = self.list_models()
        if self.model not in models:
            raise OllamaError(
                "model_not_found",
                f"Модель «{self.model}» не найдена в Ollama. Доступны: {', '.join(models)}",
            )

    def unloaded_model_size_gb(self) -> float:
        """Размер модели (ГиБ), если её ещё предстоит загрузить в память.

        0.0 — если модель уже загружена (/api/ps), размер неизвестен или
        сервер недоступен: тогда вычитать из бюджета памяти нечего.
        """
        try:
            ps = self._session().get(f"{self.url}/api/ps", timeout=5)
            ps.raise_for_status()
            if any(m.get("name") == self.model
                   for m in ps.json().get("models", [])):
                return 0.0
            tags = self._session().get(f"{self.url}/api/tags", timeout=5)
            tags.raise_for_status()
            for m in tags.json().get("models", []):
                if m.get("name") == self.model:
                    # Размер GGUF на диске ≈ объём в памяти после загрузки
                    return m.get("size", 0) / 2**30
        except requests.exceptions.RequestException:
            pass
        return 0.0

    # -- перевод ------------------------------------------------------------

    def _system_prompt(self, src: str, dst: str) -> str:
        dst_name = LANG_NAMES.get(dst, dst)
        if src == "auto":
            src_part = "the source language (detect it automatically)"
        else:
            src_part = LANG_NAMES.get(src, src)
        return (
            f"You are a professional translator. Translate the user's text "
            f"from {src_part} into {dst_name}. Preserve numbers, units and "
            f"proper names. Output ONLY the translated text without any "
            f"explanations, comments or quotes."
        )

    def translate(self, text: str, src: str = "auto", dst: str = "en") -> str:
        if not text.strip():
            return text
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": self._system_prompt(src, dst)},
                {"role": "user", "content": text},
            ],
        }
        try:
            resp = self._session().post(f"{self.url}/api/chat", json=payload,
                                        timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise OllamaError(
                "ollama_unreachable",
                "Ошибка подключения к Ollama. Убедитесь, что сервис запущен на порту 11434.",
            )
        except requests.exceptions.RequestException as e:
            raise OllamaError("ollama_error", f"Ошибка Ollama API: {e}")

        data = resp.json()
        with self._stats_lock:
            self.total_eval_count += data.get("eval_count", 0)
            self.total_eval_duration_ns += data.get("eval_duration", 0)

        result = data.get("message", {}).get("content", "")
        result = _THINK_RE.sub("", result).strip()
        return result or text

    def translate_batch(self, texts: List[str], src: str = "auto",
                        dst: str = "en", concurrency: int = 4,
                        on_progress: Optional[Callable[[int], None]] = None,
                        ) -> List[str]:
        """Переводит список текстов параллельно, сохраняя исходный порядок.

        Сервер Ollama батчит одновременные запросы при OLLAMA_NUM_PARALLEL > 1.
        on_progress(index) вызывается из вызывающего потока по мере завершения
        переводов (порядок завершения произвольный). Первая ошибка отменяет
        оставшиеся задачи и пробрасывается наверх.
        """
        if not texts:
            return []
        results: List[Optional[str]] = [None] * len(texts)
        concurrency = max(1, min(concurrency, len(texts)))
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            future_index = {
                pool.submit(self.translate, text, src, dst): i
                for i, text in enumerate(texts)
            }
            pending = set(future_index)
            try:
                while pending:
                    # FIRST_COMPLETED: просыпаемся после каждого готового
                    # перевода, чтобы on_progress шёл по мере выполнения
                    finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        i = future_index[future]
                        results[i] = future.result()  # пробрасывает OllamaError
                        if on_progress is not None:
                            on_progress(i)
            except BaseException:
                for future in pending:
                    future.cancel()
                raise
        return results  # type: ignore[return-value]  # все элементы заполнены

    # -- статистика для ETA ---------------------------------------------------

    def tokens_per_second(self) -> Optional[float]:
        if self.total_eval_duration_ns <= 0:
            return None
        return self.total_eval_count / (self.total_eval_duration_ns / 1e9)
