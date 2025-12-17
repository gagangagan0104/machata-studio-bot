# Machata Studio Bot

Telegram-бот для бронирования репетиций в Machata studio.

## Функции

- 💰 Показ цен на аренду (700₽/час)
- 📋 Правила студии и условия аренды
- 📅 Бронирование репетиций (в разработке)

## Деплой на Render

### 1. Создать бота в Telegram

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте команду `/newbot`
3. Введите имя бота (например, `Machata Studio Bot`)
4. Введите username бота (должен оканчиваться на `bot`, например `machata_studio_bot`)
5. Скопируйте **API Token** (не делитесь им ни с кем!)

### 2. Создать Web Service на Render

1. Перейдите на [Render](https://render.com/) и зарегистрируйтесь
2. Нажмите **New +** → **Web Service**
3. Подключите свой GitHub-аккаунт
4. Выберите репозиторий `machata-studio-bot`
5. Заполните настройки:
   - **Name**: `machata-studio-bot`
   - **Region**: выберите ближайший регион
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`

### 3. Добавить переменную окружения

1. В настройках сервиса перейдите в **Environment**
2. Добавьте новую переменную:
   - **Key**: `BOT_TOKEN`
   - **Value**: ваш API Token от BotFather
3. Нажмите **Save Changes**

### 4. Запустить бота

1. Render автоматически запустит деплой
2. Дождитесь статуса **Live**
3. Откройте своего бота в Telegram и нажмите `/start`

## Структура проекта

```
machata-studio-bot/
├── bot.py              # Основной код бота
├── requirements.txt    # Зависимости Python
├── Procfile            # Конфигурация для Render
└── README.md           # Документация
```

## Поддержка

Если у вас возникли вопросы или проблемы, откройте issue в этом репозитории.
