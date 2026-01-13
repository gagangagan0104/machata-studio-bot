import telebot
from telebot import types
import json
import os
from datetime import datetime, timedelta
import sys
import traceback
import re
import requests
import uuid
import base64
from flask import Flask, request

# ====== КОНФИГУРАЦИЯ ======================================================

API_TOKEN = os.environ.get("API_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
CURRENCY = "RUB"

# Конфигурация ЮKassa API
YOOKASSA_SHOP_ID = os.environ.get("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.environ.get("YOOKASSA_SECRET_KEY", "")

# Информация о студии
STUDIO_NAME = "MACHATA studio"
BOOKINGS_FILE = 'machata_bookings.json'
CONFIG_FILE = 'machata_config.json'
STUDIO_CONTACT = "+7 (977) 777-78-27"
STUDIO_ADDRESS = "Москва, Загородное шоссе, 1 корпус 2"
STUDIO_HOURS = "Пн–Пт 9:00–03:00 | Сб–Вс 09:00–09:00"
STUDIO_TELEGRAM = "@majesticbudan"
STUDIO_EMAIL = "hello@machata.studio"

# Файл для хранения VIP пользователей
VIP_USERS_FILE = 'vip_users.json'

# VIP пользователи (загружаются из файла)
VIP_USERS = {}

# Конфигурация по умолчанию
DEFAULT_CONFIG = {
    'prices': {
        'repet': 700,
        'studio': 800,
        'full': 1500,
    },
    'work_hours': {'start': 9, 'end': 22},
    'off_days': [5, 6],
}

# Инициализация бота
bot = telebot.TeleBot(API_TOKEN, threaded=True, parse_mode='HTML')
user_states = {}

# Кэш для конфигурации
_config_cache = None
_config_cache_time = None
CACHE_TTL = 300  # 5 минут

# ====== ЛОГИРОВАНИЕ ======================================================

def log_info(msg):
    """Информационное логирование"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] ℹ️ INFO: {msg}")
    sys.stdout.flush()

def log_error(msg, exc=None):
    """Логирование ошибок"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] ❌ ERROR: {msg}", file=sys.stderr)
    if exc:
        print(traceback.format_exc(), file=sys.stderr)
    sys.stderr.flush()

# ====== РАБОТА С ФАЙЛАМИ =================================================

def load_config():
    """Загрузка конфига с кэшированием"""
    global _config_cache, _config_cache_time
    
    now = datetime.now()
    if _config_cache and _config_cache_time and (now - _config_cache_time).seconds < CACHE_TTL:
        return _config_cache
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _config_cache = data
                _config_cache_time = now
                return data
        _config_cache = DEFAULT_CONFIG
        _config_cache_time = now
        return DEFAULT_CONFIG
    except Exception as e:
        log_error(f"load_config: {str(e)}", e)
        return DEFAULT_CONFIG

def load_bookings():
    """Загрузка броней"""
    try:
        if os.path.exists(BOOKINGS_FILE):
            with open(BOOKINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        log_error(f"load_bookings: {str(e)}", e)
        return []

def save_bookings(bookings):
    """Сохранение броней"""
    try:
        with open(BOOKINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(bookings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_error(f"save_bookings: {str(e)}", e)

def add_booking(booking):
    """Добавление брони"""
    bookings = load_bookings()
    bookings.append(booking)
    save_bookings(bookings)
    log_info(f"Бронь добавлена: ID={booking.get('id')}")

def cancel_booking_by_id(booking_id):
    """Отмена брони по ID"""
    bookings = load_bookings()
    for b in bookings:
        if b.get('id') == booking_id:
            b['status'] = 'cancelled'
            save_bookings(bookings)
            return b
    return None

# ====== VIP ФУНКЦИИ ======================================================

def load_vip_users():
    """Загрузка VIP пользователей из файла"""
    global VIP_USERS
    try:
        if os.path.exists(VIP_USERS_FILE):
            with open(VIP_USERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Преобразуем ключи в int (JSON сохраняет их как строки)
                VIP_USERS = {int(k): v for k, v in data.items()}
                log_info(f"VIP пользователи загружены: {len(VIP_USERS)}")
        else:
            VIP_USERS = {}
            save_vip_users()
    except Exception as e:
        log_error(f"load_vip_users: {str(e)}", e)
        VIP_USERS = {}

def save_vip_users():
    """Сохранение VIP пользователей в файл"""
    try:
        with open(VIP_USERS_FILE, 'w', encoding='utf-8') as f:
            # Сохраняем ключи как строки, так как JSON не поддерживает int ключи
            json.dump({str(k): v for k, v in VIP_USERS.items()}, f, ensure_ascii=False, indent=2)
        log_info(f"VIP пользователи сохранены: {len(VIP_USERS)}")
    except Exception as e:
        log_error(f"save_vip_users: {str(e)}", e)

def get_user_discount(chat_id):
    """Получение VIP скидки"""
    return VIP_USERS.get(chat_id, {}).get('discount', 0)

def get_user_custom_price_repet(chat_id):
    """Получение индивидуальной цены на репетицию для VIP пользователя"""
    if chat_id in VIP_USERS:
        custom_price = VIP_USERS[chat_id].get('custom_price_repet')
        if custom_price is not None:
            return custom_price
    return None

def is_vip_user(chat_id):
    """Проверка VIP статуса"""
    return chat_id in VIP_USERS

# ====== РАБОТА С ДАТАМИ ===================================================

def get_available_dates(days=30):
    """Получение доступных дат"""
    try:
        dates = []
        config = load_config()
        off_days = config.get('off_days', [5, 6])
        for i in range(1, days + 1):
            date = datetime.now() + timedelta(days=i)
            if date.weekday() not in off_days:
                dates.append(date)
        return dates
    except Exception as e:
        log_error(f"get_available_dates: {str(e)}", e)
        return []

def get_booked_slots(date_str, service):
    """Получение занятых часов"""
    try:
        bookings = load_bookings()
        booked = []
        for booking in bookings:
            if booking.get('status') in ['cancelled', 'awaiting_payment']:
                continue
            if booking.get('date') == date_str and booking.get('service') == service:
                booked.extend(booking.get('times', []))
        return sorted(set(booked))
    except Exception as e:
        log_error(f"get_booked_slots: {str(e)}", e)
        return []

# ====== КЛАВИАТУРЫ ========================================================

def main_menu_keyboard():
    """Главное меню"""
    kb = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    kb.add(
        types.KeyboardButton("🎙 Запись трека"),
        types.KeyboardButton("🎸 Репетиция")
    )
    kb.add(
        types.KeyboardButton("📝 Мои бронирования"),
        types.KeyboardButton("💰 Тарифы")
    )
    kb.add(
        types.KeyboardButton("📍 Контакты"),
        types.KeyboardButton("💬 Поддержка")
    )
    return kb

def cancel_keyboard():
    """Клавиатура отмены"""
    kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Отменить"))
    kb.add(types.KeyboardButton("🏠 Главное меню"))
    return kb

def service_keyboard(service_type):
    """Клавиатура выбора услуги"""
    kb = types.InlineKeyboardMarkup(row_width=1)
    
    if service_type == "recording":
        kb.add(types.InlineKeyboardButton(
            "🎧 Студия (самостоятельно) — 800 ₽/ч",
            callback_data="service_studio"))
        kb.add(types.InlineKeyboardButton(
            "✨ Студия со звукорежем — 1500 ₽",
            callback_data="service_full"))
    elif service_type == "repet":
        kb.add(types.InlineKeyboardButton(
            "🎸 Репетиция — 700 ₽/ч",
            callback_data="service_repet"))
    
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return kb

def dates_keyboard(page=0):
    """Клавиатура выбора даты"""
    kb = types.InlineKeyboardMarkup()
    dates = get_available_dates(30)
    per_page = 7
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, len(dates))
    
    weekdays = {0: 'Пн', 1: 'Вт', 2: 'Ср', 3: 'Чт', 4: 'Пт', 5: 'Сб', 6: 'Вс'}
    
    for d in dates[start_idx:end_idx]:
        date_str = d.strftime(f"%d.%m ({weekdays[d.weekday()]})")
        date_obj = d.strftime("%Y-%m-%d")
        kb.add(types.InlineKeyboardButton(
            f"📅 {date_str}",
            callback_data=f"date_{date_obj}"))
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton("◀️ Назад", callback_data=f"dates_page_{page-1}"))
    if end_idx < len(dates):
        nav_buttons.append(types.InlineKeyboardButton("Вперёд ▶️", callback_data=f"dates_page_{page+1}"))
    if nav_buttons:
        kb.row(*nav_buttons)
    
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_service"))
    return kb

def times_keyboard(chat_id, date_str, service):
    """Клавиатура выбора времени"""
    kb = types.InlineKeyboardMarkup(row_width=3)
    config = load_config()
    booked = get_booked_slots(date_str, service)
    selected = user_states.get(chat_id, {}).get('selected_times', [])
    
    buttons = []
    for h in range(config['work_hours']['start'], config['work_hours']['end']):
        if h in booked:
            buttons.append(types.InlineKeyboardButton("🚫", callback_data="skip"))
        elif h in selected:
            buttons.append(types.InlineKeyboardButton(f"✅ {h}", callback_data=f"timeDel_{h}"))
        else:
            buttons.append(types.InlineKeyboardButton(f"{h}:00", callback_data=f"timeAdd_{h}"))
    
    for i in range(0, len(buttons), 3):
        kb.row(*buttons[i:i+3])
    
    if selected:
        start, end = min(selected), max(selected) + 1
        
        # Проверяем индивидуальную цену для VIP на репетицию
        custom_price_repet = get_user_custom_price_repet(chat_id) if service == 'repet' else None
        
        if custom_price_repet is not None:
            # Используем индивидуальную цену для VIP
            base_price = custom_price_repet * len(selected)
            price = base_price
            discount_text = " (VIP цена)"
        else:
            # Обычный расчет
            if service == 'full':
                base_price = config['prices'].get('full', 1500)
            else:
                base_price = config['prices'].get(service, 700) * len(selected)
            
            vip_discount = get_user_discount(chat_id)
            if vip_discount > 0:
                price = int(base_price * (1 - vip_discount / 100))
                discount_text = f" (VIP -{vip_discount}%)"
            elif len(selected) >= 5:
                price = int(base_price * 0.85)
                discount_text = " (-15%)"
            elif len(selected) >= 3:
                price = int(base_price * 0.9)
                discount_text = " (-10%)"
            else:
                price = base_price
                discount_text = ""
        
        kb.row(
            types.InlineKeyboardButton("🔄 Очистить", callback_data="clear_times"),
            types.InlineKeyboardButton(f"✅ Далее {price}₽{discount_text}", callback_data="confirm_times")
        )
    
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_date"))
    return kb

def bookings_keyboard(bookings, user_id):
    """Клавиатура броней пользователя"""
    kb = types.InlineKeyboardMarkup()
    user_bookings = [
        b for b in bookings
        if b.get('user_id') == user_id and b.get('status') != 'cancelled'
    ]
    
    if not user_bookings:
        return None
    
    for booking in user_bookings:
        bid = booking.get('id')
        date = booking.get('date', '')
        if booking.get('times'):
            start = min(booking['times'])
            time_str = f"{start:02d}:00"
        else:
            time_str = ""
        
        service_emoji = {'repet': '🎸', 'studio': '🎧', 'full': '✨'}
        emoji = service_emoji.get(booking['service'], '📋')
        status = booking.get('status', 'pending')
        status_icon = "💵" if status == 'paid' else "⏳"
        
        text = f"{emoji} {date} {time_str} · {booking['price']}₽ {status_icon}"
        kb.add(types.InlineKeyboardButton(text, callback_data=f"booking_detail_{bid}"))
    
    return kb

# ====== ФОРМАТИРОВАНИЕ ТЕКСТА ============================================

def format_welcome(chat_id):
    """Форматированное приветствие"""
    vip_badge = ""
    if is_vip_user(chat_id):
        vip_name = VIP_USERS[chat_id]['name']
        vip_discount = VIP_USERS[chat_id]['discount']
        vip_badge = f"\n\n<b>👑 Привет, {vip_name}!</b>\nVIP скидка <b>{vip_discount}%</b> на все услуги! 🎁"
    
    return f"""<b>🎵 Добро пожаловать в {STUDIO_NAME}!</b>

✨ Профессиональная студия звукозаписи и репетиционная база в Москве

<b>🎯 Наши услуги:</b>

<b>🎸 РЕПЕТИЦИЯ</b> — <b>700 ₽/час</b>
   ✓ Обработанная акустика
   ✓ Все инструменты в наличии
   ✓ Кофе и чай бесплатно
   ✓ Уютная атмосфера

<b>🎧 СТУДИЯ (самостоятельно)</b> — <b>800 ₽/час</b>
   ✓ Профессиональное оборудование
   ✓ Полный контроль звука
   ✓ Звукоизоляция премиум-класса

<b>✨ СТУДИЯ СО ЗВУКОРЕЖЕМ</b> — <b>1500 ₽</b>
   ✓ Запись + микширование
   ✓ Профессиональный звукорежиссёр
   ✓ Готовый трек к релизу

<b>🎁 Скидки:</b>
   💚 <b>3+ часа</b> → <b>-10%</b>
   💚 <b>5+ часов</b> → <b>-15%</b>

🚀 <b>Забронируй время за 2 клика!</b>{vip_badge}"""

def format_prices(chat_id):
    """Форматированные тарифы"""
    vip_info = ""
    if is_vip_user(chat_id):
        vip_discount = VIP_USERS[chat_id]['discount']
        vip_info = f"\n\n<b>👑 ТВОЯ VIP СКИДКА: {vip_discount}% на все услуги!</b>"
    
    return f"""<b>💰 ТАРИФЫ {STUDIO_NAME}</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎸 РЕПЕТИЦИЯ</b> — <b>700 ₽/час</b>

   ✓ Профессиональная акустика
   ✓ Все инструменты в наличии
   ✓ Кофе/чай бесплатно
   ✓ Уютная атмосфера

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎧 СТУДИЯ (САМОСТОЯТЕЛЬНО)</b> — <b>800 ₽/час</b>

   ✓ Премиум-оборудование
   ✓ Звукоизоляция класса А
   ✓ Полный контроль звука

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>✨ СТУДИЯ СО ЗВУКОРЕЖЕМ</b> — <b>1500 ₽</b>

   ✓ Запись + микширование
   ✓ Профессиональный звукорежиссёр
   ✓ Готовый трек к релизу

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎁 СКИДКИ:</b>

💚 <b>3+ часа</b> подряд → <b>-10%</b>
💚 <b>5+ часов</b> подряд → <b>-15%</b>
💎 Постоянным клиентам — особые условия{vip_info}

🚀 <b>Забронируй прямо сейчас!</b>"""

def format_location():
    """Форматированная информация о локации"""
    return f"""<b>📍 КАК НАС НАЙТИ</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎵 {STUDIO_NAME}</b>

📍 <b>{STUDIO_ADDRESS}</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🕐 РЕЖИМ РАБОТЫ:</b>

{STUDIO_HOURS}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📞 КОНТАКТЫ:</b>

☎️ <b>{STUDIO_CONTACT}</b>
📱 <b>{STUDIO_TELEGRAM}</b>
💌 <b>{STUDIO_EMAIL}</b>

🚗 Удобная парковка
🚇 Близко к метро

<b>Приходи творить! 🎵</b>"""

# ====== ОБРАБОТЧИКИ КОМАНД ===============================================

@bot.message_handler(commands=['start'])
def send_welcome(m):
    """Обработчик /start"""
    try:
        chat_id = m.chat.id
        user_states.pop(chat_id, None)
        log_info(f"START: {m.from_user.first_name} (ID: {chat_id})")
        
        bot.send_message(
            chat_id,
            format_welcome(chat_id),
            reply_markup=main_menu_keyboard(),
            parse_mode='HTML'
        )
    except Exception as e:
        log_error(f"send_welcome: {str(e)}", e)

@bot.message_handler(func=lambda m: m.text == "🏠 Главное меню")
def to_main_menu(m):
    """Возврат в главное меню"""
    chat_id = m.chat.id
    user_states.pop(chat_id, None)
    bot.send_message(chat_id, "🏠 <b>Главное меню</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🎙 Запись трека")
def book_recording(m):
    """Бронирование записи"""
    chat_id = m.chat.id
    text = """<b>🎙 ЗАПИСЬ В СТУДИИ</b>

✨ Профессиональная звукозапись мирового уровня

<b>🎯 Что получаешь:</b>
   ✓ Премиум-оборудование (Neve, SSL, API)
   ✓ Звукоизоляция класса А
   ✓ Полный контроль над звуком
   ✓ Готовый трек к релизу

<b>💎 Выбери формат записи:</b>"""
    
    bot.send_message(chat_id, text, reply_markup=service_keyboard("recording"), parse_mode='HTML')
    user_states[chat_id] = {'step': 'service', 'type': 'recording', 'selected_times': []}

@bot.message_handler(func=lambda m: m.text == "🎸 Репетиция")
def book_repet(m):
    """Бронирование репетиции"""
    chat_id = m.chat.id
    text = """<b>🎸 РЕПЕТИЦИОННАЯ КОМНАТА</b>

🔥 Идеальное место для репетиций и творчества!

<b>✨ Что включено:</b>
   ✓ Профессиональная акустика
   ✓ Все инструменты в наличии
   ✓ Удобная планировка
   ✓ Кофе, чай, диван — бесплатно 😎
   ✓ Уютная атмосфера для вдохновения

<b>💪 Готов к репетиции? Выбирай время!</b>"""
    
    bot.send_message(chat_id, text, reply_markup=service_keyboard("repet"), parse_mode='HTML')
    user_states[chat_id] = {'step': 'service', 'type': 'repet', 'selected_times': []}

@bot.message_handler(func=lambda m: m.text == "❌ Отменить")
def cancel_booking(m):
    """Отмена бронирования"""
    chat_id = m.chat.id
    user_states.pop(chat_id, None)
    bot.send_message(chat_id, "❌ <b>Отменено.</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "📝 Мои бронирования")
def my_bookings(m):
    """Просмотр броней"""
    chat_id = m.chat.id
    bookings = load_bookings()
    user_bookings = [
        b for b in bookings
        if b.get('user_id') == chat_id and b.get('status') != 'cancelled'
    ]
    
    if not user_bookings:
        bot.send_message(
            chat_id,
            "📭 <b>Пока нет активных броней.</b>\n\n"
            "🎵 Создадим первую? Выбери услугу в главном меню!\n\n"
            "💡 После оплаты все твои брони будут здесь",
            reply_markup=main_menu_keyboard(),
            parse_mode='HTML'
        )
        return
    
    kb = bookings_keyboard(bookings, chat_id)
    if kb:
        bot.send_message(chat_id, "<b>📋 Твои сеансы:</b>\n\nТапни для деталей:", reply_markup=kb, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "💰 Тарифы")
def show_prices(m):
    """Показ тарифов"""
    chat_id = m.chat.id
    bot.send_message(chat_id, format_prices(chat_id), reply_markup=main_menu_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "📍 Контакты")
def location(m):
    """Показ локации"""
    chat_id = m.chat.id
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🗺️ Яндекс.Карты", url="https://maps.yandex.ru/?text=MACHATA+studio"))
    kb.add(types.InlineKeyboardButton("🗺️ 2ГИС", url="https://2gis.ru/moscow/search/MACHATA"))
    
    bot.send_message(chat_id, format_location(), reply_markup=kb, parse_mode='HTML')
    bot.send_message(chat_id, "🏠 <b>Главное меню</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "💬 Поддержка")
def live_chat(m):
    """Поддержка"""
    chat_id = m.chat.id
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📱 Telegram", url=f"https://t.me/{STUDIO_TELEGRAM.replace('@', '')}"))
    
    text = f"""<b>💬 СВЯЖИСЬ С НАМИ</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📱 <b>Telegram:</b> {STUDIO_TELEGRAM}
☎️ <b>Телефон:</b> {STUDIO_CONTACT}
💌 <b>Email:</b> {STUDIO_EMAIL}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ Обычно отвечаем за 15 минут
💬 Поможем с выбором услуги
🎵 Консультация бесплатно

<b>Ждём твоих вопросов! 🚀</b>"""
    
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode='HTML')
    bot.send_message(chat_id, "🏠 <b>Главное меню</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')

# ====== CALLBACK ОБРАБОТЧИКИ ============================================

@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cb_cancel(c):
    chat_id = c.message.chat.id
    user_states.pop(chat_id, None)
    bot.edit_message_text("❌ <b>Отменено</b>", chat_id, c.message.message_id, parse_mode='HTML')
    bot.send_message(chat_id, "🏠 <b>Главное меню</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data.startswith("service_"))
def cb_service(c):
    chat_id = c.message.chat.id
    service = c.data.replace("service_", "")
    user_states[chat_id] = {'step': 'date', 'service': service, 'selected_times': []}
    
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Студия (самостоятельная)',
        'full': '✨ Студия со звукорежем',
    }
    
    text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎵 ШАГ 1/4: ВЫБОР ДАТЫ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

✅ <b>{names.get(service, service)}</b> выбрана!

📅 <b>Выбери удобную дату:</b>

💡 Совет: бронируй заранее — лучшие слоты разбирают быстро!"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=dates_keyboard(0), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data.startswith("dates_page_"))
def cb_dates_page(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state:
        return
    
    page = int(c.data.replace("dates_page_", ""))
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Студия (самостоятельная)',
        'full': '✨ Студия со звукорежем',
    }
    
    text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎵 ШАГ 1/4: ВЫБОР ДАТЫ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

✅ <b>{names.get(state['service'], state['service'])}</b> выбрана!

📅 <b>Выбери удобную дату:</b>

💡 Совет: бронируй заранее — лучшие слоты разбирают быстро!"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=dates_keyboard(page), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data.startswith("date_"))
def cb_date(c):
    chat_id = c.message.chat.id
    date_str = c.data.replace("date_", "")
    state = user_states.get(chat_id)
    if not state:
        return
    
    state['date'] = date_str
    state['step'] = 'time'
    state['selected_times'] = []
    
    d = datetime.strptime(date_str, "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    
    text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎵 ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

📅 <b>Дата:</b> {df}

⏰ <b>Выбери часы:</b>

💚 Чем больше часов подряд — тем больше скидка!

<b>⭕ свободно | ✅ выбрано | 🚫 занято</b>"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, date_str, state['service']), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data.startswith("timeAdd_"))
def cb_add_time(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state:
        return
    
    h = int(c.data.replace("timeAdd_", ""))
    state.setdefault('selected_times', []).append(h)
    state['selected_times'] = sorted(set(state['selected_times']))
    
    d = datetime.strptime(state['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    sel = state['selected_times']
    start, end = min(sel), max(sel) + 1
    
    text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎵 ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

📅 <b>Дата:</b> {df}
⏰ <b>Выбрано:</b> {len(sel)} ч ({start:02d}:00 – {end:02d}:00)

💚 Продолжай выбирать или нажми <b>✅ Далее</b>"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, state['date'], state['service']), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data.startswith("timeDel_"))
def cb_del_time(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state:
        return
    
    h = int(c.data.replace("timeDel_", ""))
    if h in state['selected_times']:
        state['selected_times'].remove(h)
    
    d = datetime.strptime(state['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    sel = state['selected_times']
    
    if sel:
        start, end = min(sel), max(sel) + 1
        text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎵 ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

📅 <b>Дата:</b> {df}
⏰ <b>Выбрано:</b> {len(sel)} ч ({start:02d}:00 – {end:02d}:00)

💚 Продолжай выбирать или нажми <b>✅ Далее</b>"""
    else:
        text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎵 ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

📅 <b>Дата:</b> {df}

⏰ <b>Выбери часы:</b>

💚 Чем больше часов подряд — тем больше скидка!

<b>⭕ свободно | ✅ выбрано | 🚫 занято</b>"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, state['date'], state['service']), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "clear_times")
def cb_clear_times(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state:
        return
    
    state['selected_times'] = []
    d = datetime.strptime(state['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    
    text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎵 ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

📅 <b>Дата:</b> {df}

✅ <b>Выбор очищен</b>

⏰ <b>Выбери часы:</b>

💚 Чем больше часов подряд — тем больше скидка!

<b>⭕ свободно | ✅ выбрано | 🚫 занято</b>"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, state['date'], state['service']), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "back_to_date")
def cb_back_to_date(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state:
        return
    
    state['step'] = 'date'
    state['selected_times'] = []
    
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Студия (самостоятельная)',
        'full': '✨ Студия со звукорежем',
    }
    
    text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎵 ШАГ 1/4: ВЫБОР ДАТЫ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

✅ <b>{names.get(state['service'], state['service'])}</b> выбрана!

📅 <b>Выбери удобную дату:</b>

💡 Совет: бронируй заранее — лучшие слоты разбирают быстро!"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=dates_keyboard(0), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "back_to_service")
def cb_back_to_service(c):
    chat_id = c.message.chat.id
    service_type = user_states.get(chat_id, {}).get('type', 'repet')
    user_states[chat_id] = {'step': 'service', 'type': service_type, 'selected_times': []}
    
    if service_type == 'recording':
        text = """<b>🎙 ЗАПИСЬ В СТУДИИ</b>

✨ Профессиональная звукозапись мирового уровня

<b>🎯 Что получаешь:</b>
   ✓ Премиум-оборудование (Neve, SSL, API)
   ✓ Звукоизоляция класса А
   ✓ Полный контроль над звуком
   ✓ Готовый трек к релизу

<b>💎 Выбери формат записи:</b>"""
        kb = service_keyboard("recording")
    else:
        text = """<b>🎸 РЕПЕТИЦИОННАЯ КОМНАТА</b>

🔥 Идеальное место для репетиций и творчества!

<b>✨ Что включено:</b>
   ✓ Профессиональная акустика
   ✓ Все инструменты в наличии
   ✓ Удобная планировка
   ✓ Кофе, чай, диван — бесплатно 😎
   ✓ Уютная атмосфера для вдохновения

<b>💪 Готов к репетиции? Выбирай время!</b>"""
        kb = service_keyboard("repet")
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb, parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "confirm_times")
def cb_confirm_times(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state or not state.get('selected_times'):
        bot.answer_callback_query(c.id, "❌ Выбери хотя бы один час")
        return
    
    state['step'] = 'name'
    
    text = """<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎵 ШАГ 3/4: КОНТАКТНЫЕ ДАННЫЕ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

👤 <b>Как к тебе обращаться?</b>

💡 Можешь указать:
   • Имя
   • Никнейм
   • Название проекта/группы

<b>Введи:</b>"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, parse_mode='HTML')
    bot.send_message(chat_id, "👤 <b>Твоё имя или ник:</b>", reply_markup=cancel_keyboard(), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "skip")
def cb_skip(c):
    bot.answer_callback_query(c.id, "⚠️ Это время занято")

# ====== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ====================================

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('step') == 'name')
def process_name(m):
    chat_id = m.chat.id
    state = user_states.get(chat_id)
    if not state or state.get('step') != 'name':
        return
    
    state['name'] = m.text.strip()
    state['step'] = 'email'
    
    bot.send_message(
        chat_id,
        "📧 <b>Твой email:</b>\n\n"
        "✉️ На него отправим чек об оплате\n"
        "🔒 Данные защищены и используются только для чека",
        reply_markup=cancel_keyboard(),
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('step') == 'email')
def process_email(m):
    chat_id = m.chat.id
    state = user_states.get(chat_id)
    if not state or state.get('step') != 'email':
        return
    
    email = m.text.strip().lower()
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        bot.send_message(
            chat_id,
            "❌ <b>Некорректный email.</b> Пожалуйста, проверь.\n\n"
            "Пример: <code>name@example.com</code>\n\n"
            "📧 Email нужен для отправки чека об оплате",
            reply_markup=cancel_keyboard(),
            parse_mode='HTML'
        )
        return
    
    state['email'] = email
    state['step'] = 'phone'
    
    bot.send_message(
        chat_id,
        "☎️ <b>Номер телефона:</b>\n\n"
        "📞 Нужен для связи и подтверждения брони\n\n"
        "💡 Пример: <code>+7 (999) 000-00-00</code> или <code>79990000000</code>",
        reply_markup=cancel_keyboard(),
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('step') == 'phone')
def process_phone(m):
    chat_id = m.chat.id
    state = user_states.get(chat_id)
    if not state or state.get('step') != 'phone':
        return
    
    phone = m.text.strip()
    phone_digits = ''.join(c for c in phone if c.isdigit())
    
    if len(phone_digits) != 11:
        bot.send_message(
            chat_id,
            "❌ <b>Ошибка!</b> Номер должен содержать 11 цифр.\n\n"
            "☎️ Пример: <code>+7 (999) 000-00-00</code> или <code>79990000000</code>",
            reply_markup=cancel_keyboard(),
            parse_mode='HTML'
        )
        return
    
    state['phone'] = phone
    state['step'] = 'comment'
    
    kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    kb.add(types.KeyboardButton("⏭️ Пропустить"))
    kb.add(types.KeyboardButton("❌ Отменить"))
    kb.add(types.KeyboardButton("🏠 Главное меню"))
    
    bot.send_message(
        chat_id,
        "💬 <b>Что записываешь или репетируешь?</b>\n\n"
        "🎵 Расскажи о своём проекте (или пропусти)\n\n"
        "💡 Это поможет нам лучше подготовиться к сессии",
        reply_markup=kb,
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('step') == 'comment')
def process_comment(m):
    chat_id = m.chat.id
    state = user_states.get(chat_id)
    if not state or state.get('step') != 'comment':
        return
    
    if m.text == "⏭️ Пропустить":
        state['comment'] = "-"
    else:
        state['comment'] = m.text.strip()
    
    complete_booking(chat_id)

# ====== ЮKASSA API ======================================================

def create_yookassa_payment(amount, description, booking_id, customer_email, customer_phone, receipt_items):
    """Создание платежа через API ЮKassa"""
    try:
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            return {'success': False, 'error': 'Ключи ЮKassa не настроены'}
        
        shop_id = YOOKASSA_SHOP_ID.strip()
        secret_key = YOOKASSA_SECRET_KEY.strip()
        
        if not (secret_key.startswith('live_') or secret_key.startswith('test_')):
            return {'success': False, 'error': 'Неверный формат ключа ЮKassa'}
        
        auth_string = f"{shop_id}:{secret_key}"
        auth_b64 = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
        
        customer_data = {}
        if customer_email:
            customer_data["email"] = customer_email
        if customer_phone:
            customer_data["phone"] = customer_phone
        
        payment_data = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{STUDIO_TELEGRAM.replace('@', '')}"
            },
            "capture": True,
            "description": description[:255] if description else "Оплата бронирования",
            "metadata": {"booking_id": str(booking_id), "telegram_bot": "machata_studio"},
            "receipt": {
                "customer": customer_data,
                "items": receipt_items,
                "tax_system_code": 1
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_b64}",
            "Idempotence-Key": str(uuid.uuid4())
        }
        
        response = requests.post(
            "https://api.yookassa.ru/v3/payments",
            json=payment_data,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            payment_info = response.json()
            return {
                'success': True,
                'payment_url': payment_info.get("confirmation", {}).get("confirmation_url"),
                'payment_id': payment_info.get("id")
            }
        else:
            return {
                'success': False,
                'error': f"API вернул код {response.status_code}: {response.text[:300]}"
            }
            
    except Exception as e:
        log_error(f"Ошибка создания платежа: {str(e)}", e)
        return {'success': False, 'error': str(e)}

# ====== ЗАВЕРШЕНИЕ БРОНИ ================================================

def complete_booking(chat_id):
    """Завершение брони и создание платежа"""
    try:
        state = user_states.get(chat_id)
        if not state:
            bot.send_message(chat_id, "❌ <b>Ошибка:</b> состояние потеряно. Начни сначала.", parse_mode='HTML')
            return
        
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            bot.send_message(
                chat_id,
                "❌ <b>Ошибка конфигурации платежной системы.</b>\n\n"
                "Пожалуйста, напиши нам: " + STUDIO_TELEGRAM,
                parse_mode='HTML'
            )
            return
        
        sel = state.get('selected_times', [])
        if not sel:
            bot.send_message(chat_id, "❌ <b>Ошибка:</b> не выбрано время.", parse_mode='HTML')
            return
        
        if not all([state.get('name'), state.get('email'), state.get('phone')]):
            bot.send_message(chat_id, "❌ <b>Ошибка:</b> не все данные заполнены.", parse_mode='HTML')
            return
        
        config = load_config()
        service = state.get('service', 'repet')
        duration = len(sel)
        
        # Проверяем индивидуальную цену для VIP на репетицию
        custom_price_repet = get_user_custom_price_repet(chat_id) if service == 'repet' else None
        
        if custom_price_repet is not None:
            # Используем индивидуальную цену для VIP
            base_price = custom_price_repet * duration
            price = base_price
            discount_text = " (VIP цена)"
            log_info(f"Использована индивидуальная цена VIP для репетиции: {custom_price_repet}₽/ч × {duration}ч = {price}₽")
        else:
            # Обычный расчет
            if service == 'full':
                base_price = config['prices'].get('full', 1500)
            else:
                base_price = config['prices'].get(service, 700) * duration
            
            price = base_price
            discount_text = ""
            
            vip_discount = get_user_discount(chat_id)
            if vip_discount > 0:
                price = int(base_price * (1 - vip_discount / 100))
                discount_text = f" (VIP -{vip_discount}%)"
            elif duration >= 5:
                price = int(base_price * 0.85)
                discount_text = " (-15%)"
            elif duration >= 3:
                price = int(base_price * 0.9)
                discount_text = " (-10%)"
        
        if price <= 0:
            bot.send_message(chat_id, "❌ <b>Ошибка расчёта цены.</b>", parse_mode='HTML')
            return
        
        booking_id = int(datetime.now().timestamp() * 1000) % 1000000000
        booking = {
            'id': booking_id,
            'user_id': chat_id,
            'service': service,
            'date': state.get('date'),
            'times': sel,
            'duration': duration,
            'name': state.get('name', 'Unknown'),
            'email': state.get('email', ''),
            'phone': state.get('phone', 'Unknown'),
            'comment': state.get('comment', '-'),
            'price': price,
            'status': 'awaiting_payment',
            'created_at': datetime.now().isoformat(),
        }
        
        add_booking(booking)
        
        names = {
            'repet': '🎸 Репетиция',
            'studio': '🎧 Студия (самостоятельно)',
            'full': '✨ Студия со звукорежем',
        }
        
        d = datetime.strptime(state['date'], "%Y-%m-%d")
        df = d.strftime("%d.%m.%Y")
        start, end = min(sel), max(sel) + 1
        
        description = (
            f"🎵 {STUDIO_NAME}\n"
            f"📅 {df}\n"
            f"⏰ {start:02d}:00–{end:02d}:00 ({duration}ч)\n"
            f"👤 {state.get('name', '')}"
        )[:255]
        
        customer_email = state.get('email', '').strip().lower()
        customer_phone = state.get('phone', '').strip()
        phone_digits = ''.join(c for c in customer_phone if c.isdigit())
        if phone_digits.startswith('8') and len(phone_digits) == 11:
            phone_digits = '7' + phone_digits[1:]
        elif not phone_digits.startswith('7') and len(phone_digits) == 10:
            phone_digits = '7' + phone_digits
        
        receipt_items = [{
            "description": names.get(service, service)[:128],
            "quantity": 1,
            "amount": {"value": f"{price:.2f}", "currency": "RUB"},
            "vat_code": 1,
            "payment_mode": "full_payment",
            "payment_subject": "service"
        }]
        
        payment_result = create_yookassa_payment(
            amount=price,
            description=description + discount_text,
            booking_id=booking_id,
            customer_email=customer_email if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', customer_email) else None,
            customer_phone=phone_digits if len(phone_digits) == 11 and phone_digits.startswith('7') else None,
            receipt_items=receipt_items
        )
        
        if not payment_result['success']:
            bot.send_message(
                chat_id,
                f"❌ <b>Ошибка при создании платежа.</b>\n\n"
                f"{payment_result.get('error', 'Неизвестная ошибка')}\n\n"
                "Попробуй ещё раз или напиши нам:\n"
                f"📱 {STUDIO_TELEGRAM}\n"
                f"☎️ {STUDIO_CONTACT}",
                reply_markup=main_menu_keyboard(),
                parse_mode='HTML'
            )
            cancel_booking_by_id(booking_id)
            return
        
        bookings = load_bookings()
        for b in bookings:
            if b.get('id') == booking_id:
                b['yookassa_payment_id'] = payment_result['payment_id']
                b['payment_url'] = payment_result['payment_url']
                break
        save_bookings(bookings)
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💳 Оплатить", url=payment_result['payment_url']))
        kb.add(types.InlineKeyboardButton("📋 Мои бронирования", callback_data="back_to_bookings"))
        
        payment_message = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>💳 ОПЛАТА БРОНИРОВАНИЯ</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

📅 <b>Дата:</b> {df}
⏰ <b>Время:</b> {start:02d}:00–{end:02d}:00 ({duration}ч)
💰 <b>Сумма:</b> {price} ₽{discount_text}

<b>Нажми кнопку ниже для оплаты:</b>"""
        
        bot.send_message(chat_id, payment_message, reply_markup=kb, parse_mode='HTML')
        user_states.pop(chat_id, None)
        log_info(f"Платеж создан: booking_id={booking_id}, сумма={price}₽")
        
    except Exception as e:
        log_error(f"complete_booking: {str(e)}", e)
        bot.send_message(
            chat_id,
            "❌ <b>Критическая ошибка.</b>\n\n"
            "Пожалуйста, напиши нам: " + STUDIO_TELEGRAM,
            parse_mode='HTML'
        )

# ====== УВЕДОМЛЕНИЯ ======================================================

def notify_payment_success(booking):
    """Уведомление об успешной оплате"""
    try:
        chat_id = booking.get('user_id')
        if not chat_id:
            return
        
        names = {
            'repet': '🎸 Репетиция',
            'studio': '🎧 Студия (самостоятельно)',
            'full': '✨ Студия со звукорежем',
        }
        
        d = datetime.strptime(booking['date'], "%Y-%m-%d")
        df = d.strftime("%d.%m.%Y")
        
        if booking.get('times'):
            start = min(booking['times'])
            end = max(booking['times']) + 1
            t_str = f"{start:02d}:00 – {end:02d}:00 ({len(booking['times'])}ч)"
        else:
            t_str = "-"
        
        text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>✅ ОПЛАТА ПОЛУЧЕНА!</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

<b>🎵 {STUDIO_NAME}</b>
{names.get(booking['service'], booking['service'])}

📅 <b>Дата:</b> {df}
⏰ <b>Время:</b> {t_str}
💰 <b>Сумма:</b> {booking['price']} ₽
👤 <b>Имя:</b> {booking['name']}
☎️ <b>Телефон:</b> {booking['phone']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✉️ <b>Чек отправлен на email</b>

<b>🎉 Спасибо за оплату!</b>

<b>💡 Важно:</b>
   • Приходи за 15 минут до начала
   • При отмене менее чем за 24 часа — возврат 50%
   • При опоздании более 30 минут — бронь аннулируется

<b>🎵 Увидимся в студии! Твори с душой!</b>"""
        
        bot.send_message(chat_id, text, reply_markup=main_menu_keyboard(), parse_mode='HTML')
        log_info(f"Уведомление об оплате отправлено: booking_id={booking.get('id')}")
        
    except Exception as e:
        log_error(f"notify_payment_success: {str(e)}", e)

# ====== ОТМЕНА БРОНЕЙ ===================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("booking_detail_"))
def cb_booking_detail(c):
    chat_id = c.message.chat.id
    booking_id = int(c.data.replace("booking_detail_", ""))
    bookings = load_bookings()
    booking = next((b for b in bookings if b.get('id') == booking_id), None)
    
    if not booking:
        bot.answer_callback_query(c.id, "❌ Бронь не найдена")
        return
    
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Студия (самостоятельно)',
        'full': '✨ Студия со звукорежем',
    }
    
    d = datetime.strptime(booking['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    
    if booking.get('times'):
        start = min(booking['times'])
        end = max(booking['times']) + 1
        t_str = f"{start:02d}:00 – {end:02d}:00 ({len(booking['times'])}ч)"
    else:
        t_str = "-"
    
    status = booking.get('status', 'pending')
    status_text = "оплачена ✅" if status == 'paid' else "ожидает оплаты ⏳"
    
    text = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>📋 ДЕТАЛИ СЕАНСА</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

<b>{names.get(booking['service'], booking['service'])}</b>

📅 <b>Дата:</b> {df}
⏰ <b>Время:</b> {t_str}
💰 <b>Сумма:</b> {booking['price']} ₽

📌 <b>Статус:</b> {status_text}

👤 <b>Имя:</b> {booking['name']}
☎️ <b>Телефон:</b> {booking['phone']}
💬 <b>Комментарий:</b> {booking.get('comment', '-')}

<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>

<b>Что сделать?</b>"""
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_booking_{booking_id}"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_bookings"))
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb, parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_booking_"))
def cb_cancel_booking_confirm(c):
    chat_id = c.message.chat.id
    booking_id = int(c.data.replace("cancel_booking_", ""))
    
    cancelled = cancel_booking_by_id(booking_id)
    
    if cancelled:
        status = cancelled.get('status', '')
        if status == 'paid':
            bot.answer_callback_query(c.id, "⚠️ Оплаченная бронь не может быть отменена автоматически")
            bot.send_message(
                chat_id,
                "⚠️ <b>Эта бронь уже оплачена.</b>\n\n"
                "Для отмены оплаченной брони свяжись с нами:\n"
                f"📱 {STUDIO_TELEGRAM}\n"
                f"☎️ {STUDIO_CONTACT}\n\n"
                "💡 При отмене менее чем за 24 часа возврат 50%",
                reply_markup=main_menu_keyboard(),
                parse_mode='HTML'
            )
        else:
            bot.answer_callback_query(c.id, "✅ Отменена")
            bot.edit_message_text(
                "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                "<b>✅ БРОНЬ ОТМЕНЕНА</b>\n"
                "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
                "⏰ Время освобождено\n"
                "🎵 Можешь забронировать другое время\n\n"
                "<b>Спасибо, что уведомил нас!</b>",
                chat_id, c.message.message_id,
                parse_mode='HTML'
            )
            bot.send_message(chat_id, "🏠 <b>Главное меню</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')
    else:
        bot.answer_callback_query(c.id, "❌ Ошибка при отмене")

@bot.callback_query_handler(func=lambda c: c.data == "back_to_bookings")
def cb_back_to_bookings(c):
    chat_id = c.message.chat.id
    bookings = load_bookings()
    kb = bookings_keyboard(bookings, chat_id)
    
    if kb:
        bot.edit_message_text("<b>📋 Твои сеансы:</b>\n\nТапни для деталей:", chat_id, c.message.message_id, reply_markup=kb, parse_mode='HTML')

# ====== АДМИН ПАНЕЛЬ ====================================================

def is_admin(chat_id):
    """Проверка прав администратора"""
    ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
    return ADMIN_CHAT_ID > 0 and chat_id == ADMIN_CHAT_ID

@bot.message_handler(commands=['admin'])
def admin_panel_command(m):
    """Команда /admin для доступа к админ-панели"""
    chat_id = m.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ <b>Доступ запрещён</b>", parse_mode='HTML')
        return
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("➕ Добавить VIP клиента", callback_data="admin_add_vip"))
    kb.add(types.InlineKeyboardButton("➖ Удалить VIP клиента", callback_data="admin_remove_vip"))
    kb.add(types.InlineKeyboardButton("💰 Настроить цену на репетицию", callback_data="admin_set_price_repet"))
    kb.add(types.InlineKeyboardButton("📋 Список VIP клиентов", callback_data="admin_list_vip"))
    
    text = """👨‍💼 <b>АДМИН-ПАНЕЛЬ</b>

<b>Управление VIP клиентами:</b>

➕ <b>Добавить VIP</b> — добавить избранного клиента
➖ <b>Удалить VIP</b> — удалить из списка
💰 <b>Настроить цену</b> — установить индивидуальную цену на репетицию
📋 <b>Список VIP</b> — просмотреть всех VIP клиентов

<b>Выбери действие:</b>"""
    
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "admin_add_vip")
def admin_add_vip_handler(c):
    """Добавление VIP клиента"""
    chat_id = c.message.chat.id
    if not is_admin(chat_id):
        bot.answer_callback_query(c.id, "❌ Доступ запрещён")
        return
    
    user_states[chat_id] = {'admin_step': 'add_vip_id'}
    bot.edit_message_text(
        "<b>➕ ДОБАВЛЕНИЕ VIP КЛИЕНТА</b>\n\n"
        "📝 <b>Шаг 1/3:</b> Отправь Telegram ID клиента\n\n"
        "💡 <b>Как узнать ID?</b>\n"
        "   • Попроси клиента написать боту @userinfobot\n"
        "   • Или перешли сообщение от клиента боту @getidsbot\n\n"
        "Введи ID:",
        chat_id, c.message.message_id,
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('admin_step') == 'add_vip_id')
def process_admin_add_vip_id(m):
    """Обработка ID VIP клиента"""
    chat_id = m.chat.id
    if not is_admin(chat_id):
        return
    
    state = user_states.get(chat_id)
    try:
        vip_id = int(m.text.strip())
        state['admin_vip_id'] = vip_id
        state['admin_step'] = 'add_vip_name'
        bot.send_message(chat_id, "<b>➕ ДОБАВЛЕНИЕ VIP КЛИЕНТА</b>\n\n📝 <b>Шаг 2/3:</b> Введи имя клиента:", parse_mode='HTML')
    except ValueError:
        bot.send_message(chat_id, "❌ <b>Ошибка:</b> ID должен быть числом. Попробуй снова:", parse_mode='HTML')

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('admin_step') == 'add_vip_name')
def process_admin_add_vip_name(m):
    """Обработка имени VIP клиента"""
    chat_id = m.chat.id
    if not is_admin(chat_id):
        return
    
    state = user_states.get(chat_id)
    state['admin_vip_name'] = m.text.strip()
    state['admin_step'] = 'add_vip_discount'
    bot.send_message(
        chat_id,
        "<b>➕ ДОБАВЛЕНИЕ VIP КЛИЕНТА</b>\n\n"
        "📝 <b>Шаг 3/3:</b> Введи скидку в процентах (0-100)\n\n"
        "💡 Если нужна только индивидуальная цена на репетицию, введи <code>0</code>",
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('admin_step') == 'add_vip_discount')
def process_admin_add_vip_discount(m):
    """Обработка скидки VIP клиента"""
    chat_id = m.chat.id
    if not is_admin(chat_id):
        return
    
    state = user_states.get(chat_id)
    try:
        discount = int(m.text.strip())
        if discount < 0 or discount > 100:
            bot.send_message(chat_id, "❌ <b>Ошибка:</b> Скидка должна быть от 0 до 100. Попробуй снова:", parse_mode='HTML')
            return
        
        vip_id = state.get('admin_vip_id')
        vip_name = state.get('admin_vip_name')
        
        VIP_USERS[int(vip_id)] = {
            'name': vip_name,
            'discount': discount if discount > 0 else None
        }
        save_vip_users()
        
        bot.send_message(
            chat_id,
            f"✅ <b>VIP клиент добавлен!</b>\n\n"
            f"👤 <b>Имя:</b> {vip_name}\n"
            f"🆔 <b>ID:</b> <code>{vip_id}</code>\n"
            f"💎 <b>Скидка:</b> {discount}%\n\n"
            f"💡 Теперь можешь настроить индивидуальную цену на репетицию через админ-панель.",
            reply_markup=main_menu_keyboard(),
            parse_mode='HTML'
        )
        user_states.pop(chat_id, None)
    except ValueError:
        bot.send_message(chat_id, "❌ <b>Ошибка:</b> Скидка должна быть числом. Попробуй снова:", parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "admin_remove_vip")
def admin_remove_vip_handler(c):
    """Удаление VIP клиента"""
    chat_id = c.message.chat.id
    if not is_admin(chat_id):
        bot.answer_callback_query(c.id, "❌ Доступ запрещён")
        return
    
    if not VIP_USERS:
        bot.answer_callback_query(c.id, "📭 Список VIP пуст")
        return
    
    kb = types.InlineKeyboardMarkup()
    for user_id, vip_data in VIP_USERS.items():
        name = vip_data.get('name', 'Unknown')
        kb.add(types.InlineKeyboardButton(
            f"❌ {name} (ID: {user_id})",
            callback_data=f"admin_delete_vip_{user_id}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    
    bot.edit_message_text(
        "<b>➖ УДАЛЕНИЕ VIP КЛИЕНТА</b>\n\n"
        "Выбери клиента для удаления:",
        chat_id, c.message.message_id,
        reply_markup=kb,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_delete_vip_"))
def admin_delete_vip_confirm(c):
    """Подтверждение удаления VIP"""
    chat_id = c.message.chat.id
    if not is_admin(chat_id):
        bot.answer_callback_query(c.id, "❌ Доступ запрещён")
        return
    
    user_id = int(c.data.replace("admin_delete_vip_", ""))
    if user_id in VIP_USERS:
        name = VIP_USERS[user_id].get('name', 'Unknown')
        del VIP_USERS[user_id]
        save_vip_users()
        bot.answer_callback_query(c.id, "✅ VIP клиент удален")
        
        # Возвращаемся в админ-панель
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("➕ Добавить VIP клиента", callback_data="admin_add_vip"))
        kb.add(types.InlineKeyboardButton("➖ Удалить VIP клиента", callback_data="admin_remove_vip"))
        kb.add(types.InlineKeyboardButton("💰 Настроить цену на репетицию", callback_data="admin_set_price_repet"))
        kb.add(types.InlineKeyboardButton("📋 Список VIP клиентов", callback_data="admin_list_vip"))
        
        bot.edit_message_text(
            "<b>👨‍💼 АДМИН-ПАНЕЛЬ</b>\n\n"
            "<b>Управление VIP клиентами:</b>\n\n"
            "➕ <b>Добавить VIP</b> — добавить избранного клиента\n"
            "➖ <b>Удалить VIP</b> — удалить из списка\n"
            "💰 <b>Настроить цену</b> — установить индивидуальную цену на репетицию\n"
            "📋 <b>Список VIP</b> — просмотреть всех VIP клиентов\n\n"
            "<b>Выбери действие:</b>",
            chat_id, c.message.message_id,
            reply_markup=kb,
            parse_mode='HTML'
        )
    else:
        bot.answer_callback_query(c.id, "❌ Клиент не найден")

@bot.callback_query_handler(func=lambda c: c.data == "admin_set_price_repet")
def admin_set_price_repet_handler(c):
    """Настройка цены на репетицию для VIP"""
    chat_id = c.message.chat.id
    if not is_admin(chat_id):
        bot.answer_callback_query(c.id, "❌ Доступ запрещён")
        return
    
    if not VIP_USERS:
        bot.answer_callback_query(c.id, "📭 Список VIP пуст. Сначала добавь VIP клиента.")
        return
    
    kb = types.InlineKeyboardMarkup()
    for user_id, vip_data in VIP_USERS.items():
        name = vip_data.get('name', 'Unknown')
        current_price = vip_data.get('custom_price_repet', 'не установлена')
        kb.add(types.InlineKeyboardButton(
            f"💰 {name} (текущая: {current_price}₽/ч)",
            callback_data=f"admin_price_vip_{user_id}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    
    bot.edit_message_text(
        "<b>💰 НАСТРОЙКА ЦЕНЫ НА РЕПЕТИЦИЮ</b>\n\n"
        "Выбери клиента для настройки цены:",
        chat_id, c.message.message_id,
        reply_markup=kb,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_price_vip_"))
def admin_price_vip_handler(c):
    """Установка цены для VIP"""
    chat_id = c.message.chat.id
    if not is_admin(chat_id):
        bot.answer_callback_query(c.id, "❌ Доступ запрещён")
        return
    
    user_id = int(c.data.replace("admin_price_vip_", ""))
    vip_data = VIP_USERS.get(user_id)
    if not vip_data:
        bot.answer_callback_query(c.id, "❌ Клиент не найден")
        return
    
    user_states[chat_id] = {'admin_step': 'set_price_repet', 'admin_target_user': user_id}
    current_price = vip_data.get('custom_price_repet', 'не установлена')
    name = vip_data.get('name', 'Unknown')
    
    bot.edit_message_text(
        f"<b>💰 УСТАНОВКА ЦЕНЫ НА РЕПЕТИЦИЮ</b>\n\n"
        f"👤 <b>Клиент:</b> {name}\n"
        f"💰 <b>Текущая цена:</b> {current_price}₽/ч\n\n"
        f"Введи новую цену за час (только число, например: <code>500</code>)\n\n"
        f"💡 Для удаления индивидуальной цены введи <code>0</code>",
        chat_id, c.message.message_id,
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('admin_step') == 'set_price_repet')
def process_admin_set_price_repet(m):
    """Обработка установки цены на репетицию"""
    chat_id = m.chat.id
    if not is_admin(chat_id):
        return
    
    state = user_states.get(chat_id)
    try:
        price = int(m.text.strip())
        if price < 0:
            bot.send_message(chat_id, "❌ <b>Ошибка:</b> Цена не может быть отрицательной. Попробуй снова:", parse_mode='HTML')
            return
        
        target_user = state.get('admin_target_user')
        vip_data = VIP_USERS.get(target_user)
        
        if not vip_data:
            bot.send_message(chat_id, "❌ <b>Ошибка:</b> Клиент не найден.", parse_mode='HTML')
            user_states.pop(chat_id, None)
            return
        
        if price == 0:
            # Удаляем индивидуальную цену
            if 'custom_price_repet' in vip_data:
                del vip_data['custom_price_repet']
            save_vip_users()
            bot.send_message(
                chat_id,
                f"✅ <b>Индивидуальная цена удалена!</b>\n\n"
                f"👤 <b>Клиент:</b> {vip_data.get('name', 'Unknown')}\n"
                f"💰 Теперь используется стандартная цена.",
                reply_markup=main_menu_keyboard(),
                parse_mode='HTML'
            )
        else:
            # Устанавливаем индивидуальную цену
            vip_data['custom_price_repet'] = price
            save_vip_users()
            bot.send_message(
                chat_id,
                f"✅ <b>Цена установлена!</b>\n\n"
                f"👤 <b>Клиент:</b> {vip_data.get('name', 'Unknown')}\n"
                f"💰 <b>Цена на репетицию:</b> {price}₽/ч",
                reply_markup=main_menu_keyboard(),
                parse_mode='HTML'
            )
        
        user_states.pop(chat_id, None)
    except ValueError:
        bot.send_message(chat_id, "❌ <b>Ошибка:</b> Цена должна быть числом. Попробуй снова:", parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "admin_list_vip")
def admin_list_vip_handler(c):
    """Список VIP клиентов"""
    chat_id = c.message.chat.id
    if not is_admin(chat_id):
        bot.answer_callback_query(c.id, "❌ Доступ запрещён")
        return
    
    if not VIP_USERS:
        bot.edit_message_text(
            "<b>📋 СПИСОК VIP КЛИЕНТОВ</b>\n\n"
            "📭 Список пуст",
            chat_id, c.message.message_id,
            parse_mode='HTML'
        )
        return
    
    text = "<b>📋 СПИСОК VIP КЛИЕНТОВ</b>\n\n"
    for user_id, vip_data in VIP_USERS.items():
        name = vip_data.get('name', 'Unknown')
        discount = vip_data.get('discount', 0)
        custom_price = vip_data.get('custom_price_repet')
        
        text += f"👤 <b>{name}</b>\n"
        text += f"   ID: <code>{user_id}</code>\n"
        if custom_price is not None:
            text += f"   💰 Репетиция: <b>{custom_price}₽/ч</b> (индивидуальная цена)\n"
        elif discount and discount > 0:
            text += f"   💎 Скидка: <b>{discount}%</b>\n"
        else:
            text += f"   ⚙️ Настройки не заданы\n"
        text += "\n"
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb, parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "admin_back")
def admin_back_handler(c):
    """Возврат в админ-панель"""
    chat_id = c.message.chat.id
    if not is_admin(chat_id):
        bot.answer_callback_query(c.id, "❌ Доступ запрещён")
        return
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("➕ Добавить VIP клиента", callback_data="admin_add_vip"))
    kb.add(types.InlineKeyboardButton("➖ Удалить VIP клиента", callback_data="admin_remove_vip"))
    kb.add(types.InlineKeyboardButton("💰 Настроить цену на репетицию", callback_data="admin_set_price_repet"))
    kb.add(types.InlineKeyboardButton("📋 Список VIP клиентов", callback_data="admin_list_vip"))
    
    bot.edit_message_text(
        "<b>👨‍💼 АДМИН-ПАНЕЛЬ</b>\n\n"
        "<b>Управление VIP клиентами:</b>\n\n"
        "➕ <b>Добавить VIP</b> — добавить избранного клиента\n"
        "➖ <b>Удалить VIP</b> — удалить из списка\n"
        "💰 <b>Настроить цену</b> — установить индивидуальную цену на репетицию\n"
        "📋 <b>Список VIP</b> — просмотреть всех VIP клиентов\n\n"
        "<b>Выбери действие:</b>",
        chat_id, c.message.message_id,
        reply_markup=kb,
        parse_mode='HTML'
    )

# ====== FLASK И WEBHOOK ==================================================

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 10000))
RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "") or os.environ.get("RENDER_EXTERNAL_HOST", "")
PUBLIC_URL = ""
if RAILWAY_PUBLIC_DOMAIN:
    PUBLIC_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}"
elif RENDER_EXTERNAL_URL:
    PUBLIC_URL = RENDER_EXTERNAL_URL
IS_LOCAL = not PUBLIC_URL

@app.route("/", methods=["GET"])
def health():
    return "🎵 MACHATA bot работает!", 200

@app.route(f"/{API_TOKEN}/", methods=["POST"])
def webhook():
    try:
        json_data = request.get_json()
        if json_data:
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
        return "ok", 200
    except Exception as e:
        log_error(f"webhook: {str(e)}", e)
        return "error", 500

@app.route("/payment", methods=["POST"])
def yookassa_webhook():
    try:
        json_data = request.get_json()
        if not json_data:
            return "error", 400
        
        event_type = json_data.get("event")
        payment_object = json_data.get("object", {})
        payment_id = payment_object.get("id")
        payment_status = payment_object.get("status")
        metadata = payment_object.get("metadata", {})
        booking_id = metadata.get("booking_id")
        
        log_info(f"Вебхук ЮKassa: event={event_type}, payment_id={payment_id}, booking_id={booking_id}")
        
        if event_type not in ["payment.succeeded", "payment.waiting_for_capture"]:
            return "ok", 200
        
        if not booking_id:
            return "error", 400
        
        bookings = load_bookings()
        booking = None
        booking_index = None
        
        for i, b in enumerate(bookings):
            if str(b.get('id')) == str(booking_id):
                booking = b
                booking_index = i
                break
        
        if not booking:
            return "error", 404
        
        if payment_status == "succeeded":
            if booking.get('status') != 'paid':
                bookings[booking_index]['status'] = 'paid'
                bookings[booking_index]['paid_at'] = datetime.now().isoformat()
                bookings[booking_index]['yookassa_payment_id'] = payment_id
                save_bookings(bookings)
                notify_payment_success(bookings[booking_index])
        
        return "ok", 200
        
    except Exception as e:
        log_error(f"yookassa_webhook: {str(e)}", e)
        return "error", 500

# ====== ТОЧКА ВХОДА ======================================================

if __name__ == "__main__":
    # Загружаем VIP пользователей при запуске
    load_vip_users()
    
    log_info("=" * 60)
    log_info("🎵 MACHATA studio бот запущен!")
    log_info("✨ С полной поддержкой фискализации через ЮKassa")
    log_info(f"☎️ Контакт: {STUDIO_CONTACT}")
    log_info(f"📍 Telegram: {STUDIO_TELEGRAM}")
    log_info(f"👥 VIP клиентов: {len(VIP_USERS)}")
    log_info("=" * 60)
    
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        log_error("⚠️ Ключи ЮKassa не установлены!")
    else:
        log_info(f"✅ YOOKASSA_SHOP_ID: {YOOKASSA_SHOP_ID}")
        if YOOKASSA_SECRET_KEY.startswith('live_') or YOOKASSA_SECRET_KEY.startswith('test_'):
            log_info(f"✅ YOOKASSA_SECRET_KEY: {YOOKASSA_SECRET_KEY[:15]}...")
        else:
            log_error("⚠️ YOOKASSA_SECRET_KEY имеет неправильный формат")
    
    log_info("=" * 60)
    
    if IS_LOCAL:
        log_info("🚀 ЛОКАЛЬНЫЙ РЕЖИМ (polling)")
        try:
            bot.infinity_polling()
        except KeyboardInterrupt:
            log_info("✋ Бот остановлен")
        except Exception as e:
            log_error(f"Ошибка polling: {str(e)}", e)
    else:
        platform_name = "Railway" if RAILWAY_PUBLIC_DOMAIN else "Render"
        log_info(f"🌐 РЕЖИМ {platform_name} (webhook)")
        webhook_url = f"{PUBLIC_URL}/{API_TOKEN}/"
        log_info(f"Webhook URL: {webhook_url}")
        try:
            bot.remove_webhook()
            bot.set_webhook(url=webhook_url)
            log_info("✅ Webhook установлен")
            log_info(f"🚀 Flask запущен на порту {PORT}")
            app.run(host="0.0.0.0", port=PORT, debug=False)
        except Exception as e:
            log_error(f"Ошибка webhook: {str(e)}", e)
            log_info("Переключаюсь на polling...")
            try:
                bot.infinity_polling()
            except Exception as e2:
                log_error(f"Ошибка polling: {str(e2)}", e2)
