# -*- coding: utf-8 -*-
"""Определение доступной памяти (macOS) и выбор уровня параллелизма перевода.

Каждый параллельный слот Ollama резервирует свой KV-кэш контекста, поэтому
число одновременных запросов ограничивается свободной памятью, чтобы не
загнать машину в своп.
"""

import re
import subprocess
from typing import Optional

# Системный резерв, чтобы не съедать память в ноль
RESERVE_GB = 2.0
# KV-кэш одного слота при типовом контексте 4–8K токенов
PER_SLOT_GB = 0.75
MAX_PARALLEL = 8
# Дефолт, если память определить не удалось (поведение этапа 1)
FALLBACK_PARALLEL = 4

_PAGE_SIZE_RE = re.compile(r"page size of (\d+) bytes")
_PAGES_RE = re.compile(r"^Pages ([a-z][a-z -]*):\s+(\d+)\.", re.MULTILINE)


def parse_vm_stat(text: str) -> Optional[float]:
    """Доступная память в ГиБ из вывода vm_stat: free + inactive + purgeable."""
    page_size_match = _PAGE_SIZE_RE.search(text)
    if not page_size_match:
        return None
    page_size = int(page_size_match.group(1))
    pages = {name: int(count) for name, count in _PAGES_RE.findall(text)}
    if "free" not in pages:
        return None
    available_pages = (pages.get("free", 0) + pages.get("inactive", 0)
                       + pages.get("purgeable", 0))
    return available_pages * page_size / 2**30


def available_memory_gb() -> Optional[float]:
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True,
                             timeout=5, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_vm_stat(out)


def recommended_parallelism(available_gb: Optional[float],
                            unloaded_model_gb: float = 0.0) -> int:
    """Число параллельных запросов перевода по бюджету памяти.

    unloaded_model_gb — размер модели, которую Ollama ещё только предстоит
    загрузить в память (0, если она уже загружена или размер неизвестен).
    """
    if available_gb is None:
        return FALLBACK_PARALLEL
    budget = available_gb - RESERVE_GB - unloaded_model_gb
    return max(1, min(MAX_PARALLEL, int(budget / PER_SLOT_GB)))
