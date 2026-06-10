# -*- coding: utf-8 -*-
import sys

import pytest

from sysinfo import available_memory_gb, parse_vm_stat, recommended_parallelism

# Реальный формат вывода vm_stat (macOS), сокращён до значимых строк
VM_STAT_SAMPLE = """\
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                              100000.
Pages active:                            500000.
Pages inactive:                          200000.
Pages speculative:                        50000.
Pages throttled:                              0.
Pages wired down:                        150000.
Pages purgeable:                          25000.
"Translation faults":                 123456789.
Pages copy-on-write:                    1234567.
"""


def test_parse_vm_stat_sample():
    # (free 100000 + inactive 200000 + purgeable 25000) × 16384 байт
    expected_gb = (100000 + 200000 + 25000) * 16384 / 2**30
    assert parse_vm_stat(VM_STAT_SAMPLE) == pytest.approx(expected_gb, rel=1e-6)


def test_parse_vm_stat_garbage():
    assert parse_vm_stat("нет такого вывода") is None
    assert parse_vm_stat("") is None


@pytest.mark.skipif(sys.platform != "darwin", reason="vm_stat есть только на macOS")
def test_available_memory_gb_live():
    value = available_memory_gb()
    assert value is not None and 0 < value < 1024


def test_recommended_parallelism_table():
    # Много памяти → потолок 8
    assert recommended_parallelism(32.0) == 8
    # 8 ГБ свободно: (8 - 2) / 0.75 = 8
    assert recommended_parallelism(8.0) == 8
    # 5 ГБ: (5 - 2) / 0.75 = 4
    assert recommended_parallelism(5.0) == 4
    # Мало памяти → минимум 1
    assert recommended_parallelism(2.0) == 1
    assert recommended_parallelism(0.5) == 1


def test_recommended_parallelism_unloaded_model():
    # Модель ещё не в памяти: её размер вычитается из бюджета
    # (10 - 2 - 5) / 0.75 = 4
    assert recommended_parallelism(10.0, unloaded_model_gb=5.0) == 4
    # Модель не влезает → всё равно минимум 1 (Ollama сам разрулит выгрузку)
    assert recommended_parallelism(4.0, unloaded_model_gb=8.0) == 1


def test_recommended_parallelism_unknown_memory():
    # Память определить не удалось → консервативный дефолт этапа 1
    assert recommended_parallelism(None) == 4
