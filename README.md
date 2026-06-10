# MacPDF Translator

Офлайн-перевод PDF-документов с сохранением вёрстки. Работает локально через Ollama — тексты не покидают машину.

## Как это работает

- Python-движок (`engine/`) извлекает текст из PDF, переводит его через локальную LLM и собирает новый PDF с сохранением шрифтов, изображений и раскладки страниц.
- macOS-приложение (`MacPDFTranslator/`) — нативный SwiftUI-интерфейс, запускающий движок как подпроцесс и отображающий прогресс перевода.

## Требования

- macOS 13+
- [Ollama](https://ollama.com) — для запуска локальной LLM
- Python 3.11+
- Swift 5.9+ (входит в Xcode Command Line Tools)

## Установка моделей Ollama

Переводчик работает с любой моделью из Ollama. По умолчанию используется `bob-hymt:latest`.

### Рекомендуемые модели

| Модель | Команда установки | Размер | Качество перевода |
|---|---|---|---|
| `bob-hymt:latest` | `ollama pull bob-hymt` | ~2 GB | Хорошее (оптимизирована под перевод) |
| `gemma3:4b` | `ollama pull gemma3:4b` | ~3 GB | Хорошее |
| `llama3.2:3b` | `ollama pull llama3.2:3b` | ~2 GB | Среднее |
| `qwen2.5:7b` | `ollama pull qwen2.5:7b` | ~5 GB | Отличное |

Ollama хранит модели в `~/.ollama/models/`. Место на диске: от 2 до 10 ГБ в зависимости от выбранной модели.

### Запуск Ollama

```bash
ollama serve
```

Ollama должна быть запущена перед стартом приложения. Проверить доступность:

```bash
curl http://localhost:11434/api/tags
```

## Быстрый запуск

```bash
git clone https://github.com/Dmtrch/translate_pdf.git
cd translate_pdf
./run.sh
```

При первом запуске `run.sh` автоматически:
1. Создаёт Python-окружение (`engine/.venv`) и устанавливает зависимости.
2. Собирает Swift-приложение.
3. Запускает MacPDF Translator.

## Использование CLI (без GUI)

```bash
cd engine
.venv/bin/python translate_pdf.py input.pdf -o output.pdf --to ru
```

Опции:

```
  --to ru              Язык перевода (ru, en, de, fr, es, it, zh, ja)
  --from en            Язык оригинала (по умолчанию: auto)
  --model MODEL        Модель Ollama (по умолчанию: bob-hymt:latest)
  --ollama-url URL     Адрес Ollama (по умолчанию: http://localhost:11434)
  --parallel N         Число параллельных запросов (по умолчанию: 4)
```

Пример с другой моделью:

```bash
.venv/bin/python translate_pdf.py paper.pdf -o paper_ru.pdf --to ru --model qwen2.5:7b
```

## Структура проекта

```
translate_pdf/
├── run.sh                  # Точка входа: сборка + запуск
├── engine/                 # Python-движок
│   ├── translate_pdf.py    # CLI-оркестратор (JSON-протокол для Swift)
│   ├── translator.py       # Клиент Ollama
│   ├── extractor.py        # Разбор страниц PDF
│   ├── ocr.py              # OCR через macOS Vision
│   ├── renderer.py         # Сборка переведённого PDF
│   ├── sysinfo.py          # Авто-подбор параллелизма по RAM
│   └── requirements.txt
├── MacPDFTranslator/       # SwiftUI-приложение
│   ├── Sources/
│   └── Package.swift
└── scripts/
    └── setup_env.sh        # Создание Python-окружения
```

## Тесты

```bash
cd engine
.venv/bin/python -m pytest tests/ -v
```

## Производительность

На MacBook с Apple Silicon при `--parallel 4`:

- Холодный старт модели: ~5 с
- Тёплый старт (модель уже в памяти): ~1 с
- Скорость перевода: ~10 страниц/мин (зависит от модели и объёма текста)

Для ускорения увеличьте `OLLAMA_NUM_PARALLEL` на стороне сервера:

```bash
OLLAMA_NUM_PARALLEL=4 ollama serve
```
