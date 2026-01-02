import telebot
from telebot import types
import json
import os
from datetime import datetime, timedelta
import sys
import traceback
from flask import Flask, request
import time

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
            kb.add(types.InlineKeyboardButton("🎧 Аренда студии (самостоятельная) — 800 ₽/ч", callback_data="service_studio"))
            kb.add(types.InlineKeyboardButton("✨ Аренда со звукорежем — 1500 ₽", callback_data="service_full"))
        elif service_type == "repet":
            kb.add(types.InlineKeyboardButton("🎸 Репетиция (700 ₽/ч)", callback_data="service_repet"))
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
        user_bookings = [b for b in bookings if b.get('user_id') == user_id and b.get('status') != 'cancelled']
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
        bot.send_message(chat_id, welcome_text, reply_markup=main_menu_keyboard())
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

# ====== ОСНОВНЫЕ КОМАНДЫ ============================================
@bot.message_handler(func=lambda m: m.text == "🎙 Запись трека")
def book_recording(m):
    try:
        chat_id = m.chat.id
        text = "🎙 Запись в студии\n\nПрофессиональная аппаратура, звукорежиссёр, полный контроль звука.\n\nВыбери формат:"
        bot.send_message(chat_id, text, reply_markup=service_inline_keyboard("recording"))
        user_states[chat_id] = {'step': 'service', 'type': 'recording', 'selected_times': []}
        log_info(f"Запись: пользователь {chat_id}")
    except Exception as e:
        log_error(f"book_recording для {m.chat.id}: {str(e)}", e)

@bot.message_handler(func=lambda m: m.text == "🎸 Репетиция")
def book_repet(m):
    try:
        chat_id = m.chat.id
        text = "🎸 Репетиционная комната\n\nОбработанная акустика, инструменты, уютная атмосфера.\n\nКофе, чай, диван — бесплатно 😎\n\nБронируем?"
        kb = service_inline_keyboard("repet")
        bot.send_message(chat_id, text, reply_markup=kb)
        user_states[chat_id] = {'step': 'service', 'type': 'repet', 'selected_times': []}
        log_info(f"Репетиция: пользователь {chat_id}")
    except Exception as e:
        log_error(f"book_repet для {m.chat.id}: {str(e)}", e)

@bot.message_handler(func=lambda m: m.text == "❌ Отменить")
def cancel_booking(m):
    try:
        chat_id = m.chat.id
        user_states.pop(chat_id, None)
        bot.send_message(chat_id, "❌ Отменено.", reply_markup=main_menu_keyboard())
        log_info(f"Отмена: пользователь {chat_id}")
    except Exception as e:
        log_error(f"cancel_booking для {m.chat.id}: {str(e)}", e)

@bot.message_handler(func=lambda m: m.text == "📝 Мои бронирования")
def my_bookings(m):
    try:
        chat_id = m.chat.id
        bookings = load_bookings()
        user_bookings = [b for b in bookings if b.get('user_id') == chat_id and b.get('status') != 'cancelled']
        if not user_bookings:
            bot.send_message(chat_id, "📭 Пока нет броней. Создадим первую! 🎵", reply_markup=main_menu_keyboard())
            log_info(f"Мои брони: нет броней (пользователь {chat_id})")
            return
        text = "📋 Твои сеансы:\n\nТапни для деталей:"
        kb = my_bookings_keyboard(bookings, chat_id)
        if kb:
            bot.send_message(chat_id, text, reply_markup=kb)
        log_info(f"Мои брони: {len(user_bookings)} броней (пользователь {chat_id})")
    except Exception as e:
        log_error(f"my_bookings для {m.chat.id}: {str(e)}", e)

@bot.message_handler(func=lambda m: m.text == "💰 Тарифы & акции")
def show_prices(m):
    try:
        chat_id = m.chat.id
        vip_info = ""
        if is_vip_user(chat_id):
            vip_discount = VIP_USERS[chat_id]['discount']
            vip_info = f"\n\n👑 ТВОЯ VIP СКИДКА: {vip_discount}% на все услуги!"
        text = f"""💰 ТАРИФЫ {STUDIO_NAME}

🎸 РЕПЕТИЦИЯ
700 ₽/час
✓ Акустика и инструменты
✓ Кофе/чай бесплатно

🎧 СТУДИЯ (САМОСТОЯТЕЛЬНО)
800 ₽/час
✓ Профессиональное оборудование
✓ Звукоизоляция

✨ СТУДИЯ СО ЗВУКОРЕЖЕМ
1500 ₽
✓ Запись + микширование
✓ Готово к релизу

🎁 СКИДКИ:
💚 3+ часа: -10%
💚 5+ часов: -15%{vip_info}"""
        bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())
        log_info(f"Тарифы: пользователь {chat_id}")
    except Exception as e:
        log_error(f"show_prices для {m.chat.id}: {str(e)}", e)

