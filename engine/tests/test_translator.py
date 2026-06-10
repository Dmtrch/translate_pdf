# -*- coding: utf-8 -*-
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import ollama_available
from translator import OllamaError, OllamaTranslator

MODEL = "bob-hymt:latest"

needs_ollama = pytest.mark.skipif(not ollama_available(),
                                  reason="Ollama не запущена на 11434")


@needs_ollama
def test_translate_en_ru():
    tr = OllamaTranslator(MODEL)
    tr.check()
    result = tr.translate("Good morning, dear friends!", src="en", dst="ru")
    assert result and result != "Good morning, dear friends!"
    # Ответ содержит кириллицу
    assert any("а" <= ch.lower() <= "я" for ch in result)
    assert tr.tokens_per_second() > 0


@needs_ollama
def test_model_not_found():
    tr = OllamaTranslator("no-such-model:v0")
    with pytest.raises(OllamaError) as exc:
        tr.check()
    assert exc.value.code == "model_not_found"


def test_unreachable_server():
    tr = OllamaTranslator(MODEL, url="http://localhost:59999")
    with pytest.raises(OllamaError) as exc:
        tr.check()
    assert exc.value.code == "ollama_unreachable"


def test_think_block_stripped():
    from translator import _THINK_RE
    raw = "<think>reasoning here</think>Привет!"
    assert _THINK_RE.sub("", raw).strip() == "Привет!"


# --- параллельный батч (mock-сервер вместо живой Ollama) --------------------

class _MockOllamaHandler(BaseHTTPRequestHandler):
    """Эмулирует /api/tags и /api/chat. Перевод = "TR:<исходный текст>".

    Разная задержка ответа (по длине текста) перемешивает порядок завершения,
    чтобы проверить восстановление исходного порядка результатов.
    Текст "FAIL" вызывает ответ 500.
    """

    def log_message(self, *args):  # тишина в выводе pytest
        pass

    def do_GET(self):
        if self.path == "/api/ps":
            models = getattr(self.server, "loaded_models", [])
        else:  # /api/tags
            models = [{"name": "mock-model", "size": 8 * 2**30}]
        body = json.dumps({"models": models}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        text = payload["messages"][1]["content"]
        if text == "FAIL":
            self.send_response(500)
            self.end_headers()
            return
        time.sleep((len(text) % 3) * 0.02)
        body = json.dumps({
            "message": {"content": f"TR:{text}"},
            "eval_count": 5,
            "eval_duration": 1_000_000,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def mock_server_instance():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockOllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


@pytest.fixture
def mock_server(mock_server_instance):
    return f"http://127.0.0.1:{mock_server_instance.server_address[1]}"


def test_translate_batch_preserves_order(mock_server):
    tr = OllamaTranslator("mock-model", url=mock_server)
    texts = [f"text-{i:02d}-{'x' * (i % 5)}" for i in range(12)]
    results = tr.translate_batch(texts, src="en", dst="ru", concurrency=4)
    assert results == [f"TR:{t}" for t in texts]


def test_translate_batch_aggregates_stats(mock_server):
    tr = OllamaTranslator("mock-model", url=mock_server)
    tr.translate_batch([f"t{i}" for i in range(10)], concurrency=4)
    assert tr.total_eval_count == 50  # 10 запросов × eval_count=5
    assert tr.tokens_per_second() > 0


def test_translate_batch_progress_callback(mock_server):
    tr = OllamaTranslator("mock-model", url=mock_server)
    seen = []
    tr.translate_batch([f"t{i}" for i in range(8)], concurrency=4,
                       on_progress=seen.append)
    # Колбэк вызван по разу на каждый текст, индексы — перестановка 0..7
    assert sorted(seen) == list(range(8))


def test_translate_batch_progress_is_incremental(mock_server):
    # Прогресс должен приходить по мере завершения переводов, а не пачкой
    # в конце (wait с FIRST_EXCEPTION без ошибок ждёт все задачи разом).
    tr = OllamaTranslator("mock-model", url=mock_server)
    progress_seen = threading.Event()

    def fake_translate(text, src="auto", dst="en"):
        if text == "second":
            assert progress_seen.wait(timeout=5), \
                "on_progress не вызван до завершения всех задач"
        return f"TR:{text}"

    tr.translate = fake_translate
    results = tr.translate_batch(["first", "second"], concurrency=1,
                                 on_progress=lambda i: progress_seen.set())
    assert results == ["TR:first", "TR:second"]


def test_translate_batch_propagates_error(mock_server):
    tr = OllamaTranslator("mock-model", url=mock_server)
    texts = ["ok-1", "FAIL", "ok-2", "ok-3"]
    with pytest.raises(OllamaError):
        tr.translate_batch(texts, concurrency=2)


def test_translate_batch_empty_list(mock_server):
    tr = OllamaTranslator("mock-model", url=mock_server)
    assert tr.translate_batch([]) == []


def test_unloaded_model_size_when_not_in_memory(mock_server):
    # Модели нет в /api/ps → берём размер с диска из /api/tags (8 ГиБ в моке)
    tr = OllamaTranslator("mock-model", url=mock_server)
    assert tr.unloaded_model_size_gb() == pytest.approx(8.0)


def test_unloaded_model_size_when_loaded(mock_server, mock_server_instance):
    # Модель уже в памяти → вычитать нечего
    mock_server_instance.loaded_models = [{"name": "mock-model"}]
    tr = OllamaTranslator("mock-model", url=mock_server)
    assert tr.unloaded_model_size_gb() == 0.0


def test_unloaded_model_size_server_down():
    tr = OllamaTranslator("mock-model", url="http://localhost:59999")
    assert tr.unloaded_model_size_gb() == 0.0
