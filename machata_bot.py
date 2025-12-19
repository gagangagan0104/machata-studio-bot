import telebot
from telebot import types
import json
import os
from datetime import datetime, timedelta

# ====== КОНФИГ ======================================================

API_TOKEN = 'ТУТ_ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER'
BOOKINGS_FILE = 'machata_bookings.json'
CONFIG_FILE = 'machata_config.json'

STUDIO_NAME = "🎵 MACHATA studio — Академия звука"
STUDIO_CONTACT = "+7 (977) 777-78-27"
STUDIO_ADDRESS = "Москва, Загородное шоссе, 1 корпус 2"
STUDIO_HOURS = "Пн–Пт 9:00–22:00 | Сб–Вс 11:00–20:00"
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

bot = telebot.TeleBot(API_TOKEN)
user_states = {}


# ====== ФАЙЛЫ ======================================================

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


# ====== VIP ФУНКЦИИ ==================================================

def get_user_discount(chat_id):
    if chat_id in VIP_USERS:
        return VIP_USERS[chat_id]['discount']
    return 0


def is_vip_user(chat_id):
    return chat_id in VIP_USERS


# ====== ДАТЫ И ВРЕМЯ ================================================

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
    kb.add(types.KeyboardButton("💰 Тарифы & акции"))
    kb.add(types.KeyboardButton("📍 Как найти"))
    kb.add(types.KeyboardButton("💬 Живой чат"))
    return kb


def cancel_booking_keyboard():
    kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Отменить"))
    kb.add(types.KeyboardButton("🏠 В главное меню"))
    return kb


def service_inline_keyboard(service_type):
    kb = types.InlineKeyboardMarkup()
    
    if service_type == "recording":
        kb.add(types.InlineKeyboardButton(
            "🎧 Аренда студии (самостоятельная работа) — 800 ₽/ч", callback_data="service_studio"))
        kb.add(types.InlineKeyboardButton(
            "✨ Аренда студии со звукорежем — 1500 ₽", 
            callback_data="service_full"))
    elif service_type == "repet":
        kb.add(types.InlineKeyboardButton(
            "🎸 Репетиция (700 ₽/ч)", callback_data="service_repet"))
    
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
    
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_service"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return kb


def times_keyboard(chat_id, date_str, service):
    kb = types.InlineKeyboardMarkup(row_width=3)
    config = load_config()
    booked = get_booked_slots(date_str, service)
    selected = user_states.get(chat_id, {}).get('selected_times', [])
    
    buttons = []
    for h in range(config['work_hours']['start'], config['work_hours']['end']):
        time_str = f"{h:02d}:00"
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
        config = load_config()
        base_price = config['prices'].get(service, 0) * len(selected)
        discount = ""
        discount_percent = 0
        
        vip_discount = get_user_discount(chat_id)
        if vip_discount > 0:
            discount_percent = vip_discount
            base_price = int(base_price * (1 - vip_discount / 100))
            discount = f" (VIP скидка {vip_discount}%)"
        elif len(selected) >= 5:
            discount_percent = 15
            base_price = int(base_price * 0.85)
            discount = " (скидка за 5+ часов: -15%)"
        elif len(selected) >= 3:
            discount_percent = 10
            base_price = int(base_price * 0.9)
            discount = " (скидка за 3+ часа: -10%)"
        
        kb.row(
            types.InlineKeyboardButton("🔄 Очистить", callback_data="clear_times"),
            types.InlineKeyboardButton(f"✅ Далее → {base_price}₽{discount}", callback_data="confirm_times")
        )
    
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_date"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return kb


def my_bookings_keyboard(bookings, user_id):
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


# ====== /START И ГЛАВНОЕ МЕНЮ ========================================

def get_welcome_text(chat_id):
    vip_badge = ""
    if is_vip_user(chat_id):
        vip_name = VIP_USERS[chat_id]['name']
        vip_discount = VIP_USERS[chat_id]['discount']
        vip_badge = f"\n\n👑 Привет, {vip_name}! У тебя включена VIP скидка {vip_discount}%! 🎁"
    
    text = f"""
🎵 Добро пожаловать в {STUDIO_NAME}!

Здесь создаётся музыка.
Профессиональный звук, креативная атмосфера и душа.

💡 Что мы предлагаем:
🎸 Репетиционная комната (700 ₽/час)
🎧 Аренда студии для самостоятельной работы (800 ₽/час)
✨ Аренда студии со звукорежем (1500 ₽)

Быстро забронируй время и приходи творить 🎵{vip_badge}
"""
    return text