@bot.message_handler(func=lambda m: m.text == "📍 Как найти")
def location(m):
    try:
        chat_id = m.chat.id
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🗺️ Яндекс.Карты", url="https://maps.yandex.ru/?text=MACHATA+studio"))
        kb.add(types.InlineKeyboardButton("🗺️ 2ГИС", url="https://2gis.ru/moscow/search/MACHATA"))
        text = f"""📍 РАСПОЛОЖЕНИЕ

{STUDIO_NAME}
{STUDIO_ADDRESS}

🕐 РЕЖИМ:
{STUDIO_HOURS}

☎️ {STUDIO_CONTACT}
📱 {STUDIO_TELEGRAM}"""
        bot.send_message(chat_id, text, reply_markup=kb)
        bot.send_message(chat_id, "Главное меню", reply_markup=main_menu_keyboard())
        log_info(f"Локация: пользователь {chat_id}")
    except Exception as e:
        log_error(f"location для {m.chat.id}: {str(e)}", e)

@bot.message_handler(func=lambda m: m.text == "💬 Живой чат")
def live_chat(m):
    try:
        chat_id = m.chat.id
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📱 Telegram", url=f"https://t.me/{STUDIO_TELEGRAM.replace('@', '')}"))
        text = f"""💬 СВЯЖИСЬ С НАМИ

📱 {STUDIO_TELEGRAM}
☎️ {STUDIO_CONTACT}
💌 hello@machata.studio

Обычно отвечаем за 15 минут 🚀"""
        bot.send_message(chat_id, text, reply_markup=kb)
        bot.send_message(chat_id, "Главное меню", reply_markup=main_menu_keyboard())
        log_info(f"Чат: пользователь {chat_id}")
    except Exception as e:
        log_error(f"live_chat для {m.chat.id}: {str(e)}", e)

