# План: сборка DMG для MacPDF Translator

Статус: не начато. Создан 2026-06-11. Выполнение отложено.

## Цель

Упаковать приложение в распространяемый `MacPDFTranslator.dmg` с настоящим
`.app`-бандлом вместо текущего «голого» бинарника, запускаемого через `run.sh`.

## Текущее состояние (что важно учесть)

- Приложение — SwiftPM-executable без бандла: `MacPDFTranslator/.build/release/MacPDFTranslator`.
- Движок ищется через `EngineLocator` (`EngineRunner.swift:43`): поиск
  `engine/translate_pdf.py` + `engine/.venv/bin/python` от cwd и bundleURL
  вверх по дереву (до 6 уровней).
- venv непереносим между машинами: абсолютные пути в `pyvenv.cfg`,
  симлинк на системный python.
- Зависимость от Ollama (localhost:11434) остаётся внешней в любом варианте.
- Для бандл-приложения уже был фикс клавиатурного фокуса (bundleless-проблема);
  после перехода на .app проверить, что костыль не мешает.

## Этап 1 — DMG «для себя» (минимальный рабочий вариант)

1. **Скрипт сборки бандла** — новый `scripts/make_app.sh`:
   - `swift build -c release`;
   - собрать структуру `MacPDFTranslator.app/Contents/{MacOS,Resources}`;
   - бинарник → `Contents/MacOS/`;
   - написать `Contents/Info.plist` (CFBundleIdentifier, CFBundleName,
     LSMinimumSystemVersion, NSHighResolutionCapable);
   - `engine/` (py-файлы + requirements.txt, без `.venv`, без кэшей)
     → `Contents/Resources/engine/`.

2. **Доработка `EngineLocator`** (`EngineRunner.swift`):
   - добавить кандидата `Bundle.main.resourceURL` (Contents/Resources);
   - сохранить текущий поиск по дереву для dev-запуска из терминала.

3. **Размещение venv вне бандла** (чтобы .app можно было копировать):
   - целевой путь: `~/Library/Application Support/MacPDFTranslator/venv`;
   - `EngineLocator` проверяет его как кандидата python;
   - при отсутствии — приложение показывает понятную ошибку с командой
     установки (этап 1) или создаёт venv само (этап 2, см. ниже).

4. **Скрипт упаковки DMG** — новый `scripts/make_dmg.sh`:
   - `hdiutil create -volname "MacPDF Translator" -srcfolder dist/ -ov -format UDZO MacPDFTranslator.dmg`;
   - в `dist/` положить `.app` и симлинк на `/Applications`.

5. **Проверка**:
   - смонтировать DMG, перетащить .app в /Applications;
   - запуск из Finder: окно открывается, клавиатура работает;
   - перевод тестового PDF проходит end-to-end;
   - запуск со смонтированного DMG (read-only том) не падает.

## Этап 2 — автонастройка окружения при первом запуске

6. **First-run setup в Swift**: если venv в Application Support отсутствует —
   диалог «Первый запуск: установка компонентов», затем
   `python3 -m venv` + `pip install -r requirements.txt` из Resources
   с прогрессом; обработка отсутствия python3/Xcode CLT.

7. **Проверка Ollama в UI**: понятное сообщение, если Ollama не запущена
   или модель не скачана (сейчас частично есть), с командами установки.

## Этап 3 — распространение на другие Mac (опционально)

8. **Иконка**: нарисовать/сгенерировать `.icns`, добавить в Resources
   и CFBundleIconFile.
9. **Подпись и нотаризация** (нужна учётка Apple Developer, $99/год):
   - `codesign --deep --options runtime`;
   - `notarytool submit` + `stapler staple`;
   - без этого на чужих Mac: правый клик → «Открыть» или
     `xattr -d com.apple.quarantine`.
10. **README**: раздел «Установка из DMG» (Ollama, модель, первый запуск).

## Файлы, которые будут затронуты

| Файл | Действие |
|---|---|
| `scripts/make_app.sh` | создать |
| `scripts/make_dmg.sh` | создать |
| `MacPDFTranslator/Sources/MacPDFTranslator/EngineRunner.swift` | изменить (EngineLocator) |
| `MacPDFTranslator/Sources/MacPDFTranslator/*` (first-run, этап 2) | изменить |
| `README.md` | дополнить |

## Открытые вопросы (решить перед началом)

- Нужен ли этап 3 вообще, или DMG только для личного переноса между своими Mac?
- Иконка: есть ли готовая, или генерируем?
- Минимальная версия macOS (сейчас неявно — та, на которой собрано; зафиксировать в Package.swift/Info.plist).