@bot.message_handler(commands=['start'])
def send_welcome(m):
    chat_id = m.chat.id
    user_states.pop(chat_id, None)
    print(f"👤 Пользователь: {m.from_user.first_name} | ID: {chat_id}")
    bot.send_message(chat_id, get_welcome_text(chat_id), reply_markup=main_menu_keyboard())


@bot.message_handler(func=lambda m: m.text == "🏠 В главное меню")
def to_main_menu(m):
    chat_id = m.chat.id
    user_states.pop(chat_id, None)
    bot.send_message(chat_id, "🏠 Главное меню", reply_markup=main_menu_keyboard())


# ====== ОСНОВНЫЕ КОМАНДЫ ============================================

@bot.message_handler(func=lambda m: m.text == "🎙 Запись трека")
def book_recording(m):
    chat_id = m.chat.id
    text = """
🎙 Запись в студии

Профессиональная аппаратура, звукорежиссёр, полный контроль звука.

Формат:
"""
    bot.send_message(chat_id, text, reply_markup=service_inline_keyboard("recording"))
    user_states[chat_id] = {'step': 'service', 'type': 'recording'}


@bot.message_handler(func=lambda m: m.text == "🎸 Репетиция")
def book_repet(m):
    chat_id = m.chat.id
    text = """
🎸 Репетиционная комната

Обработанная акустика, инструменты, уютная атмосфера.
Кофе, чай, диван — бесплатно 😎

Бронируем?
"""
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
    user_bookings = [
        b for b in bookings 
        if b.get('user_id') == chat_id and b.get('status') != 'cancelled'
    ]
    if not user_bookings:
        bot.send_message(chat_id, "📭 Пока нет броней. Давай создадим первую! 🎵", 
                        reply_markup=main_menu_keyboard())
        return
    
    text = "📋 Твои сеансы:\n\nТапни, чтобы увидеть детали и отменить:"
    kb = my_bookings_keyboard(bookings, chat_id)
    bot.send_message(chat_id, text, reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "💰 Тарифы & акции")
def show_prices(m):
    chat_id = m.chat.id
    vip_info = ""
    if is_vip_user(chat_id):
        vip_discount = VIP_USERS[chat_id]['discount']
        vip_info = f"\n\n👑 ТВОЯ VIP СКИДКА: {vip_discount}% на все услуги! 🎁"
    
    text = f"""
💰 ТАРИФЫ {STUDIO_NAME}

🎸 РЕПЕТИЦИЯ
   700 ₽/час
   ✓ Репетиционная комната с хорошей акустикой
   ✓ Инструменты и оборудование
   ✓ Кофе/чай/вода — бесплатно

🎧 АРЕНДА СТУДИИ (САМОСТОЯТЕЛЬНАЯ РАБОТА)
   800 ₽/час
   ✓ Профессиональное оборудование
   ✓ Звукоизоляция и хорошая акустика
   ✓ Работай в своём темпе
   ✓ Экспорт в MP3, WAV, FLAC

✨ АРЕНДА СТУДИИ СО ЗВУКОРЕЖЕМ
   1500 ₽
   ✓ Профессиональная запись инструментов/вокала
   ✓ Помощь звукорежиссёра при записи
   ✓ Микширование и обработка звука
   ✓ Полная готовность к релизу

🎁 СКИДКИ:
   💚 3–4 часа подряд: -10%
   💚 5+ часов: -15%

📌 Первое посещение? Приходи за 15 минут раньше — покажем студию!{vip_info}
"""
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())