# ====== CALLBACK ОБРАБОТЧИКИ ========================================
@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cb_cancel(c):
    try:
        chat_id = c.message.chat.id
        user_states.pop(chat_id, None)
        bot.edit_message_text("❌ Отменено", chat_id, c.message.message_id)
        bot.send_message(chat_id, "Вернёмся в главное меню", reply_markup=main_menu_keyboard())
        log_info(f"Отмена (callback): пользователь {chat_id}")
    except Exception as e:
        log_error(f"cb_cancel для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data.startswith("service_"))
def cb_service(c):
    try:
        chat_id = c.message.chat.id
        service = c.data.replace("service_", "")
        user_states[chat_id] = {'step': 'date', 'service': service, 'selected_times': []}
        names = {'repet': '🎸 Репетиция', 'studio': '🎧 Студия (самостоятельная)', 'full': '✨ Студия со звукорежем'}
        text = f"— — — 🎵 ШАГ 1/4 — — —\n\n{names.get(service, service)} выбрана.\n\nВыбери дату 👇"
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=dates_keyboard(0))
        log_info(f"Услуга выбрана: {service} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_service для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data.startswith("dates_page_"))
def cb_dates_page(c):
    try:
        chat_id = c.message.chat.id
        state = user_states.get(chat_id)
        if not state:
            return
        page = int(c.data.replace("dates_page_", ""))
        names = {'repet': '🎸 Репетиция', 'studio': '🎧 Студия (самостоятельная)', 'full': '✨ Студия со звукорежем'}
        text = f"— — — 🎵 ШАГ 1/4 — — —\n\n{names.get(state['service'], state['service'])} выбрана.\n\nВыбери дату 👇"
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=dates_keyboard(page))
        log_info(f"Страница дат: {page} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_dates_page для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data.startswith("date_"))
def cb_date(c):
    try:
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
        text = f"— — — 🎵 ШАГ 2/4 — — —\n\nДата: {df}\n\nВыбери часы 👇\n\n(подряд = скидка 💚)\n\n⭕ свободно | ✅ выбрано | ❌ занято"
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, date_str, state['service']))
        log_info(f"Дата выбрана: {date_str} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_date для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data.startswith("timeAdd_"))
def cb_add_time(c):
    try:
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
        text = f"— — — 🎵 ШАГ 2/4 — — —\n\nДата: {df}\n\nВыбрано: {len(sel)} ч ({start:02d}:00 – {end:02d}:00)\n\nПродолжай или ✅ Далее 👇"
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, state['date'], state['service']))
        log_info(f"Время добавлено: {h} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_add_time для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data.startswith("timeDel_"))
def cb_del_time(c):
    try:
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
            text = f"— — — 🎵 ШАГ 2/4 — — —\n\nДата: {df}\n\nВыбрано: {len(sel)} ч ({start:02d}:00 – {end:02d}:00)\n\nПродолжай или ✅ Далее 👇"
        else:
            text = f"— — — 🎵 ШАГ 2/4 — — —\n\nДата: {df}\n\nВыбери часы 👇"
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, state['date'], state['service']))
        log_info(f"Время удалено: {h} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_del_time для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data == "clear_times")
def cb_clear_times(c):
    try:
        chat_id = c.message.chat.id
        state = user_states.get(chat_id)
        if not state:
            return
        state['selected_times'] = []
        d = datetime.strptime(state['date'], "%Y-%m-%d")
        df = d.strftime("%d.%m.%Y")
        text = f"— — — 🎵 ШАГ 2/4 — — —\n\nДата: {df}\n\nВыбор очищен ✅\n\nВыбери часы 👇"
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=times_keyboard(chat_id, state['date'], state['service']))
        log_info(f"Время очищено (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_clear_times для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data == "back_to_date")
def cb_back_to_date(c):
    try:
        chat_id = c.message.chat.id
        state = user_states.get(chat_id)
        if not state:
            return
        state['step'] = 'date'
        state['selected_times'] = []
        names = {'repet': '🎸 Репетиция', 'studio': '🎧 Студия (самостоятельная)', 'full': '✨ Студия со звукорежем'}
        text = f"— — — 🎵 ШАГ 1/4 — — —\n\n{names.get(state['service'], state['service'])} выбрана.\n\nВыбери дату 👇"
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=dates_keyboard(0))
        log_info(f"Назад к датам (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_back_to_date для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data == "back_to_service")
def cb_back_to_service(c):
    try:
        chat_id = c.message.chat.id
        service_type = user_states.get(chat_id, {}).get('type', 'repet')
        user_states[chat_id] = {'step': 'service', 'type': service_type, 'selected_times': []}
        if service_type == 'recording':
            text = "🎙 Запись в студии\n\nВыбери формат:"
            kb = service_inline_keyboard("recording")
        else:
            text = "🎸 Репетиционная комната\n\nБронируем?"
            kb = service_inline_keyboard("repet")
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb)
        log_info(f"Назад к услугам (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_back_to_service для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data == "confirm_times")
def cb_confirm_times(c):
    try:
        chat_id = c.message.chat.id
        state = user_states.get(chat_id)
        if not state or not state.get('selected_times'):
            bot.answer_callback_query(c.id, "❌ Выбери хотя бы один час")
            return
        state['step'] = 'name'
        text = "— — — 🎵 ШАГ 3/4 — — —\n\nКак к тебе обращаться?\n\n(имя, ник или проект)\n\n👤 Введи 👇"
        bot.edit_message_text(text, chat_id, c.message.message_id)
        bot.send_message(chat_id, "Твоё имя или ник:", reply_markup=cancel_booking_keyboard())
        log_info(f"Время подтверждено: {len(state['selected_times'])} ч (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_confirm_times для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data == "skip")
def cb_skip(c):
    try:
        bot.answer_callback_query(c.id, "⚠️ Это время занято")
    except Exception as e:
        log_error(f"cb_skip: {str(e)}", e)

# ====== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ================================
@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('step') == 'name')
def process_name(m):
    try:
        chat_id = m.chat.id
        state = user_states.get(chat_id)
        if not state or state.get('step') != 'name':
            return
        state['name'] = m.text.strip()
        state['step'] = 'phone'
        bot.send_message(chat_id, "☎️ Номер телефона:\n\nПример: +7 (999) 000-00-00 или 79990000000", reply_markup=cancel_booking_keyboard())
        log_info(f"Имя введено: {state['name']} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"process_name для {m.chat.id}: {str(e)}", e)

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('step') == 'phone')
def process_phone(m):
    try:
        chat_id = m.chat.id
        state = user_states.get(chat_id)
        if not state or state.get('step') != 'phone':
            return
        phone = m.text.strip()
        phone_digits = ''.join(c for c in phone if c.isdigit())
        if len(phone_digits) != 11:
            bot.send_message(chat_id, "❌ Ошибка! Номер должен содержать 11 цифр.\n\n☎️ Пример: +7 (999) 000-00-00 или 79990000000", reply_markup=cancel_booking_keyboard())
            log_info(f"Ошибка телефона: {phone} (пользователь {chat_id})")
            return
        state['phone'] = phone
        state['step'] = 'comment'
        kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        kb.add(types.KeyboardButton("⏭️ Пропустить"))
        kb.add(types.KeyboardButton("❌ Отменить"))
        kb.add(types.KeyboardButton("🏠 В главное меню"))
        bot.send_message(chat_id, "💬 Что записываешь или репетируешь?\n\n(Или пропусти)", reply_markup=kb)
        log_info(f"Телефон введён: {phone} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"process_phone для {m.chat.id}: {str(e)}", e)

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get('step') == 'comment')
def process_comment(m):
    try:
        chat_id = m.chat.id
        state = user_states.get(chat_id)
        if not state or state.get('step') != 'comment':
            return
        if m.text == "⏭️ Пропустить":
            state['comment'] = "-"
        else:
            state['comment'] = m.text.strip()
        complete_booking(chat_id)
        log_info(f"Комментарий введён: {state['comment']} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"process_comment для {m.chat.id}: {str(e)}", e)

# ====== ЗАВЕРШЕНИЕ БРОНИ ============================================
def complete_booking(chat_id):
    try:
        state = user_states.get(chat_id)
        if not state:
            log_error(f"complete_booking: нет состояния для {chat_id}")
            return
        config = load_config()
        sel = state.get('selected_times', [])
        if not sel:
            bot.send_message(chat_id, "❌ Ошибка: не выбрано время")
            return
        duration = len(sel)
        service = state.get('service', 'repet')
        if service == 'full':
            base_price = config['prices']['full']
        else:
            base_price = config['prices'].get(service, 700) * duration
        price = base_price
        discount_text = ""
        vip_discount = get_user_discount(chat_id)
        if vip_discount > 0:
            price = int(base_price * (1 - vip_discount / 100))
            discount_text = f" (VIP {vip_discount}%)"
        elif duration >= 5:
            price = int(base_price * 0.85)
            discount_text = " (-15%)"
        elif duration >= 3:
            price = int(base_price * 0.9)
            discount_text = " (-10%)"
        booking_id = int(datetime.now().timestamp())
        booking = {
            'id': booking_id,
            'user_id': chat_id,
            'service': service,
            'date': state.get('date'),
            'times': sel,
            'duration': duration,
            'name': state.get('name', 'Неизвестно'),
            'phone': state.get('phone', 'Неизвестно'),
            'comment': state.get('comment', '-'),
            'price': price,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
        }
        add_booking(booking)
        names = {'repet': '🎸 Репетиция', 'studio': '🎧 Студия (самостоятельно)', 'full': '✨ Студия со звукорежем'}
        d = datetime.strptime(state['date'], "%Y-%m-%d")
        df = d.strftime("%d.%m.%Y")
        start, end = min(sel), max(sel) + 1
        cfg = load_config()
        pay_info = cfg.get('payment', {})
        text = f"""✅ БРОНЬ ПОДТВЕРЖДЕНА!

🎵 {STUDIO_NAME}

📋 ДЕТАЛИ:
{names.get(service, service)}

📅 {df}
⏰ {start:02d}:00 – {end:02d}:00
⏱️ {duration} ч

💰 {price} ₽{discount_text}

👤 {state['name']}
☎️ {state['phone']}
💬 {state['comment']}

💳 ОПЛАТА:
{pay_info.get('phone', STUDIO_CONTACT)}
{pay_info.get('bank', 'Сбербанк')}
{pay_info.get('card', '****')}

Приходи за 15 мин раньше! 🎵"""
        bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())
        user_states.pop(chat_id, None)
        log_info(f"Бронь завершена: ID={booking_id}, цена={price} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"complete_booking для {chat_id}: {str(e)}", e)
        try:
            bot.send_message(chat_id, "❌ Ошибка при сохранении брони. Попробуй ещё раз.")
        except:
            pass

# ====== ОТМЕНА БРОНЕЙ ================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("booking_detail_"))
def cb_booking_detail(c):
    try:
        chat_id = c.message.chat.id
        booking_id = int(c.data.replace("booking_detail_", ""))
        bookings = load_bookings()
        booking = next((b for b in bookings if b.get('id') == booking_id), None)
        if not booking:
            bot.answer_callback_query(c.id, "❌ Бронь не найдена")
            return
        names = {'repet': '🎸 Репетиция', 'studio': '🎧 Студия (самостоятельно)', 'full': '✨ Студия со звукорежем'}
        d = datetime.strptime(booking['date'], "%Y-%m-%d")
        df = d.strftime("%d.%m.%Y")
        if booking.get('times'):
            start = min(booking['times'])
            end = max(booking['times']) + 1
            t_str = f"{start:02d}:00 – {end:02d}:00 ({len(booking['times'])} ч)"
        else:
            t_str = "-"
        text = f"""📋 ДЕТАЛИ СЕАНСА:

{names.get(booking['service'], booking['service'])}

📅 {df}
⏰ {t_str}

💰 {booking['price']} ₽

👤 {booking['name']}
☎️ {booking['phone']}

Что сделать?"""
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_booking_{booking_id}"))
        kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_bookings"))
        bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb)
        log_info(f"Детали брони: ID={booking_id} (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_booking_detail для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_booking_"))
