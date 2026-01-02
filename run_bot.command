#!/bin/bash

cd "$(dirname "$0")"

# Установка переменных окружения
export API_TOKEN="7334437140:AAG8GYbJFcwFFj4YfpGsFKrLYBO6VlbWkRE"
export PAYMENT_PROVIDER_TOKEN="390540012:LIVE:85749"

# Конфигурация ЮKassa API
# ⚠️ ВАЖНО: Замените значения на реальные из личного кабинета ЮKassa!
# Инструкция: см. файл КАК_ПОЛУЧИТЬ_КЛЮЧИ_ЮКАССА.md
export YOOKASSA_SHOP_ID="1231094"  # Идентификатор магазина (из ЛК ЮKassa)
export YOOKASSA_SECRET_KEY="live_G7u2yfiQfxt-YSwsPwG3iJsAyBz4sVENqfqvGQVosME"  # ⚠️ УКАЖИТЕ ПОЛНЫЙ СЕКРЕТНЫЙ КЛЮЧ из ЛК ЮKassa (начинается с live_ или test_)
export YOOKASSA_GATEWAY_ID=""  # Опционально, если есть суб-аккаунт
export WEBHOOK_URL=""  # URL для вебхуков (например, через ngrok: https://xxxx.ngrok.io)

PYTHON_EXE="./venv/bin/python3"

# Проверка наличия Python
if [ ! -f "$PYTHON_EXE" ]; then
    echo "❌ Ошибка: Python не найден в $PYTHON_EXE"
    echo "Проверьте, что виртуальное окружение создано правильно."
    read
    exit 1
fi

# Проверка наличия файла бота
if [ ! -f "machata_bot.py" ]; then
    echo "❌ Ошибка: файл machata_bot.py не найден"
    read
    exit 1
fi

echo "🚀 Запуск бота MACHATA studio..."
echo ""

# Запуск бота
$PYTHON_EXE machata_bot.py

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Бот остановлен нормально"
else
    echo "❌ Бот завершился с ошибкой (код: $EXIT_CODE)"
fi

echo ""
echo "Нажми Enter, чтобы закрыть окно..."
read