@bot.message_handler(func=lambda m: m.text == "📍 Как найти")
def location(m):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🗺️ Яндекс.Карты", 
                                     url="https://maps.yandex.ru/?text=MACHATA+studio+Загородное+шоссе+1+2+Москва"))
    kb.add(types.InlineKeyboardButton("🗺️ 2ГИС", 
                                     url="https://2gis.ru/moscow/search/MACHATA%20studio"))
    
    text = f"""
📍 РАСПОЛОЖЕНИЕ

{STUDIO_NAME}
Адрес: {STUDIO_ADDRESS}

🚇 Метро: [5 минут пешком]
🅿️ Парковка: [есть во дворе]

🕐 РЕЖИМ РАБОТЫ:
{STUDIO_HOURS}

☎️ КОНТАКТЫ:
Телефон: {STUDIO_CONTACT}
Telegram: {STUDIO_TELEGRAM}

💬 Быстрее всего отвечаем в Telegram 👍

Открыть маршрут 👇
"""
    bot.send_message(m.chat.id, text, reply_markup=kb)
    kb_main = main_menu_keyboard()
    bot.send_message(m.chat.id, "Главное меню", reply_markup=kb_main)


@bot.message_handler(func=lambda m: m.text == "💬 Живой чат")
def live_chat(m):
    kb = types.InlineKeyboardMarkup()
    
    kb.add(types.InlineKeyboardButton("📱 Telegram профиль", url=f"https://t.me/{STUDIO_TELEGRAM.replace('@', '')}"))
    kb.add(types.InlineKeyboardButton("💬 Написать сообщение", url=f"https://t.me/{STUDIO_TELEGRAM.replace('@', '')}?start=chat"))
    
    text = f"""
💬 СВЯЖИСЬ С НАМИ

Быстрые ответы на вопросы:

📱 Telegram: {STUDIO_TELEGRAM}
☎️ Звонок: {STUDIO_CONTACT}
💌 Email: hello@machata.studio

Обычно отвечаем в течение 15 минут 🚀

Часто спрашивают:
— Когда свободно?
— Могу ли я принести свою аппаратуру?
— Есть ли парковка?
— Сколько человек влезет в репетиционную?

Контакт 👇
"""
    bot.send_message(m.chat.id, text, reply_markup=kb)
    kb_main = main_menu_keyboard()
    bot.send_message(m.chat.id, "Главное меню", reply_markup=kb_main)


# ====== CALLBACK: СЕРВИС ============================================

@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cb_cancel(c):
    chat_id = c.message.chat.id
    user_states.pop(chat_id, None)
    bot.edit_message_text("❌ Отменено", chat_id, c.message.message_id)
    bot.send_message(chat_id, "Вернёмся в главное меню", reply_markup=main_menu_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("service_"))
def cb_service(c):
    chat_id = c.message.chat.id
    service = c.data.replace("service_", "")
    user_states[chat_id] = {'step': 'date', 'service': service, 'selected_times': []}
    
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Аренда студии (самостоятельная)',
        'full': '✨ Аренда со звукорежем',
    }
    
    text = f"""
— — — 🎵 ШАГ 1/4 — — —

{names[service]} выбрана.

Дату 👇
"""
    bot.edit_message_text(text, chat_id, c.message.message_id, 
                         reply_markup=dates_keyboard(0))


@bot.callback_query_handler(func=lambda c: c.data.startswith("dates_page_"))
def cb_dates_page(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state:
        return
    page = int(c.data.replace("dates_page_", ""))
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Аренда студии (самостоятельная)',
        'full': '✨ Аренда со звукорежем',
    }
    text = f"""
— — — 🎵 ШАГ 1/4 — — —

{names[state['service']]} выбрана.

Дату 👇
"""
    bot.edit_message_text(text, chat_id, c.message.message_id, 
                         reply_markup=dates_keyboard(page))


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
    
    text = f"""
— — — 🎵 ШАГ 2/4 — — —

Дата: {df}

Часы 👇
Выбирай несколько подряд для скидки 💚

⭕ свободно | ✅ выбрано | ❌ занято
"""
    bot.edit_message_text(text, chat_id, c.message.message_id,
                         reply_markup=times_keyboard(chat_id, date_str, state['service']))


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
    
    text = f"""
— — — 🎵 ШАГ 2/4 — — —

Дата: {df}
Выбрано: {len(sel)} ч ({start:02d}:00 – {end:02d}:00)

Продолжай или ✅ Далее 👇
"""
    bot.edit_message_text(text, chat_id, c.message.message_id,
                         reply_markup=times_keyboard(chat_id, state['date'], state['service']))


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
        text = f"""
— — — 🎵 ШАГ 2/4 — — —

Дата: {df}
Выбрано: {len(sel)} ч ({start:02d}:00 – {end:02d}:00)

Продолжай или ✅ Далее 👇
"""
    else:
        text = f"""
— — — 🎵 ШАГ 2/4 — — —

Дата: {df}

Часы 👇
"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id,
                         reply_markup=times_keyboard(chat_id, state['date'], state['service']))


@bot.callback_query_handler(func=lambda c: c.data == "clear_times")
def cb_clear_times(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if state:
        state['selected_times'] = []
    d = datetime.strptime(state['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    text = f"""
