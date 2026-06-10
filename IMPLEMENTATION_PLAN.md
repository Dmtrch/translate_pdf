# План реализации: MacPDF Translator (локальный перевод PDF через Ollama)

## Контекст

По PRD (`start_prompt.md`) нужно создать macOS-приложение для перевода PDF с сохранением вёрстки (текст заменяется в тех же bounding box, изображения и таблицы не сдвигаются). Перевод — локально через Ollama (localhost:11434), OCR сканов — Apple Vision.

**Принятые решения (подтверждены пользователем):**
- Архитектура: **SwiftUI UI + Python-движок (PyMuPDF)**, движок запускается как subprocess.
- Python-окружение: **venv в папке проекта** (системный python3 + venv с зависимостями).
- Референс: `/Users/dim/vscodeproject/pdf->word/converter.py` — оттуда переиспользуем: детекцию сканированных страниц (`is_page_scanned`), OCR через Apple Vision/pyobjc (`_ocr_page_with_vision`), извлечение блоков/таблиц/картинок с bbox (`page.get_text("dict")`, `find_tables`, `get_image_info`), геометрическую сортировку (`sort_elements`).

**Среда подтверждена:** Ollama запущен на 11434, модели доступны (bob-hymt, qwen2.5, gemma3, minicpm-v и др.).

## Архитектура

```
SwiftUI App (MacPDFTranslator.app)
  │  Process + JSON-lines по stdout (события прогресса/ETA/ошибок)
  ▼
engine/translate_pdf.py (venv: pymupdf, pyobjc-framework-Vision, requests)
  ├─ 1. Парсинг PDF / классификация страниц (текст vs скан)
  ├─ 2. OCR сканов: Apple Vision (с координатами boundingBox)
  ├─ 3. Перевод блоков: HTTP → Ollama localhost:11434 (/api/chat)
  └─ 4. Сборка PDF: redaction-замена текста в исходных bbox,
        insert_textbox с автоподбором шрифта (до 6pt), картинки/сетка таблиц не трогаются
```

**Протокол Swift ↔ Python (JSON-lines в stdout):**
```json
{"event":"stage_start","stage":"parse|ocr|translate|render"}
{"event":"progress","stage":"ocr","done":3,"total":10,"eta_sec":25}
{"event":"progress","stage":"translate","done":12,"total":80,"eta_sec":140,"tps":42.5}
{"event":"done","output":"/path/out.pdf"}
{"event":"error","code":"ollama_unreachable","message":"..."}
```

## Структура проекта

```
translate_pdf/
├── IMPLEMENTATION_PLAN.md          # этот план с чекбоксами
├── engine/
│   ├── requirements.txt            # pymupdf, pyobjc-framework-Vision, requests
│   ├── translate_pdf.py            # CLI-точка входа (argparse: input, output, src-lang, dst-lang, model)
│   ├── extractor.py                # извлечение структуры (блоки/таблицы/картинки/bbox)
│   ├── ocr.py                      # Apple Vision OCR с координатами
│   ├── translator.py               # клиент Ollama + батчинг + расчёт TPS/ETA
│   ├── renderer.py                 # сборка итогового PDF (redaction + insert_textbox)
│   └── tests/                      # pytest + тестовые PDF-фикстуры
├── MacPDFTranslator/               # Xcode-проект (SwiftUI, macOS 14+)
│   ├── MacPDFTranslatorApp.swift
│   ├── ContentView.swift           # главный экран по wireframe из PRD
│   ├── TranslationViewModel.swift  # @Observable: состояние, прогресс, ETA
│   ├── EngineRunner.swift          # Process + парсинг JSON-lines
│   └── OllamaClient.swift          # GET /api/tags: статус + список моделей
└── scripts/
    ├── setup_env.sh                # создание venv + pip install
    └── make_fixtures.py            # генерация тестовых PDF (текст+таблицы+картинки, скан)
```

---

## Этапы работ

### Этап 0 — Каркас проекта (последовательно, база для всего остального)

- [x] 0.1. Создать `IMPLEMENTATION_PLAN.md` в корне проекта (копия этого плана с чекбоксами)
- [x] 0.2. Создать структуру папок `engine/`, `scripts/`, venv + `requirements.txt` (`scripts/setup_env.sh`) — Python 3.14.4, pymupdf 1.27.2.3, pyobjc-Vision 12.2
- [x] 0.3. Создать SwiftUI-проект `MacPDFTranslator` (macOS 14+). *Отклонение от плана: вместо `.xcodeproj` используется Swift Package (`Package.swift`) — xcodegen в системе нет, а SPM-пакет Xcode открывает нативно; `swift build` и `swift test` проходят*
- [x] 0.4. Скрипт `scripts/make_fixtures.py`: сгенерировать тестовые PDF — (а) текстовый с таблицей и картинкой, (б) «скан» (страницы-изображения) → verify: `fixtures/text.pdf` и `fixtures/scan.pdf` созданы, самопроверки пройдены (текстовый слой/картинки на месте, у «скана» текстового слоя нет)

### ⬇ После этапа 0 два трека идут ПАРАЛЛЕЛЬНО

### Этап 1 — Трек A: Python-движок (параллельно с Этапом 2)

