from flask import Flask, request
import telebot
from telebot import types
import json
import os
from datetime import datetime, timedelta

# ====== КОНФИГ ======================================================

API_TOKEN = '7788156343:AAEflbPqrFjVCBw-Dy_FiRiCH5K_WV5X9dY'  # ВСТАВЬ СВОЙ ТОКЕН
WEBHOOK_URL = 'https://machata-studio-bot.onrender.com/webhook'

BOOKINGS_FILE = 'machata_bookings.json'
CONFIG_FILE = 'machata_config.json'

STUDIO_NAME = "🎵 MACHATA studio — Академия звука"
STUDIO_CONTACT = "+7 (977) 777-78-27"
STUDIO_ADDRESS = "Москва, Загородное шоссе, 1 корпус 2"
STUDIO_HOURS = "Пн–Пт 9:00–22:00 | Сб–Вс 11:00–20:00"
STUDIO_TELEGRAM = "@majesticbudan"

VIP_USERS = {
    123456789: {'name': 'Иван Рок', 'discount': 20},
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

# ====== FLASK + TELEBOT =============================================

app = Flask(__name__)
bot = telebot.TeleBot(API_TOKEN, threaded=False)
user_states = {}

print("\n" + "="*60)
print("🎵 MACHATA Studio Bot (Webhook Mode)")
print("="*60)
print(f"📍 Webhook: {WEBHOOK_URL}")
print(f"☎️  Контакт: {STUDIO_CONTACT}")
print(f"📱 Telegram: {STUDIO_TELEGRAM}")
print("="*60 + "\n")

# ====== ФУНКЦИИ ХРАНИЛИЩА ==========================================

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return DEFAULT_CONFIG


def load_bookings():
    if os.path.exists(BOOKINGS_FILE):
        with open(BOOKINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_bookings(bookings):
    with open(BOOKINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(bookings, f, ensure_ascii=False, indent=2)


def add_booking(booking):
    bookings = load_bookings()
    bookings.append(booking)
    save_bookings(bookings)


def cancel_booking_by_id(booking_id):
    bookings = load_bookings()
    for b in bookings:
        if b.get('id') == booking_id:
            b['status'] = 'cancelled'
    save_bookings(bookings)
    return next((b for b in bookings if b.get('id') == booking_id), None)


def get_user_discount(chat_id):
    if chat_id in VIP_USERS:
        return VIP_USERS[chat_id]['discount']
    return 0


def is_vip_user(chat_id):
    return chat_id in VIP_USERS


def get_available_dates(days=30):
    dates = []
    config = load_config()
    off_days = config.get('off_days', [5, 6])
    for i in range(1, days + 1):
        date = datetime.now() + timedelta(days=i)
        if date.weekday() not in off_days:
            dates.append(date)
    return dates


def get_booked_slots(date_str, service):
    bookings = load_bookings()
    booked = []
    for booking in bookings:
        if booking.get('status') == 'cancelled':
            continue
        if booking['date'] == date_str and booking['service'] == service:
            booked.extend(booking.get('times', []))
    return booked


# ====== КЛАВИАТУРЫ ==================================================

def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    kb.add(types.KeyboardButton("🎙 Запись трека"))
    kb.add(types.KeyboardButton("🎸 Репетиция"))
    kb.add(types.KeyboardButton("📝 Мои бронирования"))
    kb.add(types.KeyboardButton("💰 Тарифы"))
    kb.add(types.KeyboardButton("📍 Адрес"))
    kb.add(types.KeyboardButton("💬 Контакты"))
    return kb


def cancel_booking_keyboard():
    kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Отменить"))
    kb.add(types.KeyboardButton("🏠 Меню"))
    return kb


def service_inline_keyboard(service_type):
    kb = types.InlineKeyboardMarkup()
    if service_type == "recording":
        kb.add(types.InlineKeyboardButton("🎧 Аренда студии (самостоятельно) — 800 ₽/ч", callback_data="service_studio"))
        kb.add(types.InlineKeyboardButton("✨ Со звукорежем — 1500 ₽", callback_data="service_full"))
    elif service_type == "repet":
        kb.add(types.InlineKeyboardButton("🎸 Репетиция — 700 ₽/ч", callback_data="service_repet"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return kb


def dates_keyboard(page=0):
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
    
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return kb


def times_keyboard(chat_id, date_str, service):
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
            buttons.append(types.InlineKeyboardButton(f"{h}", callback_data=f"timeAdd_{h}"))
    
    for i in range(0, len(buttons), 3):
        kb.row(*buttons[i:i+3])
    
    if selected:
        start, end = min(selected), max(selected) + 1
        base_price = config['prices'].get(service, 0) * len(selected)
        price = base_price
        discount = ""
        
        vip_discount = get_user_discount(chat_id)
        if vip_discount > 0:
            price = int(base_price * (1 - vip_discount / 100))
            discount = f" (VIP {vip_discount}%)"
        elif len(selected) >= 5:
            price = int(base_price * 0.85)
            discount = " (-15%)"
        elif len(selected) >= 3:
            price = int(base_price * 0.9)
            discount = " (-10%)"
        
        kb.row(
            types.InlineKeyboardButton("🔄 Очистить", callback_data="clear_times"),
            types.InlineKeyboardButton(f"✅ Далее {price}₽{discount}", callback_data="confirm_times")
        )
    
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return kb


def my_bookings_keyboard(bookings, user_id):
    kb = types.InlineKeyboardMarkup()
    user_bookings = [b for b in bookings if b.get('user_id') == user_id and b.get('status') != 'cancelled']
    if not user_bookings:
        return None
    
    for booking in user_bookings[:10]:
        bid = booking.get('id')
        date = booking.get('date', '')
        if booking.get('times'):
            start = min(booking['times'])
            time_str = f"{start:02d}:00"
        else:
            time_str = ""
        text = f"📋 {date} {time_str} · {booking['price']}₽"
        kb.add(types.InlineKeyboardButton(text, callback_data=f"booking_detail_{bid}"))
    
    return kb


# ====== /START И ГЛАВНОЕ МЕНЮ ========================================

def get_welcome_text(chat_id):
    vip_badge = ""
    if is_vip_user(chat_id):
        vip_name = VIP_USERS[chat_id]['name']
        vip_discount = VIP_USERS[chat_id]['discount']
        vip_badge = f"\n\n👑 Привет, {vip_name}! VIP скидка {vip_discount}%! 🎁"
    
    text = f"""
🎵 {STUDIO_NAME}!

🎸 Репетиция — 700 ₽/час
🎧 Аренда студии — 800 ₽/час
✨ Со звукорежем — 1500 ₽

💚 Скидки: 3ч (-10%), 5+ч (-15%){vip_badge}
"""
    return text


@bot.message_handler(commands=['start'])
def send_welcome(m):
    chat_id = m.chat.id
    user_states.pop(chat_id, None)
    print(f"👤 /start от {m.from_user.first_name or 'User'} | ID: {chat_id}")
    bot.send_message(chat_id, get_welcome_text(chat_id), reply_markup=main_menu_keyboard())


@bot.message_handler(func=lambda m: m.text == "🏠 Меню")
def to_main_menu(m):
    chat_id = m.chat.id
    user_states.pop(chat_id, None)
    bot.send_message(chat_id, "🏠 Главное меню", reply_markup=main_menu_keyboard())


# ====== ОСНОВНЫЕ КОМАНДЫ ============================================

@bot.message_handler(func=lambda m: m.text == "🎙 Запись трека")
def book_recording(m):
    chat_id = m.chat.id
    text = "🎙 Запись в студии\n\nВыбери формат:"
    bot.send_message(chat_id, text, reply_markup=service_inline_keyboard("recording"))
    user_states[chat_id] = {'step': 'service', 'type': 'recording'}


@bot.message_handler(func=lambda m: m.text == "🎸 Репетиция")
def book_repet(m):
    chat_id = m.chat.id
    text = "🎸 Репетиция\n\nБронируем?"
    kb = service_inline_keyboard("repet")
    bot.send_message(chat_id, text, reply_markup=kb)
    user_states[chat_id] = {'step': 'service', 'type': 'repet'}


@bot.message_handler(func=lambda m: m.text == "❌ Отменить")
def cancel_booking(m):
    chat_id = m.chat.id
    user_states.pop(chat_id, None)
    bot.send_message(chat_id, "❌ Отменено.", reply_markup=main_menu_keyboard())


@bot.message_handler(func=lambda m: m.text == "📝 Мои бронирования")
def my_bookings(m):
    chat_id = m.chat.id
    bookings = load_bookings()
    user_bookings = [b for b in bookings if b.get('user_id') == chat_id and b.get('status') != 'cancelled']
    if not user_bookings:
        bot.send_message(chat_id, "📭 Нет броней. Давай создадим первую!", reply_markup=main_menu_keyboard())
        return
    
    text = "📋 Твои сеансы:"
    kb = my_bookings_keyboard(bookings, chat_id)
    bot.send_message(chat_id, text, reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "💰 Тарифы")
def show_prices(m):
    chat_id = m.chat.id
    vip_info = ""
    if is_vip_user(chat_id):
        vip_discount = VIP_USERS[chat_id]['discount']
        vip_info = f"\n\n👑 Твоя VIP скидка: {vip_discount}%! 🎁"
    
    text = f"""
💰 ТАРИФЫ {STUDIO_NAME}

🎸 РЕПЕТИЦИЯ
   700 ₽/час

🎧 АРЕНДА СТУДИИ
   800 ₽/час

✨ СО ЗВУКОРЕЖЕМ
   1500 ₽

🎁 СКИДКИ:
   3–4ч: -10%
   5+ч: -15%{vip_info}
"""
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())


@bot.message_handler(func=lambda m: m.text == "📍 Адрес")
def location(m):
    text = f"""
📍 {STUDIO_NAME}
{STUDIO_ADDRESS}

🕐 {STUDIO_HOURS}
☎️ {STUDIO_CONTACT}
"""
    bot.send_message(m.chat.id, text, reply_markup=main_menu_keyboard())


@bot.message_handler(func=lambda m: m.text == "💬 Контакты")
def live_chat(m):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📱 Telegram", url=f"https://t.me/{STUDIO_TELEGRAM.replace('@', '')}"))
    text = f"""
💬 СВЯЖИСЬ С НАМИ

📱 Telegram: {STUDIO_TELEGRAM}
☎️ {STUDIO_CONTACT}
"""
    bot.send_message(m.chat.id, text, reply_markup=kb)


# ====== CALLBACK: СЕРВИС ============================================

@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cb_cancel(c):
    chat_id = c.message.chat.id
    user_states.pop(chat_id, None)
    bot.edit_message_text("❌ Отменено", chat_id, c.message.message_id)
    bot.send_message(chat_id, "Главное меню", reply_markup=main_menu_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("service_"))
def cb_service(c):
    chat_id = c.message.chat.id
    service = c.data.replace("service_", "")
    user_states[chat_id] = {'step': 'date', 'service': service, 'selected_times': []}
    
    text = "ШАГ 1/4: Дату? 👇"
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=dates_keyboard(0))


@bot.callback_query_handler(func=lambda c: c.data.startswith("dates_page_"))
def cb_dates_page(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state:
        return
    page = int(c.data.replace("dates_page_", ""))
    text = "ШАГ 1/4: Выбери дату 👇"
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=dates_keyboard(page))


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
    
    text = f"ШАГ 2/4: {df}\n\nЧасы? (выбери несколько) 👇"
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, date_str, state['service']))


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
    
    text = f"ШАГ 2/4: {df}\nВыбрано: {len(sel)} ч"
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, state['date'], state['service']))


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
    
    text = f"ШАГ 2/4: {df}\nВыбрано: {len(sel) if sel else 0} ч"
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, state['date'], state['service']))


