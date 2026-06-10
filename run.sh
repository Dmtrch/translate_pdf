#!/bin/bash
# Простой запуск MacPDF Translator: ./run.sh
# При первом запуске сам создаёт python-окружение и собирает приложение.
set -euo pipefail
cd "$(dirname "$0")"

# 1. Окружение движка (venv с PyMuPDF/Vision) — создаётся один раз
if [ ! -x engine/.venv/bin/python ]; then
    echo "[*] Первый запуск: создаю окружение движка…"
    scripts/setup_env.sh
fi

# 2. Предупреждение, если Ollama не запущена (приложение покажет статус, но так нагляднее)
if ! curl -s --max-time 2 http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[!] Ollama не отвечает на localhost:11434 — запустите её командой: ollama serve"
else
    # 2a. Если модель была загружена при нехватке памяти, Ollama урезает её
    # до одного слота (-np 1) — перевод идёт последовательно и медленно.
    # Выгружаем такие модели: следующий запрос перезагрузит их с полным -np.
    if pgrep -f "llama-server" > /dev/null && \
       ps -o command= -p "$(pgrep -f llama-server | head -1)" | grep -q -- "-np 1 "; then
        echo "[!] Модель загружена в урезанном режиме (1 слот) — перезагружаю…"
        ollama ps | awk 'NR>1 {print $1}' | while read -r m; do
            [ -n "$m" ] && ollama stop "$m"
        done
    fi
fi

# 3. Сборка и запуск приложения
echo "[*] Сборка приложения…"
(cd MacPDFTranslator && swift build -c release 2>&1 | tail -1)
echo "[*] Запуск MacPDF Translator"
exec MacPDFTranslator/.build/release/MacPDFTranslator
