import telebot
from telebot import types
import json
import os
from datetime import datetime, timedelta
import sys
import traceback
from flask import Flask, request

# ====== КОНФИГ ======================================================
API_TOKEN = os.environ.get("API_TOKEN", "8081224286:AAHAty9YsUluB9MDF6UIsJu3lBgESEnS9Wo")
STUDIO_NAME = "MACHATA studio"
BOOKINGS_FILE = 'machata_bookings.json'
CONFIG_FILE = 'machata_config.json'
STUDIO_CONTACT = "+7 (977) 777-78-27"
STUDIO_ADDRESS = "Москва, Загородное шоссе, 1 корпус 2"
STUDIO_HOURS = "Пн–Пт 9:00–03:00 | Сб–Вс 09:00–09:00"
STUDIO_TELEGRAM = "@majesticbudan"

VIP_USERS = {
    123456789: {'name': 'Иван Рок', 'discount': 20},
    987654321: {'name': 'Мария Вокал', 'discount': 15},
    555444333: {'name': 'Миша Продакшн', 'discount': 25},
}

DEFAULT_CONFIG = {
    'prices': {
        'repet': 700,
        'studio': 800,
        'full': 1500,
    },
    'work_hours': {'start': 9, 'end': 22},
    'off_days': [5, 6],
    'payment': {
        'phone': STUDIO_CONTACT,
        'card': '2202 2000 0000 0000',
        'bank': 'Сбербанк',
    },
}

bot = telebot.TeleBot(API_TOKEN, threaded=False)
user_states = {}

# ====== ЛОГИРОВАНИЕ ==================================================
def log_info(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] ℹ️ INFO: {msg}")
    sys.stdout.flush()

def log_error(msg, exc=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] ❌ ERROR: {msg}", file=sys.stderr)
    if exc:
        print(traceback.format_exc(), file=sys.stderr)
    sys.stderr.flush()

# ====== ФАЙЛЫ ======================================================
def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                log_info(f"Конфиг загружен: {len(data)} ключей")
                return data
        log_info("Конфиг не найден, используется DEFAULT_CONFIG")
        return DEFAULT_CONFIG
    except Exception as e:
        log_error(f"load_config: {str(e)}", e)
        return DEFAULT_CONFIG