@bot.callback_query_handler(func=lambda c: c.data == "clear_times")
def cb_clear_times(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if state:
        state['selected_times'] = []
    d = datetime.strptime(state['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    text = f"ШАГ 2/4: {df}\nОчищено ✅"
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, state['date'], state['service']))


@bot.callback_query_handler(func=lambda c: c.data == "confirm_times")
def cb_confirm_times(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state or not state.get('selected_times'):
        bot.answer_callback_query(c.id, "❌ Выбери хотя бы 1 час")
        return
    
    state['step'] = 'name'
    text = "ШАГ 3/4: Твоё имя? 👇"
    bot.edit_message_text(text, chat_id, c.message.message_id)
    bot.send_message(chat_id, "Введи имя:", reply_markup=cancel_booking_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == "skip")
def cb_skip(c):
    bot.answer_callback_query(c.id, "⚠️ Занято")


@bot.callback_query_handler(func=lambda c: c.data.startswith("booking_detail_"))
def cb_booking_detail(c):
    chat_id = c.message.chat.id
    booking_id = int(c.data.replace("booking_detail_", ""))
    bookings = load_bookings()
    booking = next((b for b in bookings if b.get('id') == booking_id), None)
    
    if not booking:
        bot.answer_callback_query(c.id, "❌ Не найдено")
        return
    
    d = datetime.strptime(booking['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    if booking.get('times'):
        start = min(booking['times'])
        end = max(booking['times']) + 1
        t_str = f"{start:02d}:00 – {end:02d}:00"
    else:
        t_str = "-"
    
    text = f"""
📋 {df}
⏰ {t_str}
💰 {booking['price']} ₽
👤 {booking['name']}
"""
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_booking_{booking_id}"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_bookings"))
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_booking_"))
def cb_cancel_booking_confirm(c):
    chat_id = c.message.chat.id
    booking_id = int(c.data.replace("cancel_booking_", ""))
    cancelled = cancel_booking_by_id(booking_id)
    
    if cancelled:
        bot.answer_callback_query(c.id, "✅ Отменена")
        bot.edit_message_text("✅ Отменена!", chat_id, c.message.message_id)
        bot.send_message(chat_id, "Главное меню", reply_markup=main_menu_keyboard())
    else:
        bot.answer_callback_query(c.id, "❌ Ошибка")


@bot.callback_query_handler(func=lambda c: c.data == "back_to_bookings")
def cb_back_to_bookings(c):
    chat_id = c.message.chat.id
    bookings = load_bookings()
    text = "📋 Твои сеансы:"
    kb = my_bookings_keyboard(bookings, chat_id)
    if kb:
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb)


# ====== ТЕКСТОВЫЕ ВВОДЫ =============================================

@bot.message_handler(func=lambda m: m.chat.id in user_states)
def process_text_steps(m):
    chat_id = m.chat.id
    state = user_states.get(chat_id)
    if not state:
        return
    
    step = state.get('step')
    
    if step == 'name':
        state['name'] = m.text
        state['step'] = 'phone'
        bot.send_message(chat_id, "ШАГ 4/4: Телефон? (+7XXXXXXXXXX)", reply_markup=cancel_booking_keyboard())
    
    elif step == 'phone':
        phone = m.text.strip()
        phone_digits = ''.join(c for c in phone if c.isdigit())
        
        if len(phone_digits) != 11:
            bot.send_message(chat_id, "❌ Ошибка! Нужно 11 цифр.\n\nПример: +79990000000", reply_markup=cancel_booking_keyboard())
            return
        
        state['phone'] = m.text
        complete_booking(chat_id)


# ====== ЗАВЕРШЕНИЕ БРОНИ ============================================

def complete_booking(chat_id):
    state = user_states.get(chat_id)
    if not state:
        return
    
    config = load_config()
    sel = state['selected_times']
    service = state['service']
    duration = len(sel)
    
    if service == 'full':
        base_price = config['prices']['full']
    else:
        base_price = config['prices'][service] * duration
    
    price = base_price
    discount_text = ""
    
    vip_discount = get_user_discount(chat_id)
    if vip_discount > 0:
        price = int(base_price * (1 - vip_discount / 100))
        discount_text = f" (VIP {vip_discount}%)"
    elif duration >= 5:
        price = int(price * 0.85)
        discount_text = " (-15%)"
    elif duration >= 3:
        price = int(price * 0.9)
        discount_text = " (-10%)"
    
    booking_id = int(datetime.now().timestamp())
    booking = {
        'id': booking_id,
        'user_id': chat_id,
        'service': service,
        'date': state['date'],
        'times': sel,
        'duration': duration,
        'name': state['name'],
        'phone': state['phone'],
        'price': price,
        'status': 'pending',
        'created_at': datetime.now().isoformat(),
    }
    add_booking(booking)
    
    d = datetime.strptime(state['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    start, end = min(sel), max(sel) + 1
    
    text = f"""
✅ ПОДТВЕРЖДЕНО!

{STUDIO_NAME}

{df}
{start:02d}:00 – {end:02d}:00
{duration} ч

💰 {price} ₽{discount_text}

👤 {state['name']}
☎️ {state['phone']}

Спасибо! 🎵
"""
    
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())
    user_states.pop(chat_id, None)


# ====== FLASK ENDPOINT: WEBHOOK ======================================

@app.route('/webhook', methods=['POST'])
def webhook():
    """Получение обновлений от Telegram"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        
        try:
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        except Exception as e:
            print(f"❌ Ошибка webhook: {e}")
            return '', 500
    return 'Error', 403


@app.route('/', methods=['GET'])
def index():
    """Главная страница"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>MACHATA Studio Bot</title>
        <style>
            body { font-family: sans-serif; text-align: center; padding: 40px; background: #f5f5f5; }
            h1 { color: #208080; }
            .status { background: white; padding: 20px; border-radius: 8px; max-width: 600px; margin: 20px auto; }
        </style>
    </head>
    <body>
        <h1>🎵 MACHATA Studio Bot</h1>
        <div class="status">
            <p>✅ Бот работает!</p>
            <p>Telegram: <a href="https://t.me/majesticbudan">@majesticbudan</a></p>
            <p>Webhook: https://machata-studio-bot.onrender.com/webhook</p>
        </div>
    </body>
    </html>
    ''', 200


@app.route('/info', methods=['GET'])
def info():
    """Информация о боте"""
    try:
        webhook_info = bot.get_webhook_info()
        return f"✅ Работает<br>URL: {webhook_info.url}", 200
    except Exception as e:
        return f"❌ Ошибка: {str(e)}", 500


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return 'OK', 200


# ====== ЗАПУСК ======================================================

if __name__ == '__main__':
    # Для локального запуска
    app.run(host='0.0.0.0', port=10000, debug=False)
