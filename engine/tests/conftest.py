import os
import sys

import pytest

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(ENGINE_DIR)
FIXTURES_DIR = os.path.join(PROJECT_DIR, "fixtures")

sys.path.insert(0, ENGINE_DIR)


@pytest.fixture
def text_pdf() -> str:
    return os.path.join(FIXTURES_DIR, "text.pdf")


@pytest.fixture
def scan_pdf() -> str:
    return os.path.join(FIXTURES_DIR, "scan.pdf")


def ollama_available() -> bool:
    import requests
    try:
        requests.get("http://localhost:11434/api/tags", timeout=2)
        return True
    except requests.exceptions.RequestException:
        return False
