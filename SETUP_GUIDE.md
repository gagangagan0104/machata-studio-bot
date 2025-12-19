# 🚀 Руководство по установке MACHATA Bot

Полное пошаговое руководство для начинающих.

## Шаг 1: Установка Python

### Windows
1. Скачай Python с [python.org](https://www.python.org/downloads/)
2. Запусти установщик
3. ✅ **Обязательно** отметь "Add Python to PATH"
4. Нажми "Install Now"
5. Проверь установку:
```bash
python --version
```

### macOS / Linux
```bash
# macOS
brew install python3

# Linux (Ubuntu/Debian)
sudo apt-get install python3 python3-pip
```

## Шаг 2: Создание Telegram бота

1. Открой Telegram и найди **@BotFather**
2. Напиши `/newbot`
3. Дай боту имя (например: "MACHATA Studio Bot")
4. Дай боту юзернейм (например: "machata_booking_bot")
5. **Скопируй токен**, который БотФадер отправил тебе

Выглядит так: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`

## Шаг 3: Скачивание файлов

1. Скачай `machata_bot.py`
2. Положи в папку на компьютере

## Шаг 4: Установка зависимостей

Открой терминал/консоль и выполни:
```bash
pip install pytelegrambotapi
```

## Шаг 5: Вставка токена

1. Открой `machata_bot.py` в текстовом редакторе
2. Найди строку:
```python
API_TOKEN = 'ТУТ_ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER'
```
3. Замени на:
```python
API_TOKEN = '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'
```

## Шаг 6: Запуск бота

В терминале выполни:
```bash
python machata_bot.py
```

Если всё верно, увидишь:
```
🎵 MACHATA studio бот запущен!
✨ Полнофункциональная версия с VIP скидками
☎️ Контакт: +7 (977) 777-78-27
📍 Telegram: @majesticbudan
```

## Шаг 7: Тестирование

1. Открой Telegram
2. Найди своего бота (@machata_booking_bot)
3. Напиши `/start`
4. Проверь меню

## ✅ Если не работает

### Ошибка: "python: command not found"
- Установи Python правильно (с добавлением в PATH)
- На Windows пробуй `python3` вместо `python`

### Ошибка: "ModuleNotFoundError: No module named 'telebot'"
- Выполни: `pip install pytelegrambotapi`

### Бот не отвечает в Telegram
- Проверь, что токен правильный
- Убедись, что боту написал /start
- Перезапусти скрипт

### Ошибка с кириллицей
- Убедись, что файл сохранён в UTF-8 кодировке
- Открой файл в VS Code, внизу нажми на "UTF-8"

## 🎯 Добавление VIP пользователей

1. Запусти бота один раз
2. Напиши боту в Telegram любое сообщение
3. В консоли увидишь: `👤 Пользователь: Иван | ID: 123456789`
4. Скопируй этот ID
5. В коде добавь:
```python
VIP_USERS = {
    123456789: {'name': 'Иван', 'discount': 20},
}
```

## 📝 Кастомизация

### Изменение тарифов
```python
'prices': {
    'repet': 700,
    'studio': 800,
    'full': 1500,
}
```

### Изменение контактов
```python
STUDIO_CONTACT = "+7 (977) 777-78-27"
STUDIO_ADDRESS = "Москва, Загородное шоссе, 1 корпус 2"
STUDIO_TELEGRAM = "@majesticbudan"
```

### Изменение режима работы
```python
'work_hours': {'start': 9, 'end': 22},  # 9:00 - 22:00
'off_days': [5, 6],                     # 5=сб, 6=вс
```

## 🚀 Запуск на сервере (для постоянной работы)

### Вариант 1: Используй Heroku / Railway / Render
Создай .env файл с токеном и деплой туда

### Вариант 2: Используй VPS
1. Установи Python на сервер
2. Загрузи файлы через SSH/SFTP
3. Используй `screen` или `tmux` для постоянного запуска:
```bash
screen -S machata_bot
python machata_bot.py
# Ctrl+A, потом D (detach)
```

---

Если что-то непонятно, пиши в @majesticbudan 📱