def load_bookings():
    try:
        if os.path.exists(BOOKINGS_FILE):
            with open(BOOKINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                log_info(f"Брони загружены: {len(data)} записей")
                return data
        log_info("Файл броней не найден, создаю пустой список")
        return []
    except Exception as e:
        log_error(f"load_bookings: {str(e)}", e)
        return []

def save_bookings(bookings):
    try:
        with open(BOOKINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(bookings, f, ensure_ascii=False, indent=2)
        log_info(f"Брони сохранены: {len(bookings)} записей")
    except Exception as e:
        log_error(f"save_bookings: {str(e)}", e)

def add_booking(booking):
    try:
        bookings = load_bookings()
        bookings.append(booking)
        save_bookings(bookings)
        log_info(f"Бронь добавлена: ID={booking.get('id')}, user={booking.get('user_id')}")
    except Exception as e:
        log_error(f"add_booking: {str(e)}", e)

def cancel_booking_by_id(booking_id):
    try:
        bookings = load_bookings()
        booking_found = False
        for b in bookings:
            if b.get('id') == booking_id:
                b['status'] = 'cancelled'
                booking_found = True
                break
        save_bookings(bookings)
        if booking_found:
            log_info(f"Бронь отменена: ID={booking_id}")
            return next((b for b in bookings if b.get('id') == booking_id), None)
        else:
            log_info(f"Бронь не найдена: ID={booking_id}")
            return None
    except Exception as e:
        log_error(f"cancel_booking_by_id: {str(e)}", e)
        return None

# ====== VIP ФУНКЦИИ ==================================================
def get_user_discount(chat_id):
    if chat_id in VIP_USERS:
        discount = VIP_USERS[chat_id]['discount']
        log_info(f"VIP пользователь {chat_id}: скидка {discount}%")
        return discount
    return 0

def is_vip_user(chat_id):
    return chat_id in VIP_USERS

# ====== ДАТЫ И ВРЕМЯ ================================================
def get_available_dates(days=30):
    try:
        dates = []
        config = load_config()
        off_days = config.get('off_days', [5, 6])
        for i in range(1, days + 1):
            date = datetime.now() + timedelta(days=i)
            if date.weekday() not in off_days:
                dates.append(date)
        log_info(f"Доступные даты: {len(dates)} дней")
        return dates
    except Exception as e:
        log_error(f"get_available_dates: {str(e)}", e)
        return []

def get_booked_slots(date_str, service):
    try:
        bookings = load_bookings()
        booked = []
        for booking in bookings:
            if booking.get('status') == 'cancelled':
                continue
            if booking.get('date') == date_str and booking.get('service') == service:
                booked.extend(booking.get('times', []))
        booked = sorted(set(booked))
        log_info(f"Занятые часы {date_str} ({service}): {booked}")
        return booked
    except Exception as e:
        log_error(f"get_booked_slots: {str(e)}", e)
        return []

# ====== КЛАВИАТУРЫ ==================================================
def main_menu_keyboard():
    try:
        kb = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        kb.add(types.KeyboardButton("🎙 Запись трека"))
        kb.add(types.KeyboardButton("🎸 Репетиция"))
        kb.add(types.KeyboardButton("📝 Мои бронирования"))
        kb.add(types.KeyboardButton("💰 Тарифы & акции"))
        kb.add(types.KeyboardButton("📍 Как найти"))
        kb.add(types.KeyboardButton("💬 Живой чат"))
        return kb
    except Exception as e:
        log_error(f"main_menu_keyboard: {str(e)}", e)
        return types.ReplyKeyboardMarkup()

def cancel_booking_keyboard():
    try:
        kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        kb.add(types.KeyboardButton("❌ Отменить"))
        kb.add(types.KeyboardButton("🏠 В главное меню"))
        return kb
    except Exception as e:
        log_error(f"cancel_booking_keyboard: {str(e)}", e)
        return types.ReplyKeyboardMarkup()

def service_inline_keyboard(service_type):
    try:
        kb = types.InlineKeyboardMarkup()
        if service_type == "recording":
            kb.add(types.InlineKeyboardButton(
                "🎧 Аренда студии (самостоятельная) — 800 ₽/ч",
                callback_data="service_studio"))
            kb.add(types.InlineKeyboardButton(
                "✨ Аренда со звукорежем — 1500 ₽",
                callback_data="service_full"))
        elif service_type == "repet":
            kb.add(types.InlineKeyboardButton(
                "🎸 Репетиция (700 ₽/ч)",
                callback_data="service_repet"))
        kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
        return kb
    except Exception as e:
        log_error(f"service_inline_keyboard: {str(e)}", e)
        return types.InlineKeyboardMarkup()

def dates_keyboard(page=0):
    try:
        kb = types.InlineKeyboardMarkup()
        dates = get_available_dates(30)
        per_page = 7
        start_idx = page * per_page
        end_idx = min(start_idx + per_page, len(dates))
        weekdays = {0: 'пн', 1: 'вт', 2: 'ср', 3: 'чт', 4: 'пт', 5: 'сб', 6: 'вс'}
        for d in dates[start_idx:end_idx]:
            date_str = d.strftime(f"%d.%m ({weekdays[d.weekday()]})")
            date_obj = d.strftime("%Y-%m-%d")
            kb.add(types.InlineKeyboardButton(f"📅 {date_str}", callback_data=f"date_{date_obj}"))
        nav = []
        if page > 0:
            nav.append(types.InlineKeyboardButton("◀️", callback_data=f"dates_page_{page-1}"))
        if end_idx < len(dates):
            nav.append(types.InlineKeyboardButton("▶️", callback_data=f"dates_page_{page+1}"))
        if nav:
            kb.row(*nav)
        kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_service"))
        kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
        return kb
    except Exception as e:
        log_error(f"dates_keyboard: {str(e)}", e)
        return types.InlineKeyboardMarkup()

def times_keyboard(chat_id, date_str, service):
    try:
        kb = types.InlineKeyboardMarkup(row_width=3)
        config = load_config()
        booked = get_booked_slots(date_str, service)
        selected = user_states.get(chat_id, {}).get('selected_times', [])
        buttons = []
        for h in range(config['work_hours']['start'], config['work_hours']['end']):
            if h in booked:
                buttons.append(types.InlineKeyboardButton("❌", callback_data="skip"))
            elif h in selected:
                buttons.append(types.InlineKeyboardButton(f"✅{h}", callback_data=f"timeDel_{h}"))
            else:
                buttons.append(types.InlineKeyboardButton(f"⭕{h}", callback_data=f"timeAdd_{h}"))
        for i in range(0, len(buttons), 3):
            kb.row(*buttons[i:i+3])
        if selected:
            start, end = min(selected), max(selected) + 1
            base_price = config['prices'].get(service, 0) * len(selected)
            discount_text = ""
            vip_discount = get_user_discount(chat_id)
            if vip_discount > 0:
                base_price = int(base_price * (1 - vip_discount / 100))
                discount_text = f" (VIP {vip_discount}%)"
            elif len(selected) >= 5:
                base_price = int(base_price * 0.85)
                discount_text = " (-15%)"
            elif len(selected) >= 3:
                base_price = int(base_price * 0.9)
                discount_text = " (-10%)"
            kb.row(
                types.InlineKeyboardButton("🔄 Очистить", callback_data="clear_times"),
                types.InlineKeyboardButton(f"✅ Далее → {base_price}₽{discount_text}", callback_data="confirm_times")
            )
        kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_date"))
        kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
        return kb
    except Exception as e:
        log_error(f"times_keyboard: {str(e)}", e)
        return types.InlineKeyboardMarkup()

def my_bookings_keyboard(bookings, user_id):
    try:
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
            text = f"{emoji} {date} {time_str} · {booking['price']}₽"
            kb.add(types.InlineKeyboardButton(text, callback_data=f"booking_detail_{bid}"))
        return kb
    except Exception as e:
        log_error(f"my_bookings_keyboard: {str(e)}", e)
        return None

# ====== /START И ГЛАВНОЕ МЕНЮ ========================================
def get_welcome_text(chat_id):
    try:
        vip_badge = ""
        if is_vip_user(chat_id):
            vip_name = VIP_USERS[chat_id]['name']
            vip_discount = VIP_USERS[chat_id]['discount']
            vip_badge = f"\n\n👑 Привет, {vip_name}! VIP скидка {vip_discount}%! 🎁"
        text = f"""🎵 Добро пожаловать в {STUDIO_NAME}!

Здесь создаётся музыка.
Профессиональный звук, креативная атмосфера и душа.

💡 Услуги:
🎸 Репетиция (700 ₽/час)
🎧 Студия самостоятельно (800 ₽/час)
✨ Студия со звукорежем (1500 ₽)

Быстро забронируй время и приходи творить! 🎵{vip_badge}"""
        return text
    except Exception as e:
        log_error(f"get_welcome_text: {str(e)}", e)
        return "🎵 Добро пожаловать в MACHATA studio!"

@bot.message_handler(commands=['start'])
def send_welcome(m):
    try:
        chat_id = m.chat.id
        user_states.pop(chat_id, None)
        log_info(f"START: {m.from_user.first_name} (ID: {chat_id})")
        welcome_text = get_welcome_text(chat_id)
        bot.send_message(
            chat_id,
            welcome_text,
            reply_markup=main_menu_keyboard()
        )
        log_info(f"Приветствие отправлено пользователю {chat_id}")
    except Exception as e:
        log_error(f"send_welcome для {m.chat.id}: {str(e)}", e)
        try:
            bot.send_message(m.chat.id, "❌ Ошибка при загрузке меню")
        except:
            pass

@bot.message_handler(func=lambda m: m.text == "🏠 В главное меню")
def to_main_menu(m):
    try:
        chat_id = m.chat.id
        user_states.pop(chat_id, None)
        bot.send_message(chat_id, "🏠 Главное меню", reply_markup=main_menu_keyboard())
        log_info(f"Главное меню: пользователь {chat_id}")
    except Exception as e:
        log_error(f"to_main_menu для {m.chat.id}: {str(e)}", e)

# ... (остальной код из machata_bot.py - обработчики, callbacks и т.д.)
# Скопируй весь код из твоего machata_bot.py сюда

# ====== FLASK И WEBHOOK ===============================================
app = Flask(__name__)

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

# ====== ИНИЦИАЛИЗАЦИЯ ================================================
if __name__ == "__main__":
    log_info("=" * 60)
    log_info("🎵 MACHATA studio бот запущен!")
    log_info("=== * 60)
    
    PORT = int(os.environ.get("PORT", 10000))
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
    
    if RENDER_URL:
        log_info(f"🌐 РЕЖИМ RENDER (webhook)")
        log_info(f"Webhook URL: {RENDER_URL}/{API_TOKEN}/")
        try:
            bot.remove_webhook()
            bot.set_webhook(url=f"{RENDER_URL}/{API_TOKEN}/")
            log_info("✅ Webhook установлен успешно")
        except Exception as e:
            log_error(f"Ошибка при настройке webhook: {str(e)}", e)
    
    app.run(host="0.0.0.0", port=PORT, debug=False)