- [x] A1. `extractor.py`: извлечение структуры страницы — текстовые блоки/спаны с bbox, шрифтом и размером; таблицы (`find_tables`, bbox ячеек); картинки (bbox). Перенести и адаптировать логику из `pdf->word/converter.py` (фильтрация блоков внутри таблиц, `is_page_scanned`) → verify: pytest на фикстуре (а) — все блоки/таблица/картинка найдены с координатами
- [x] A2. `ocr.py`: Apple Vision OCR через pyobjc, **с координатами** (`VNRecognizedTextObservation.boundingBox`, перевод нормализованных координат Vision в координаты страницы PDF; в референсе координаты не извлекались — это доработка) → verify: pytest на фикстуре (б) — текст распознан, bbox в пределах страницы
- [x] A3. `translator.py`: клиент Ollama `/api/chat` (system-промпт «переведи, верни только перевод», поддержка авто-детекта языка), последовательный перевод блоков, замер tokens/sec и расчёт ETA, обработка недоступности сервера (`ollama_unreachable`) → verify: pytest с реальной Ollama — блок переведён, при выключенном порте корректная ошибка
- [x] A4. `renderer.py`: сборка итогового PDF:
  - текстовые PDF: `page.add_redact_annot(bbox)` + `apply_redactions(images=PDF_REDACT_IMAGE_NONE)` (картинки не затираются), затем `insert_textbox` с циклом уменьшения fontsize до 6pt, подбор CJK/кириллических шрифтов под целевой язык
  - таблицы: замена текста по bbox ячеек, сетка остаётся нетронутой
  - сканы: белая подложка по bbox строки поверх изображения + переведённый текст
  → verify: pytest — выходной PDF открывается, текст заменён, картинка на месте (попиксельное сравнение области картинки)
- [x] A5. `translate_pdf.py`: CLI-оркестратор этапов 1→4, эмиссия JSON-lines прогресса/ETA в stdout, очистка кэша страниц (память) → verify: запуск из терминала на обеих фикстурах даёт корректный переведённый PDF и валидный поток JSON

### Этап 2 — Трек B: SwiftUI-приложение (параллельно с Этапом 1)

- [x] B1. `ContentView.swift`: макет по wireframe PRD — поля исходного/выходного файла (NSOpenPanel/NSSavePanel, фильтр .pdf, Drag-and-Drop, автоимя `_translated.pdf`), дропдауны языков (8 языков + Auto-detect), кнопка «Начать перевод», два прогресс-бара с ETA, секция настроек Ollama. Тёмная/светлая темы → verify: сборка, ручная проверка выбора файлов и DnD
- [x] B2. `OllamaClient.swift`: GET `localhost:11434/api/tags` → статус «Подключено/Ошибка» и наполнение дропдауна моделей; плашка «Ошибка подключения к Ollama…» при недоступности → verify: с запущенной и остановленной Ollama
- [x] B3. `EngineRunner.swift`: запуск `engine/.venv/bin/python translate_pdf.py …` через `Process`, асинхронное чтение stdout, парсинг JSON-lines в события; кнопка отмены (terminate) → verify: unit-тест на парсинг событий + запуск с mock-скриптом, печатающим тестовые события
- [x] B4. `TranslationViewModel.swift`: связка B1+B2+B3 — состояния (idle/parsing/ocr/translating/done/error), форматирование ETA «ММ:СС», блокировка UI во время работы → verify: сборка, прогон с mock-скриптом

### Этап 3 — Интеграция (после A5 и B4)

- [ ] 3.1. Сквозной прогон: приложение → движок → переведённый PDF для фикстуры (а) и (б) — *ручная проверка пользователем: `cd MacPDFTranslator && swift run`; конвейер CLI и mock-прогон EngineRunner проверены автоматически*
- [x] 3.2. Обработка ошибок end-to-end: Ollama выключена (плашка), битый PDF, нет прав на запись выходного файла
- [x] 3.3. Точность ETA: сравнить прогноз и факт на 10-страничном документе (цель — погрешность ≤15%)

### Этап 4 — Приёмочное тестирование (по критериям PRD)

- [x] 4.1. Тест 1: текстовый PDF 10 стр., 3 таблицы, 5 картинок — картинки на месте, сетка таблиц не съехала, ETA ±15%
- [x] 4.2. Тест 2: сканированный PDF — OCR, перевод, наложение с сохранением структуры
- [ ] 4.3. Тест 3: автономия — перевод при отключённом интернете — *ручная проверка: код обращается только к localhost:11434, внешних запросов нет*
- [x] 4.4. Память: перевод объёмного PDF без неконтролируемого роста RAM (постраничная обработка, освобождение pixmap)

## Карта параллелизма

| Параллельно | Задачи |
|---|---|
| Волна 1 (после 0.2/0.3) | **Трек A** (A1→A2→A3→A4→A5) ∥ **Трек B** (B1→B2→B3→B4) |
| Внутри трека A | A2 (OCR) ∥ A3 (Ollama-клиент) — независимы после A1 |
| Внутри трека B | B2 (OllamaClient) ∥ B3 (EngineRunner) — независимы после B1 |
| Последовательно | Этап 0 → волна 1 → Этап 3 → Этап 4 |

## Верификация (итог)

1. `pytest engine/tests/` — все юнит-тесты движка зелёные.
2. CLI: `engine/.venv/bin/python engine/translate_pdf.py fixtures/text.pdf -o out.pdf --to en --model qwen2.5` — PDF создан, вёрстка сохранена (визуальная проверка).
3. Сборка приложения в Xcode (`xcodebuild`), ручной сквозной прогон по обеим фикстурам.
4. Приёмочные тесты 4.1–4.3 из PRD.

## Риски

- **Шрифты для CJK/кириллицы**: встроенные шрифты PyMuPDF не покрывают все 8 языков — потребуется подключение системных шрифтов macOS (`insert_font` с файлом, напр. PingFang/Helvetica). Закладывается в A4.
- **Качество перевода маленьких блоков** (заголовки ячеек таблиц): переводить с контекстом, но вставлять по-блочно.
- **App Sandbox**: запуск python-subprocess из песочницы может потребовать отключения sandbox для dev-сборки (личное использование — допустимо).