def cb_cancel_booking_confirm(c):
    try:
        chat_id = c.message.chat.id
        booking_id = int(c.data.replace("cancel_booking_", ""))
        cancelled = cancel_booking_by_id(booking_id)
        if cancelled:
            bot.answer_callback_query(c.id, "✅ Отменена")
            bot.edit_message_text("✅ Отменена!\n\nВремя свободно 🎵", chat_id, c.message.message_id)
            bot.send_message(chat_id, "Главное меню", reply_markup=main_menu_keyboard())
            log_info(f"Бронь отменена: ID={booking_id} (пользователь {chat_id})")
        else:
            bot.answer_callback_query(c.id, "❌ Ошибка при отмене")
    except Exception as e:
        log_error(f"cb_cancel_booking_confirm для {c.message.chat.id}: {str(e)}", e)

@bot.callback_query_handler(func=lambda c: c.data == "back_to_bookings")
def cb_back_to_bookings(c):
    try:
        chat_id = c.message.chat.id
        bookings = load_bookings()
        text = "📋 Твои сеансы:\n\nТапни для деталей:"
        kb = my_bookings_keyboard(bookings, chat_id)
        if kb:
            bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb)
        log_info(f"Назад к бронял (пользователь {chat_id})")
    except Exception as e:
        log_error(f"cb_back_to_bookings для {c.message.chat.id}: {str(e)}", e)

