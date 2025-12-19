# 📚 API Reference — MACHATA Bot

Полная справка по функциям и методам.

## 🔌 Основные функции

### load_config()
Загружает конфигурацию из файла или использует DEFAULT_CONFIG.
```python
config = load_config()
print(config['prices']['repet'])  # 700
```

### load_bookings()
Загружает все бронирования из JSON.
```python
bookings = load_bookings()
for booking in bookings:
    print(booking['name'], booking['date'])
```

### save_bookings(bookings)
Сохраняет бронирования в JSON.
```python
save_bookings(bookings)
```

### add_booking(booking)
Добавляет новое бронирование в список.
```python
booking = {
    'id': 1234567890,
    'user_id': 123456789,
    'name': 'Иван',
    'phone': '+7 (999) 000-00-00',
    'date': '2025-12-25',
    'times': [19, 20, 21],
    'service': 'studio',
    'price': 2160,
    'comment': 'Запись вокала',
    'status': 'pending'
}
add_booking(booking)
```

### cancel_booking_by_id(booking_id)
Отменяет бронирование по ID.
```python
cancelled = cancel_booking_by_id(1234567890)
```

## 👑 VIP функции

### get_user_discount(chat_id)
Возвращает скидку VIP пользователя (в процентах).
```python
discount = get_user_discount(123456789)
print(discount)  # 20 (если VIP)
```

### is_vip_user(chat_id)
Проверяет, является ли пользователь VIP.
```python
if is_vip_user(123456789):
    print("Это VIP!")
```

## 📅 Функции дат и времени

### get_available_dates(days=30)
Возвращает список доступных дат (исключая выходные).
```python
dates = get_available_dates(30)
print(dates[0])  # datetime object
```

### get_booked_slots(date_str, service)
Возвращает занятые часы для даты и сервиса.
```python
booked = get_booked_slots('2025-12-25', 'studio')
print(booked)  # [18, 19, 20]
```

## 🎮 Состояния пользователя (user_states)

Структура состояния:
```python
user_states[chat_id] = {
    'step': 'name',  # service, date, time, name, phone, comment
    'type': 'repet',  # repet, recording
    'service': 'studio',  # repet, studio, full
    'date': '2025-12-25',  # YYYY-MM-DD
    'selected_times': [19, 20, 21],  # часы
    'name': 'Иван',
    'phone': '+7 (999) 000-00-00',
    'comment': 'Запись вокала'
}
```

## 📨 Обработчики сообщений

### @bot.message_handler(commands=['start'])
Обрабатывает команду /start.

### @bot.message_handler(func=lambda m: m.text == "🎙 Запись трека")
Обрабатывает нажатие кнопки меню.

### @bot.callback_query_handler(func=lambda c: c.data.startswith("service_"))
Обрабатывает нажатие кнопки выбора сервиса.

## 🔔 Callback данные

| Callback | Назначение |
|----------|-----------|
| service_studio | Выбор: аренда студии (самостоятельно) |
| service_full | Выбор: аренда со звукорежем |
| service_repet | Выбор: репетиция |
| date_YYYY-MM-DD | Выбор даты |
| timeAdd_HH | Добавить час |
| timeDel_HH | Удалить час |
| confirm_times | Подтвердить время |
| cancel | Отмена всей операции |
| booking_detail_ID | Посмотреть детали брони |
| cancel_booking_ID | Отменить конкретную бронь |

## 💾 Структура JSON

### machata_bookings.json
```json
[
  {
    "id": 1234567890,
    "user_id": 123456789,
    "service": "studio",
    "date": "2025-12-25",
    "times": [19, 20, 21],
    "duration": 3,
    "name": "Иван",
    "phone": "+7 (999) 000-00-00",
    "comment": "Запись вокала",
    "price": 2160,
    "status": "pending",
    "created_at": "2025-12-15T18:30:00"
  }
]
```

### machata_config.json
```json
{
  "prices": {
    "repet": 700,
    "studio": 800,
    "full": 1500
  },
  "work_hours": {
    "start": 9,
    "end": 22
  },
  "off_days": [5, 6],
  "payment": {
    "phone": "+7 (977) 777-78-27",
    "card": "2202 2000 0000 0000",
    "bank": "Сбербанк"
  }
}
```

## 🔧 Переменные конфига

| Параметр | Значение | Описание |
|----------|----------|---------|
| API_TOKEN | string | Токен Telegram бота |
| BOOKINGS_FILE | string | Путь к файлу броней |
| CONFIG_FILE | string | Путь к файлу конфига |
| STUDIO_NAME | string | Название студии |
| STUDIO_CONTACT | string | Телефон студии |
| STUDIO_ADDRESS | string | Адрес студии |
| STUDIO_HOURS | string | Часы работы |
| STUDIO_TELEGRAM | string | Юзернейм студии в TG |
| VIP_USERS | dict | Словарь VIP пользователей |

---

Удачи в кодировании! 🚀
