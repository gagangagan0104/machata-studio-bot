# 🎨 Кастомизация MACHATA Bot

Примеры и инструкции по изменению функциональности.

## 💰 Изменение тарифов

### Вариант 1: Удалить старые, добавить новые
```python
DEFAULT_CONFIG = {
    'prices': {
        'repet_30': 400,      # 30 минут репетиции
        'repet_60': 700,      # 60 минут репетиции
        'studio_4h': 2400,    # 4 часа студии
        'studio_8h': 4500,    # 8 часов студии (день)
    },
}
```

### Вариант 2: Динамические скидки за количество часов
```python
def calculate_price(service, hours, vip_discount=0):
    config = load_config()
    base_price = config['prices'][service] * hours
    
    if vip_discount > 0:
        return int(base_price * (1 - vip_discount / 100))
    
    if hours >= 8:
        return int(base_price * 0.80)  # 20% скидка
    elif hours >= 5:
        return int(base_price * 0.85)  # 15% скидка
    elif hours >= 3:
        return int(base_price * 0.90)  # 10% скидка
    
    return base_price
```

## 🕐 Изменение режима работы

### Вариант 1: 24/7
```python
'work_hours': {'start': 0, 'end': 24},
'off_days': [],  # Нет выходных
```

### Вариант 2: Только выходные
```python
'work_hours': {'start': 10, 'end': 20},
'off_days': [0, 1, 2, 3, 4],  # Только сб (5) и вс (6)
```

### Вариант 3: Разный режим по дням
```python
def get_available_dates(days=30):
    dates = []
    config = load_config()
    
    for i in range(1, days + 1):
        date = datetime.now() + timedelta(days=i)
        weekday = date.weekday()
        
        # Выходные - обычные выходные
        if weekday in config.get('off_days', [5, 6]):
            continue
        
        # Понедельник - выходной
        if weekday == 0:
            continue
        
        dates.append(date)
    
    return dates
```

## 📱 Добавление новых кнопок меню

### Добавь в main_menu_keyboard():
```python
def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    kb.add(types.KeyboardButton("🎙 Запись трека"))
    kb.add(types.KeyboardButton("🎸 Репетиция"))
    kb.add(types.KeyboardButton("📝 Мои бронирования"))
    kb.add(types.KeyboardButton("💰 Тарифы & акции"))
    kb.add(types.KeyboardButton("📍 Как найти"))
    kb.add(types.KeyboardButton("💬 Живой чат"))
    kb.add(types.KeyboardButton("📊 Статистика"))  # Новая кнопка
    kb.add(types.KeyboardButton("⚙️ Настройки"))    # Новая кнопка
    return kb
```

### Добавь обработчик:
```python
@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def show_stats(m):
    chat_id = m.chat.id
    bookings = load_bookings()
    
    # Фильтруем по пользователю
    user_bookings = [b for b in bookings if b.get('user_id') == chat_id]
    total_hours = sum(b['duration'] for b in user_bookings)
    total_spent = sum(b['price'] for b in user_bookings)
    
    text = f"""
📊 ТВОЯ СТАТИСТИКА

Количество сеансов: {len(user_bookings)}
Всего часов: {total_hours}
Потрачено: {total_spent} ₽
"""
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())
```

## 🎨 Изменение текстов сообщений

### Более дружеский тон
```python
def get_welcome_text(chat_id):
    text = """
🎵 Эй! Добро пожаловать в MACHATA Studio!

Здесь мы создаём музыку мирового уровня 🌟

🎸 Нужна репетиция? 700₽/час!
🎧 Хочешь записать трек? 800-1500₽!
✨ Звукорежиссер поможет? Конечно!

Давай забронируем время? 👇
"""
    return text
```

## 👑 Расширенная VIP система

### Добавь разные уровни VIP:
```python
VIP_USERS = {
    123456789: {'name': 'Иван', 'level': 'gold', 'discount': 30},
    987654321: {'name': 'Мария', 'level': 'silver', 'discount': 20},
    555444333: {'name': 'Миша', 'level': 'bronze', 'discount': 10},
}

def get_vip_badge(chat_id):
    if chat_id not in VIP_USERS:
        return ""
    
    user = VIP_USERS[chat_id]
    badges = {
        'gold': '👑🥇',
        'silver': '👑🥈',
        'bronze': '👑🥉'
    }
    
    return f"{badges[user['level']]} {user['name']} (скидка {user['discount']}%)"
```

## 📧 Отправка подтверждения по email

### Добавь зависимость:
```bash
pip install python-dotenv
```

### Добавь функцию:
```python
import smtplib
from email.mime.text import MIMEText

def send_email_confirmation(booking):
    email = "hello@machata.studio"
    password = "твой_пароль_приложения"
    
    # Форматируем письмо
    subject = f"Подтверждение брони #{booking['id']}"
    body = f"""
    Привет, {booking['name']}!
    
    Твоя бронь подтверждена:
    Дата: {booking['date']}
    Время: {min(booking['times']):02d}:00
    Сумма: {booking['price']} ₽
    """
    
    # Отправляем
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(email, password)
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    
    server.send_message(msg)
    server.quit()
```

## 🗄️ Миграция на БД (SQLite)

### Создай database.py:
```python
import sqlite3

def init_db():
    conn = sqlite3.connect('machata.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        name TEXT,
        phone TEXT,
        service TEXT,
        date TEXT,
        times TEXT,
        price INTEGER,
        status TEXT,
        created_at TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

def add_booking_db(booking):
    conn = sqlite3.connect('machata.db')
    c = conn.cursor()
    
    c.execute('''INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (booking['id'], booking['user_id'], booking['name'], 
               booking['phone'], booking['service'], booking['date'],
               ','.join(map(str, booking['times'])), booking['price'],
               booking['status'], booking['created_at']))
    
    conn.commit()
    conn.close()
```

## 🔔 Добавь уведомления

### Отправка напоминания за день:
```python
from datetime import datetime, timedelta

def send_reminders():
    bookings = load_bookings()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    for booking in bookings:
        if booking['date'] == tomorrow and booking['status'] != 'cancelled':
            text = f"""
            ⏰ НАПОМИНАНИЕ!
            
            Завтра у тебя сеанс в {min(booking['times']):02d}:00
            Запиши адрес: {STUDIO_ADDRESS}
            """
            
            bot.send_message(booking['user_id'], text)
```

---

Фантазируй и кастомизируй! 🚀