— — — 🎵 ШАГ 2/4 — — —

Дата: {df}
Выбор очищен ✅

Часы 👇
"""
    bot.edit_message_text(text, chat_id, c.message.message_id,
                         reply_markup=times_keyboard(chat_id, state['date'], state['service']))


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
        'studio': '🎧 Аренда студии (самостоятельная)',
        'full': '✨ Аренда со звукорежем',
    }
    text = f"""
— — — 🎵 ШАГ 1/4 — — —

{names[state['service']]} выбрана.

Дату 👇
"""
    bot.edit_message_text(text, chat_id, c.message.message_id,
                         reply_markup=dates_keyboard(0))


@bot.callback_query_handler(func=lambda c: c.data == "back_to_service")
def cb_back_to_service(c):
    chat_id = c.message.chat.id
    service_type = user_states.get(chat_id, {}).get('type', 'repet')
    user_states[chat_id] = {'step': 'service', 'type': service_type, 'selected_times': []}
    
    if service_type == 'recording':
        text = "🎙 Запись в студии\n\nФормат:"
        kb = service_inline_keyboard("recording")
    else:
        text = "🎸 Репетиционная комната\n\nБронируем:"
        kb = service_inline_keyboard("repet")
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "confirm_times")
def cb_confirm_times(c):
    chat_id = c.message.chat.id
    state = user_states.get(chat_id)
    if not state or not state.get('selected_times'):
        bot.answer_callback_query(c.id, "❌ Выбери хотя бы один час")
        return
    
    state['step'] = 'name'
    text = """
— — — 🎵 ШАГ 3/4 — — —

Как к тебе обращаться?
(имя, ник или проект)

👤 Введи 👇
"""
    bot.edit_message_text(text, chat_id, c.message.message_id)
    bot.send_message(chat_id, "Твоё имя или ник:", reply_markup=cancel_booking_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == "skip")
def cb_skip(c):
    bot.answer_callback_query(c.id, "⚠️ Это время занято")


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
        bot.send_message(chat_id, 
                        "☎️ Номер телефона для подтверждения:\nПример: +7 (999) 000–00–00 или 79990000000",
                        reply_markup=cancel_booking_keyboard())
    
    elif step == 'phone':
        phone = m.text.strip()
        phone_digits = ''.join(c for c in phone if c.isdigit())
        
        if len(phone_digits) != 11:
            bot.send_message(chat_id,
                            "❌ Ошибка! Номер должен содержать 11 цифр.\n\n☎️ Пример: +7 (999) 000–00–00 или 79990000000",
                            reply_markup=cancel_booking_keyboard())
            return
        
        state['phone'] = m.text
        state['step'] = 'comment'
        
        kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        kb.add(types.KeyboardButton("⏭️ Пропустить"))
        kb.add(types.KeyboardButton("❌ Отменить"))
        kb.add(types.KeyboardButton("🏠 В главное меню"))
        
        bot.send_message(chat_id,
                        "💬 Что записываешь или репетируешь?\n\n(Или пропусти этот шаг)",
                        reply_markup=kb)
    
    elif step == 'comment':
        if m.text == "⏭️ Пропустить":
            comment = "-"
        else:
            comment = m.text
        
        state['comment'] = comment
        complete_booking(chat_id)


# ====== ЗАВЕРШЕНИЕ БРОНИ ============================================

def complete_booking(chat_id):
    state = user_states.get(chat_id)
    if not state:
        return
    
    config = load_config()
    sel = state['selected_times']
    duration = len(sel)
    service = state['service']
    
    if service == 'full':
        base_price = config['prices']['full']
    else:
        base_price = config['prices'][service] * duration
    
    price = base_price
    discount_text = ""
    
    vip_discount = get_user_discount(chat_id)
    if vip_discount > 0:
        price = int(base_price * (1 - vip_discount / 100))
        discount_text = f" (VIP скидка {vip_discount}%)"
    elif duration >= 5:
        price = int(price * 0.85)
        discount_text = " (скидка 15%)"
    elif duration >= 3:
        price = int(price * 0.9)
        discount_text = " (скидка 10%)"
    
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
        'comment': state['comment'],
        'price': price,
        'status': 'pending',
        'created_at': datetime.now().isoformat(),
    }
    add_booking(booking)
    
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Аренда студии (самостоятельная)',
        'full': '✨ Аренда со звукорежем',
    }
    d = datetime.strptime(state['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    start, end = min(sel), max(sel) + 1
    
    cfg = load_config()
    pay_info = cfg.get('payment', {})
    
    text = f"""