# ====== FLASK И WEBHOOK ===============================================
app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    log_info("Health check")
    return "🎵 MACHATA bot работает! ✅", 200

@app.route(f"/{API_TOKEN}/", methods=["POST"])
def webhook():
    try:
        json_data = request.get_json()
        if json_data:
            log_info(f"Webhook получен: {len(str(json_data))} bytes")
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
        return "ok", 200
    except Exception as e:
        log_error(f"webhook: {str(e)}", e)
        return "error", 500

# ====== ЮКАССА WEBHOOK ==============================================
@app.route("/yookassa/webhook", methods=["POST"])
def yookassa_webhook():
    try:
        json_data = request.get_json()
        log_info("ЮКасса webhook получен")
        # TODO: Обработка платежа ЮКасса
        # После успешной оплаты обновить статус брони
        return "ok", 200
    except Exception as e:
        log_error(f"yookassa_webhook: {str(e)}", e)
        return "error", 500
# ====== ТОЧКА ВХОДА ==================================================
if __name__ == "__main__":
    log_info("=" * 60)
    log_info("🎵 MACHATA studio бот запущен!")
    log_info("✨ Полнофункциональная версия")
    log_info(f"☎️ Контакт: {STUDIO_CONTACT}")
    log_info(f"📍 Telegram: {STUDIO_TELEGRAM}")
    log_info("=" * 60)
    
    PORT = int(os.environ.get("PORT", 10000))
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
    
    log_info(f"PORT: {PORT}")
    log_info(f"RENDER_URL: {RENDER_URL if RENDER_URL else 'NOT SET'}")
    
    if RENDER_URL:
        log_info(f"🌐 РЕЖИМ RENDER (webhook)")
        webhook_url = f"{RENDER_URL}/{API_TOKEN}/"
        log_info(f"Webhook URL: {webhook_url}")
        try:
            # Небольшая задержка перед установкой webhook
            time.sleep(1)
            
            # Сначала удаляем старый webhook
            log_info("Удаление старого webhook...")
            bot.remove_webhook()
            log_info("✅ Старый webhook удален")
            
            # Небольшая задержка
            time.sleep(1)
            
            # Затем устанавливаем новый
            log_info("Установка нового webhook...")
            bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            log_info("✅ Webhook установлен успешно")
            
            # Проверяем статус
            time.sleep(1)
            info = bot.get_webhook_info()
            log_info(f"Статус webhook: URL={info.url}, pending_updates={info.pending_update_count}")
        except Exception as e:
            log_error(f"Ошибка при настройке webhook: {str(e)}", e)
    else:
        log_info("⚠️ RENDER_EXTERNAL_URL не установлена! Webhook не может быть настроен.")
    
    app.run(host="0.0.0.0", port=PORT, debug=False)