✅ БРОНЬ ПОДТВЕРЖДЕНА!

🎵 {STUDIO_NAME}

— — — — — — — — — — —

📋 ДЕТАЛИ:
  {names[service]}
  📅 {df}
  ⏰ {start:02d}:00 – {end:02d}:00
  ⏱️ {duration} ч
  💰 {price} ₽{discount_text}

👤 {state['name']}
☎️ {state['phone']}
💬 {state['comment']}

— — — — — — — — — — —

💳 ОПЛАТА:
📱 СБП / перевод:
  {pay_info.get('phone', STUDIO_CONTACT)}
  {pay_info.get('bank', 'Сбербанк')}
  {pay_info.get('card', '****')}

💡 Приходи за 15 минут раньше — покажем студию!

🙏 Спасибо за доверие!
"""
    
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())
    user_states.pop(chat_id, None)


# ====== ОТМЕНА БРОНИ ================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("booking_detail_"))
def cb_booking_detail(c):
    chat_id = c.message.chat.id
    booking_id = int(c.data.replace("booking_detail_", ""))
    bookings = load_bookings()
    booking = next((b for b in bookings if b.get('id') == booking_id), None)
    
    if not booking:
        bot.answer_callback_query(c.id, "❌ Не найдено")
        return
    
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Аренда студии (самостоятельная)',
        'full': '✨ Аренда со звукорежем',
    }
    d = datetime.strptime(booking['date'], "%Y-%m-%d")
    df = d.strftime("%d.%m.%Y")
    if booking.get('times'):
        start = min(booking['times'])
        end = max(booking['times']) + 1
        t_str = f"{start:02d}:00 – {end:02d}:00 ({len(booking['times'])} ч)"
    else:
        t_str = "-"
    
    text = f"""
📋 ДЕТАЛИ СЕАНСА:

{names.get(booking['service'], booking['service'])}
📅 {df}
⏰ {t_str}
💰 {booking['price']} ₽
👤 {booking['name']}
☎️ {booking['phone']}

Что сделать?
"""
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "❌ Отменить", callback_data=f"cancel_booking_{booking_id}"))
    kb.add(types.InlineKeyboardButton(
        "🔙 Назад", callback_data="back_to_bookings"))
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_booking_"))
def cb_cancel_booking_confirm(c):
    chat_id = c.message.chat.id
    booking_id = int(c.data.replace("cancel_booking_", ""))
    cancelled = cancel_booking_by_id(booking_id)
    
    if cancelled:
        bot.answer_callback_query(c.id, "✅ Отменена")
        bot.edit_message_text(
            "✅ Отменена!\n\nВремя освободилось 🎵",
            chat_id, c.message.message_id
        )
        bot.send_message(chat_id, "Главное меню", reply_markup=main_menu_keyboard())
    else:
        bot.answer_callback_query(c.id, "❌ Ошибка")


@bot.callback_query_handler(func=lambda c: c.data == "back_to_bookings")
def cb_back_to_bookings(c):
    chat_id = c.message.chat.id
    bookings = load_bookings()
    text = "📋 Твои сеансы:\n\nТапни для деталей:"
    kb = my_bookings_keyboard(bookings, chat_id)
    if kb:
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb)


# ====== ЗАПУСК =======================================================

if __name__ == "__main__":
    print("🎵 MACHATA studio бот запущен!")
    print("✨ Полнофункциональная версия с VIP скидками + валидацией телефона")
    print("☎️ Контакт: " + STUDIO_CONTACT)
    print("📍 Telegram: " + STUDIO_TELEGRAM)
    print("Нажми Ctrl+C чтобы остановить…\n")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print("Перезапускаю через 5 секунд…")
        import time
        time.sleep(5)
