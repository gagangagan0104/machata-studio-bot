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
import time
import threading
from flask import Flask, request
from urllib.parse import quote_plus

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
STUDIO_CONTACT = "79299090989"
STUDIO_CONTACT_ALT = "+7 (977) 777-78-27"  # Дополнительный номер
STUDIO_ADDRESS = "Москва, Загородное шоссе, 1 корпус 2"
STUDIO_HOURS = "Пн–Пт 9:00–03:00 | Сб–Вс 09:00–09:00"
STUDIO_TELEGRAM = "@saxaffon"
STUDIO_TELEGRAM_ALT = "@majesticbudan"  # Дополнительный Telegram
STUDIO_EMAIL = "hello@machata.studio"

# Администратор (ID чата для уведомлений и админ-панели)
# Устанавливается двумя способами:
# 1. Через переменную окружения ADMIN_CHAT_ID на Railway/Render (постоянно)
# 2. Через команду /setadmin в боте (временно, до перезапуска)
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))

# VIP пользователи
VIP_USERS = {
    123456789: {'name': 'Иван Рок', 'discount': 20},
    987654321: {'name': 'Мария Вокал', 'discount': 15},
    555444333: {'name': 'Миша Продакшн', 'discount': 25},
}

# Конфигурация по умолчанию
DEFAULT_CONFIG = {
    'prices': {
        'repet': 50,
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
        # Проверяем и исправляем цену репетиции в кэше
        if _config_cache.get('prices', {}).get('repet') != 50:
            log_info("Обнаружена неправильная цена репетиции в кэше, исправляем")
            if 'prices' not in _config_cache:
                _config_cache['prices'] = {}
            _config_cache['prices']['repet'] = 50
        return _config_cache
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Принудительно устанавливаем правильную цену репетиции
                if 'prices' not in data:
                    data['prices'] = {}
                data['prices']['repet'] = 50
                _config_cache = data
                _config_cache_time = now
                # Логируем загруженные цены для отладки
                log_info(f"Конфиг загружен: repet={data.get('prices', {}).get('repet', 'N/A')}, studio={data.get('prices', {}).get('studio', 'N/A')}, full={data.get('prices', {}).get('full', 'N/A')}")
                return data
        _config_cache = DEFAULT_CONFIG
        _config_cache_time = now
        log_info(f"Используется DEFAULT_CONFIG: repet={DEFAULT_CONFIG.get('prices', {}).get('repet', 'N/A')}")
        return DEFAULT_CONFIG
    except Exception as e:
        log_error(f"load_config: {str(e)}", e)
        log_info(f"Ошибка загрузки, используем DEFAULT_CONFIG: repet={DEFAULT_CONFIG.get('prices', {}).get('repet', 'N/A')}")
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

def get_user_discount(chat_id):
    """Получение VIP скидки"""
    return VIP_USERS.get(chat_id, {}).get('discount', 0)

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

def is_admin(chat_id):
    """Проверка, является ли пользователь администратором"""
    return ADMIN_CHAT_ID > 0 and chat_id == ADMIN_CHAT_ID

def main_menu_keyboard(chat_id=None):
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
        types.KeyboardButton("📍 Контакты")
    )
    kb.add(
        types.KeyboardButton("📋 Правила")
    )
    # Добавляем админ-панель только для администратора
    if chat_id and is_admin(chat_id):
        kb.add(
            types.KeyboardButton("👨‍💼 Админ-панель")
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
            "🎸 Репетиция — 50 ₽/ч",
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
        # Принудительно используем правильные цены
        if service == 'repet':
            base_price = 50 * len(selected)  # Всегда 50 рублей за час репетиции
        elif service == 'full':
            base_price = config['prices'].get('full', 1500)
        else:
            base_price = config['prices'].get(service, 800) * len(selected)
        
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
        vip_badge = f"\n\n👑 <b>VIP СТАТУС АКТИВЕН!</b>\n\n🎁 <b>Привет, {vip_name}!</b>\n💎 Твоя персональная скидка: <b>{vip_discount}%</b> на всё!\n✨ Ты в приоритете при бронировании\n\n"
    
    return f"""🎵 <b>{STUDIO_NAME}</b>

<b>🔥 Где рождается настоящая музыка</b>

Ты попал в место, где звук становится искусством.
Профессиональная студия мирового уровня в самом сердце Москвы.

<b>🎯 ЧТО МЫ ПРЕДЛАГАЕМ:</b>

<b>🎸 РЕПЕТИЦИЯ</b> — <b>50 ₽/час</b> ⚡
   🎤 Идеальная акустика для твоей музыки
   🎹 Все инструменты готовы к игре
   ☕ Кофе, чай, уют — всё включено
   💫 Атмосфера, где рождаются хиты

<b>🎧 СТУДИЯ (самостоятельно)</b> — <b>800 ₽/час</b>
   🎚️ Премиум-оборудование (Neve, SSL, API)
   🔇 Звукоизоляция класса А
   🎛️ Полный контроль над каждым звуком
   🎬 Твой трек будет звучать как в топ-чартах

<b>✨ СТУДИЯ СО ЗВУКОРЕЖЕМ</b> — <b>1500 ₽</b>
   🎵 Запись + профессиональное микширование
   👨‍🎤 Опытный звукорежиссёр рядом
   🚀 Готовый трек к релизу за один сеанс
   💎 Качество студий уровня Abbey Road

<b>🎁 БОНУСЫ ДЛЯ ТЕБЯ:</b>
   💚 <b>3+ часа</b> подряд → <b>-10%</b> экономии
   💚 <b>5+ часов</b> подряд → <b>-15%</b> экономии
   ⭐ Чем больше времени — тем больше выгода!

<b>⚡ Забронируй за 30 секунд — всего 2 клика!</b>
🎵 <b>Твоя музыка ждёт тебя!</b>{vip_badge}"""

def format_prices(chat_id):
    """Форматированные тарифы"""
    vip_info = ""
    if is_vip_user(chat_id):
        vip_discount = VIP_USERS[chat_id]['discount']
        vip_info = f"\n\n👑 <b>ТВОЙ VIP СТАТУС</b>\n\n💎 <b>Персональная скидка: {vip_discount}%</b> на все услуги!\n⭐ Приоритетное бронирование\n🎁 Эксклюзивные предложения\n\n"
    
    return f"""💰 <b>ТАРИФЫ {STUDIO_NAME}</b>     

<b>🎯 ВЫБЕРИ СВОЙ ФОРМАТ:</b>

<b>🎸 РЕПЕТИЦИЯ</b>
   <b>50 ₽/час</b> ⚡ Супер цена!

   🎤 Идеальная акустика для репетиций
   🎹 Все инструменты в наличии
   ☕ Кофе, чай, уют — бесплатно
   💫 Атмосфера, где рождается магия
   🎵 Твоя музыка зазвучит по-новому

<b>🎧 СТУДИЯ (САМОСТОЯТЕЛЬНО)</b>
   <b>800 ₽/час</b>

   🎚️ Премиум-оборудование (Neve, SSL, API)
   🔇 Звукоизоляция класса А
   🎛️ Полный контроль над каждым звуком
   🎬 Твой трек будет звучать как в топ-чартах
   💎 Профессиональный уровень записи

<b>✨ СТУДИЯ СО ЗВУКОРЕЖЕМ</b>
   <b>1500 ₽</b> за сеанс

   🎵 Запись + профессиональное микширование
   👨‍🎤 Опытный звукорежиссёр рядом
   🚀 Готовый трек к релизу за один раз
   💎 Качество студий уровня Abbey Road
   ⭐ Твой звук будет идеальным

<b>🎁 СИСТЕМА СКИДОК:</b>

💚 <b>3+ часа</b> подряд → <b>-10%</b> экономии
💚 <b>5+ часов</b> подряд → <b>-15%</b> экономии
💎 Постоянным клиентам — особые условия
⭐ Чем больше времени — тем больше выгода!{vip_info}

<b>⚡ Забронируй прямо сейчас — всего 2 клика!</b>
🎵 <b>Твоя музыка ждёт тебя!</b>"""

def format_location():
    """Форматированная информация о локации"""
    return """📍 <b>КОНТАКТЫ</b>

<b>🎵 MACHATA studio</b>

<b>📞 СВЯЗЬ:</b>
☎️ <b>Телефон:</b> +7 (929) 909-09-89
📱 <b>Telegram:</b> @saxaffon
📱 <b>Telegram:</b> @majesticbudan
☎️ <b>Телефон:</b> +7 (977) 777-78-27

📍 <b>АДРЕС:</b>
Москва, Загородное шоссе, 1 корпус 2"""

def format_rules():
    """Форматированные правила использования студии"""
    config = load_config()
    rules = config.get('rules', {})
    
    title = rules.get('title', '📋 ПРАВИЛА ИСПОЛЬЗОВАНИЯ СТУДИИ')
    prohibitions = rules.get('prohibitions', [])
    damage_prices = rules.get('damage_prices', {})
    responsibility = rules.get('responsibility', [])
    general_rules = rules.get('general_rules', [])
    
    text = f"""<b>{title}</b>

<b>🚫 ЗАПРЕЩЕНО:</b>
"""
    for prohibition in prohibitions:
        text += f"   {prohibition}\n"
    
    text += f"""
<b>💰 СТОИМОСТЬ УЩЕРБА:</b>
"""
    for damage_type, price in damage_prices.items():
        damage_name = damage_type.replace('_', ' ').title()
        text += f"   • <b>{damage_name}:</b> {price}\n"
    
    text += f"""
<b>⚖️ ОТВЕТСТВЕННОСТЬ:</b>
"""
    for resp in responsibility:
        text += f"   • {resp}\n"
    
    text += f"""
<b>📝 ОБЩИЕ ПРАВИЛА:</b>
"""
    for rule in general_rules:
        text += f"   • {rule}\n"
    
    text += f"""
<b>💡 ВАЖНО:</b>
Бронируя студию, ты соглашаешься с данными правилами. Мы верим, что вместе создадим отличную атмосферу для творчества!

<b>🎵 Приятной работы в студии!</b>
<b>🔥 Твори с душой!</b>"""
    
    return text

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
            reply_markup=main_menu_keyboard(chat_id),
            parse_mode='HTML'
        )
    except Exception as e:
        log_error(f"send_welcome: {str(e)}", e)

@bot.message_handler(commands=['admin'])
def admin_command(m):
    """Команда для настройки администратора"""
    try:
        global ADMIN_CHAT_ID
        chat_id = m.chat.id
        log_info(f"Команда /admin от пользователя {chat_id}")
        
        # Показываем текущий chat_id
        text = f"""👨‍💼 <b>АДМИН-ПАНЕЛЬ</b>

<b>Твой Chat ID:</b> <code>{chat_id}</code>

<b>Текущий ADMIN_CHAT_ID:</b> <code>{ADMIN_CHAT_ID}</code>

"""
        
        if ADMIN_CHAT_ID == 0:
            text += f"""⚠️ <b>Админ-панель не настроена</b>

<b>Чтобы активировать админ-панель:</b>

1️⃣ <b>Способ 1 (рекомендуется):</b>
   Добавь переменную окружения на Railway/Render:
   <code>ADMIN_CHAT_ID={chat_id}</code>
   
   Затем перезапусти бота.

2️⃣ <b>Способ 2 (временный):</b>
   Напиши: <code>/setadmin</code>
   ⚠️ Это установит тебя как админа до перезапуска бота."""
        elif ADMIN_CHAT_ID == chat_id:
            text += f"""✅ <b>Ты администратор!</b>

Админ-панель должна быть видна в главном меню.
Если не видишь кнопку "👨‍💼 Админ-панель", отправь /start"""
        else:
            text += f"""❌ <b>Ты не администратор</b>

Текущий администратор: <code>{ADMIN_CHAT_ID}</code>
Твой ID: <code>{chat_id}</code>"""
        
        bot.send_message(chat_id, text, parse_mode='HTML')
        log_info(f"Ответ на /admin отправлен пользователю {chat_id}")
    except Exception as e:
        log_error(f"Ошибка в admin_command: {str(e)}", e)
        try:
            bot.send_message(m.chat.id, f"❌ <b>Ошибка:</b> {str(e)}", parse_mode='HTML')
        except:
            pass

@bot.message_handler(commands=['setadmin'])
def set_admin(m):
    """Временная установка администратора (до перезапуска)"""
    try:
        global ADMIN_CHAT_ID
        chat_id = m.chat.id
        log_info(f"Команда /setadmin от пользователя {chat_id}")
        
        old_admin = ADMIN_CHAT_ID
        ADMIN_CHAT_ID = chat_id
        
        text = f"""✅ <b>Администратор установлен!</b>

<b>Твой Chat ID:</b> <code>{chat_id}</code>
<b>Предыдущий админ:</b> <code>{old_admin if old_admin > 0 else 'не был установлен'}</code>

⚠️ <b>Внимание:</b> Это временная настройка!
После перезапуска бота настройка сбросится.

<b>Для постоянной настройки на Railway:</b>
1. Зайди в настройки проекта на Railway
2. Добавь переменную окружения:
   <code>ADMIN_CHAT_ID={chat_id}</code>
3. Перезапусти бота

Отправь /start чтобы увидеть админ-панель в меню."""
        
        bot.send_message(chat_id, text, parse_mode='HTML')
        
        # Отправляем обновлённое меню с админ-панелью
        bot.send_message(chat_id, "🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n\n<b>🎵 Выбери действие:</b>", reply_markup=main_menu_keyboard(chat_id), parse_mode='HTML')
        
        log_info(f"Администратор установлен через команду: {chat_id} (было: {old_admin})")
    except Exception as e:
        log_error(f"Ошибка в set_admin: {str(e)}", e)
        try:
            bot.send_message(m.chat.id, f"❌ <b>Ошибка:</b> {str(e)}", parse_mode='HTML')
        except:
            pass

@bot.message_handler(func=lambda m: m.text == "🏠 Главное меню")
def to_main_menu(m):
    """Возврат в главное меню"""
    chat_id = m.chat.id
    user_states.pop(chat_id, None)
    bot.send_message(chat_id, "🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n\n<b>🎵 Выбери действие:</b>", reply_markup=main_menu_keyboard(chat_id), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🎙 Запись трека")
def book_recording(m):
    """Бронирование записи"""
    chat_id = m.chat.id
    text = """🎙 <b>ЗАПИСЬ В СТУДИИ</b>     

<b>✨ Профессиональная звукозапись мирового уровня</b>

Твой трек будет звучать как в топ-чартах.
Премиум-оборудование, опытные звукорежиссёры и атмосфера настоящей студии.

<b>🎯 ЧТО ТЫ ПОЛУЧАЕШЬ:</b>

   🎚️ <b>Премиум-оборудование</b> (Neve, SSL, API)
   🔇 <b>Звукоизоляция класса А</b> — идеальный звук
   🎛️ <b>Полный контроль</b> над каждым звуком
   🚀 <b>Готовый трек к релизу</b> — сразу после сессии
   💎 <b>Профессиональный уровень</b> — как у звёзд

<b>💎 Выбери свой формат записи:</b>"""
    
    bot.send_message(chat_id, text, reply_markup=service_keyboard("recording"), parse_mode='HTML')
    user_states[chat_id] = {'step': 'service', 'type': 'recording', 'selected_times': []}

@bot.message_handler(func=lambda m: m.text == "🎸 Репетиция")
def book_repet(m):
    """Бронирование репетиции"""
    chat_id = m.chat.id
    text = """🎸 <b>РЕПЕТИЦИОННАЯ КОМНАТА</b>   

<b>🔥 Твоё идеальное место для творчества!</b>

Здесь рождаются хиты, здесь звучит настоящая музыка.
Профессиональная акустика, уютная атмосфера и всё необходимое для репетиций.

<b>✨ ЧТО ТЕБЯ ЖДЁТ:</b>

   🎤 <b>Идеальная акустика</b> — звук как на сцене
   🎹 <b>Все инструменты</b> — готовы к игре
   🛋️ <b>Удобная планировка</b> — просторно и комфортно
   ☕ <b>Кофе, чай, диван</b> — всё бесплатно 😎
   💫 <b>Атмосфера вдохновения</b> — здесь творят лучшие

<b>💪 Готов творить? Выбирай время!</b>
🎵 <b>Твоя музыка ждёт тебя!</b>"""
    
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
            "📭 <b>ПОКА НЕТ БРОНЕЙ</b>\n\n🎵 <b>Создадим первую?</b>\n\n💡 Выбери услугу в главном меню и забронируй время!\n\n✨ После оплаты все твои брони будут здесь\n🎯 Управляй своими сеансами в одном месте",
            reply_markup=main_menu_keyboard(chat_id),
            parse_mode='HTML'
        )
        return
    
    kb = bookings_keyboard(bookings, chat_id)
    if kb:
        bot.send_message(chat_id, "\n📋 <b>ТВОИ СЕАНСЫ</b>   \n\n\n👆 <b>Тапни на бронь для деталей:</b>", reply_markup=kb, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "💰 Тарифы")
def show_prices(m):
    """Показ тарифов"""
    chat_id = m.chat.id
    bot.send_message(chat_id, format_prices(chat_id), reply_markup=main_menu_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "📍 Контакты")
def location(m):
    """Показ локации"""
    try:
        chat_id = m.chat.id
        log_info(f"Обработка кнопки 'Контакты' от пользователя {chat_id}")
        
        location_text = format_location()
        
        # Создаём клавиатуру с кнопками Яндекс.Карт
        kb = types.InlineKeyboardMarkup(row_width=1)
        address_encoded = quote_plus("Москва, Загородное шоссе, 1 корпус 2")
        kb.add(types.InlineKeyboardButton("🚗 Яндекс.Карты - На машине", url=f"https://yandex.ru/maps/?rtext=&rtt=auto&text={address_encoded}"))
        kb.add(types.InlineKeyboardButton("🚇 Яндекс.Карты - Общественный транспорт", url=f"https://yandex.ru/maps/?rtext=&rtt=mt&text={address_encoded}"))
        
        log_info(f"Отправка контактов пользователю {chat_id}")
        bot.send_message(chat_id, location_text, reply_markup=kb, parse_mode='HTML')
        log_info(f"Контакты успешно отправлены пользователю {chat_id}")
    except Exception as e:
        log_error(f"Ошибка в функции location: {str(e)}", e)
        try:
            # Отправляем упрощённую версию контактов
            simple_text = """📍 <b>КОНТАКТЫ</b>

<b>🎵 MACHATA studio</b>

<b>📞 СВЯЗЬ:</b>
☎️ <b>Телефон:</b> +7 (929) 909-09-89
📱 <b>Telegram:</b> @saxaffon
📱 <b>Telegram:</b> @majesticbudan
☎️ <b>Телефон:</b> +7 (977) 777-78-27

📍 <b>АДРЕС:</b>
Москва, Загородное шоссе, 1 корпус 2"""
            bot.send_message(m.chat.id, simple_text, parse_mode='HTML')
        except Exception as e2:
            log_error(f"Критическая ошибка при отправке контактов: {str(e2)}", e2)

@bot.message_handler(func=lambda m: m.text == "📋 Правила")
def show_rules(m):
    """Показ правил использования студии"""
    chat_id = m.chat.id
    bot.send_message(chat_id, format_rules(), reply_markup=main_menu_keyboard(chat_id), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "👨‍💼 Админ-панель")
def admin_panel(m):
    """Админ-панель"""
    chat_id = m.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ <b>Доступ запрещён</b>", parse_mode='HTML')
        return
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📋 Все бронирования", callback_data="admin_all_bookings"))
    kb.add(types.InlineKeyboardButton("📅 Бронирования сегодня", callback_data="admin_today_bookings"))
    kb.add(types.InlineKeyboardButton("📅 Бронирования завтра", callback_data="admin_tomorrow_bookings"))
    
    text = """👨‍💼 <b>АДМИН-ПАНЕЛЬ</b>

<b>Выбери действие:</b>"""
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode='HTML')

# ====== АДМИН ФУНКЦИИ ====================================================

def format_admin_booking(booking):
    """Форматирование бронирования для администратора"""
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Студия (самостоятельная)',
        'full': '✨ Студия со звукорежем',
    }
    
    date_str = booking.get('date', '')
    times = booking.get('times', [])
    if times:
        start = min(times)
        end = max(times) + 1
        time_str = f"{start:02d}:00–{end:02d}:00 ({len(times)}ч)"
    else:
        time_str = "Время не указано"
    
    status = booking.get('status', 'pending')
    status_text = {
        'pending': '⏳ Ожидает оплаты',
        'paid': '✅ Оплачено',
        'cancelled': '❌ Отменено',
    }.get(status, status)
    
    return f"""📋 <b>Бронь #{booking.get('id', 'N/A')}</b>

<b>Услуга:</b> {names.get(booking.get('service', ''), booking.get('service', ''))}
<b>Дата:</b> {date_str}
<b>Время:</b> {time_str}
<b>Сумма:</b> {booking.get('price', 0)} ₽
<b>Статус:</b> {status_text}

<b>Клиент:</b>
👤 Имя: {booking.get('name', 'N/A')}
☎️ Телефон: {booking.get('phone', 'N/A')}
📧 Email: {booking.get('email', 'N/A')}
💬 Комментарий: {booking.get('comment', '-')}"""

# ====== CALLBACK ОБРАБОТЧИКИ ============================================

@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cb_cancel(c):
    chat_id = c.message.chat.id
    user_states.pop(chat_id, None)
    bot.edit_message_text("❌ <b>Отменено</b>", chat_id, c.message.message_id, parse_mode='HTML')
    bot.send_message(chat_id, "🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n\n<b>🎵 Выбери действие:</b>", reply_markup=main_menu_keyboard(chat_id), parse_mode='HTML')

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
    
    text = f"""🎵 <b>ШАГ 1/4: ВЫБОР ДАТЫ</b>   

✅ <b>{names.get(service, service)}</b> выбрана!

📅 <b>Выбери удобную дату:</b>

💡 <b>Совет:</b> Бронируй заранее — лучшие слоты разбирают быстро!
⚡ Популярные даты уходят за несколько дней

🎯 <b>Выбирай дату ниже:</b>"""
    
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
    
    text = f"""🎵 <b>ШАГ 1/4: ВЫБОР ДАТЫ</b>   

✅ <b>{names.get(state['service'], state['service'])}</b> выбрана!

📅 <b>Выбери удобную дату:</b>

💡 <b>Совет:</b> Бронируй заранее — лучшие слоты разбирают быстро!
⚡ Популярные даты уходят за несколько дней

🎯 <b>Выбирай дату ниже:</b>"""
    
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
    
    text = f"""🎵 <b>ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>   

📅 <b>Дата:</b> {df}

⏰ <b>Выбери часы для сессии:</b>

💚 <b>Чем больше часов подряд — тем больше скидка!</b>
   • 3+ часа → -10%
   • 5+ часов → -15%

<b>⭕ свободно | ✅ выбрано | 🚫 занято</b>

🎯 <b>Выбирай часы ниже:</b>"""
    
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
    
    text = f"""🎵 <b>ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>   

📅 <b>Дата:</b> {df}
⏰ <b>Выбрано:</b> {len(sel)} ч ({start:02d}:00 – {end:02d}:00)

💚 <b>Продолжай выбирать или нажми ✅ Далее</b>

🎯 <b>Чем больше часов — тем больше скидка!</b>"""
    
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
        text = f"""🎵 <b>ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>   

📅 <b>Дата:</b> {df}
⏰ <b>Выбрано:</b> {len(sel)} ч ({start:02d}:00 – {end:02d}:00)

💚 <b>Продолжай выбирать или нажми ✅ Далее</b>

🎯 <b>Чем больше часов — тем больше скидка!</b>"""
    else:
        text = f"""🎵 <b>ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>   

📅 <b>Дата:</b> {df}

⏰ <b>Выбери часы для сессии:</b>

💚 <b>Чем больше часов подряд — тем больше скидка!</b>
   • 3+ часа → -10%
   • 5+ часов → -15%

<b>⭕ свободно | ✅ выбрано | 🚫 занято</b>

🎯 <b>Выбирай часы ниже:</b>"""
    
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
    
    text = f"""🎵 <b>ШАГ 2/4: ВЫБОР ВРЕМЕНИ</b>   

📅 <b>Дата:</b> {df}

✅ <b>Выбор очищен</b>

⏰ <b>Выбери часы для сессии:</b>

💚 <b>Чем больше часов подряд — тем больше скидка!</b>
   • 3+ часа → -10%
   • 5+ часов → -15%

<b>⭕ свободно | ✅ выбрано | 🚫 занято</b>

🎯 <b>Выбирай часы ниже:</b>"""
    
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
    
    text = f"""🎵 <b>ШАГ 1/4: ВЫБОР ДАТЫ</b>   

✅ <b>{names.get(state['service'], state['service'])}</b> выбрана!

📅 <b>Выбери удобную дату:</b>

💡 <b>Совет:</b> Бронируй заранее — лучшие слоты разбирают быстро!
⚡ Популярные даты уходят за несколько дней

🎯 <b>Выбирай дату ниже:</b>"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=dates_keyboard(0), parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "back_to_service")
def cb_back_to_service(c):
    chat_id = c.message.chat.id
    service_type = user_states.get(chat_id, {}).get('type', 'repet')
    user_states[chat_id] = {'step': 'service', 'type': service_type, 'selected_times': []}
    
    if service_type == 'recording':
        text = """🎙 <b>ЗАПИСЬ В СТУДИИ</b>     

<b>✨ Профессиональная звукозапись мирового уровня</b>

Твой трек будет звучать как в топ-чартах.
Премиум-оборудование, опытные звукорежиссёры и атмосфера настоящей студии.

<b>🎯 ЧТО ТЫ ПОЛУЧАЕШЬ:</b>

   🎚️ <b>Премиум-оборудование</b> (Neve, SSL, API)
   🔇 <b>Звукоизоляция класса А</b> — идеальный звук
   🎛️ <b>Полный контроль</b> над каждым звуком
   🚀 <b>Готовый трек к релизу</b> — сразу после сессии
   💎 <b>Профессиональный уровень</b> — как у звёзд

<b>💎 Выбери свой формат записи:</b>"""
        kb = service_keyboard("recording")
    else:
        text = """🎸 <b>РЕПЕТИЦИОННАЯ КОМНАТА</b>   

<b>🔥 Твоё идеальное место для творчества!</b>

Здесь рождаются хиты, здесь звучит настоящая музыка.
Профессиональная акустика, уютная атмосфера и всё необходимое для репетиций.

<b>✨ ЧТО ТЕБЯ ЖДЁТ:</b>

   🎤 <b>Идеальная акустика</b> — звук как на сцене
   🎹 <b>Все инструменты</b> — готовы к игре
   🛋️ <b>Удобная планировка</b> — просторно и комфортно
   ☕ <b>Кофе, чай, диван</b> — всё бесплатно 😎
   💫 <b>Атмосфера вдохновения</b> — здесь творят лучшие

<b>💪 Готов творить? Выбирай время!</b>
🎵 <b>Твоя музыка ждёт тебя!</b>"""
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
    
    text = """🎵 <b>ШАГ 3/4: КОНТАКТНЫЕ ДАННЫЕ</b>   

👤 <b>Как к тебе обращаться?</b>

💡 <b>Можешь указать:</b>
   • Имя
   • Никнейм
   • Название проекта/группы

🎯 <b>Введи ниже:</b>"""
    
    bot.edit_message_text(text, chat_id, c.message.message_id, parse_mode='HTML')
    bot.send_message(chat_id, "\n👤 <b>ТВОЁ ИМЯ</b>   \n\n\n💡 <b>Как к тебе обращаться?</b>\n\n🎯 Можешь указать:\n   • Имя\n   • Никнейм\n   • Название проекта/группы\n\n<b>Введи ниже:</b>", reply_markup=cancel_keyboard(), parse_mode='HTML')

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
        "\n📧 <b>ТВОЙ EMAIL</b>   \n\n\n✉️ <b>На него отправим чек об оплате</b>\n\n🔒 <b>Безопасность:</b>\n   • Данные защищены\n   • Используются только для чека\n   • Не передаём третьим лицам\n\n<b>Введи email ниже:</b>",
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
            "\n⚠️ <b>ОШИБКА EMAIL</b>   \n\n\n❌ <b>Некорректный email</b>\n\n💡 <b>Пожалуйста, проверь формат:</b>\n   Пример: <code>name@example.com</code>\n\n📧 <b>Email нужен для отправки чека об оплате</b>\n\n<b>Попробуй ещё раз:</b>",
            reply_markup=cancel_keyboard(),
            parse_mode='HTML'
        )
        return
    
    state['email'] = email
    state['step'] = 'phone'
    
    bot.send_message(
        chat_id,
        "\n☎️ <b>ТВОЙ ТЕЛЕФОН</b>   \n\n\n📞 <b>Нужен для связи и подтверждения брони</b>\n\n💡 <b>Примеры формата:</b>\n   • <code>+7 (999) 000-00-00</code>\n   • <code>79990000000</code>\n\n🔒 <b>Безопасность:</b> Данные защищены\n\n<b>Введи номер ниже:</b>",
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
            "\n⚠️ <b>ОШИБКА ТЕЛЕФОНА</b>   \n\n\n❌ <b>Номер должен содержать 11 цифр</b>\n\n💡 <b>Правильные форматы:</b>\n   • <code>+7 (999) 000-00-00</code>\n   • <code>79990000000</code>\n\n<b>Попробуй ещё раз:</b>",
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
        "\n💬 <b>КОММЕНТАРИЙ</b>   \n\n\n🎵 <b>Что записываешь или репетируешь?</b>\n\n💡 <b>Расскажи о своём проекте:</b>\n   • Название группы/проекта\n   • Стиль музыки\n   • Особые пожелания\n\n✨ <b>Это поможет нам лучше подготовиться!</b>\n\n⏭️ <b>Или просто пропусти</b>",
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

def check_payment_status(payment_id):
    """Проверка статуса платежа через API ЮKassa"""
    try:
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            return {'success': False, 'error': 'Ключи ЮKassa не настроены'}
        
        shop_id = YOOKASSA_SHOP_ID.strip()
        secret_key = YOOKASSA_SECRET_KEY.strip()
        
        auth_string = f"{shop_id}:{secret_key}"
        auth_b64 = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
        
        headers = {
            "Authorization": f"Basic {auth_b64}"
        }
        
        response = requests.get(
            f"https://api.yookassa.ru/v3/payments/{payment_id}",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            payment_info = response.json()
            return {
                'success': True,
                'status': payment_info.get('status'),
                'paid': payment_info.get('status') == 'succeeded',
                'payment_info': payment_info
            }
        else:
            return {
                'success': False,
                'error': f"API вернул код {response.status_code}: {response.text[:300]}"
            }
            
    except Exception as e:
        log_error(f"Ошибка проверки статуса платежа: {str(e)}", e)
        return {'success': False, 'error': str(e)}

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
                "return_url": PUBLIC_URL if PUBLIC_URL else "https://t.me"  # После оплаты возврат на наш сайт
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
            bot.send_message(chat_id, "\n⚠️ <b>ОШИБКА</b>   \n\n\n❌ <b>Состояние потеряно</b>\n\n💡 <b>Не переживай! Просто начни заново:</b>\n\n🎯 Выбери услугу в главном меню\n\n<b>🎵 Всё будет хорошо!</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')
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
        
        # Принудительно используем правильные цены
        prices = config.get('prices', {})
        if service == 'full':
            base_price = prices.get('full', 1500)
        elif service == 'repet':
            # Принудительно 50 рублей за час репетиции
            base_price = 50 * duration
            log_info(f"Расчёт цены репетиции: 50₽ × {duration}ч = {base_price}₽")
        elif service == 'studio':
            base_price = prices.get('studio', 800) * duration
        else:
            base_price = prices.get(service, 50) * duration
        
        log_info(f"Расчёт цены: service={service}, duration={duration}, base_price={base_price}₽")
        
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
                f"\n⚠️ <b>ОШИБКА ОПЛАТЫ</b>   \n\n\n❌ <b>Не удалось создать платёж</b>\n\n💡 <b>Что делать:</b>\n   • Попробуй ещё раз через минуту\n   • Или свяжись с нами — мы поможем!\n\n\n\n<b>📞 КОНТАКТЫ:</b>\n📱 <b>Telegram:</b> {STUDIO_TELEGRAM}\n☎️ <b>Телефон:</b> +{STUDIO_CONTACT}\n\n<b>🎵 Мы всегда готовы помочь!</b>",
                reply_markup=main_menu_keyboard(chat_id),
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
        
        payment_message = f"""💳 <b>ОПЛАТА БРОНИРОВАНИЯ</b>   

<b>🎵 Почти готово! Осталось оплатить</b>

📅 <b>Дата:</b> {df}
⏰ <b>Время:</b> {start:02d}:00–{end:02d}:00 ({duration}ч)
💰 <b>Сумма:</b> {price} ₽{discount_text}

<b>⚡ Нажми кнопку ниже для оплаты:</b>
💳 <b>Безопасная оплата через ЮKassa</b>
🔒 <b>Чек придёт на email автоматически</b>"""
        
        bot.send_message(chat_id, payment_message, reply_markup=kb, parse_mode='HTML')
        user_states.pop(chat_id, None)
        log_info(f"Платеж создан: booking_id={booking_id}, сумма={price}₽")
        
        # Уведомляем администратора о новом бронировании
        notify_admin_new_booking(booking)
        
    except Exception as e:
        log_error(f"complete_booking: {str(e)}", e)
        bot.send_message(
            chat_id,
            f"\n⚠️ <b>ОШИБКА</b>   \n\n\n❌ <b>Что-то пошло не так</b>\n\n💡 <b>Не переживай! Мы поможем:</b>\n\n📱 <b>Telegram:</b> {STUDIO_TELEGRAM}\n☎️ <b>Телефон:</b> +{STUDIO_CONTACT}\n\n<b>🎵 Свяжись с нами — мы решим всё быстро!</b>",
            parse_mode='HTML'
        )

# ====== УВЕДОМЛЕНИЯ ======================================================

def notify_admin_new_booking(booking):
    """Уведомление администратору о новом бронировании"""
    if not ADMIN_CHAT_ID or ADMIN_CHAT_ID <= 0:
        return
    
    try:
        names = {
            'repet': '🎸 Репетиция',
            'studio': '🎧 Студия (самостоятельная)',
            'full': '✨ Студия со звукорежем',
        }
        
        date_str = booking.get('date', '')
        times = booking.get('times', [])
        if times:
            start = min(times)
            end = max(times) + 1
            time_str = f"{start:02d}:00–{end:02d}:00 ({len(times)}ч)"
        else:
            time_str = "Время не указано"
        
        text = f"""🆕 <b>НОВОЕ БРОНИРОВАНИЕ</b>

{format_admin_booking(booking)}

<b>📞 Контакты клиента:</b>
☎️ {booking.get('phone', 'N/A')}
📧 {booking.get('email', 'N/A')}

<b>⏳ Статус:</b> Ожидает оплаты
💳 Клиенту отправлена ссылка на оплату"""
        
        bot.send_message(ADMIN_CHAT_ID, text, parse_mode='HTML')
        log_info(f"Уведомление администратору о новом бронировании {booking.get('id')}")
    except Exception as e:
        log_error(f"Ошибка отправки уведомления администратору о новом бронировании: {str(e)}", e)

def notify_admin_payment_success(booking):
    """Уведомление администратору об успешной оплате"""
    if not ADMIN_CHAT_ID or ADMIN_CHAT_ID <= 0:
        return
    
    try:
        names = {
            'repet': '🎸 Репетиция',
            'studio': '🎧 Студия (самостоятельная)',
            'full': '✨ Студия со звукорежем',
        }
        
        date_str = booking.get('date', '')
        times = booking.get('times', [])
        if times:
            start = min(times)
            end = max(times) + 1
            time_str = f"{start:02d}:00–{end:02d}:00 ({len(times)}ч)"
        else:
            time_str = "Время не указано"
        
        text = f"""✅ <b>БРОНИРОВАНИЕ ОПЛАЧЕНО</b>

{format_admin_booking(booking)}

<b>📞 Контакты клиента:</b>
☎️ {booking.get('phone', 'N/A')}
📧 {booking.get('email', 'N/A')}

<b>💰 Сумма:</b> {booking.get('price', 0)} ₽
<b>✅ Статус:</b> Оплачено"""
        
        bot.send_message(ADMIN_CHAT_ID, text, parse_mode='HTML')
        log_info(f"Уведомление администратору об оплате бронирования {booking.get('id')}")
    except Exception as e:
        log_error(f"Ошибка отправки уведомления администратору об оплате: {str(e)}", e)

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
        
        text = f"""✅ <b>ОПЛАТА ПОЛУЧЕНА!</b>   

<b>🎉 Спасибо за оплату!</b>

Твоя бронь подтверждена и мы ждём тебя в студии!

<b>📋 Детали брони:</b>
🎵 {names.get(booking['service'], booking['service'])}
📅 <b>Дата:</b> {df}
⏰ <b>Время:</b> {t_str}
💰 <b>Сумма:</b> {booking['price']} ₽

✉️ <b>Чек отправлен на email автоматически</b>

<b>💡 ВАЖНО:</b>
   ⏰ Приходи за 15 минут до начала сессии
   💰 Отмена менее чем за 24 часа — возврат 50%
   ⚠️ Опоздание более 30 минут — бронь аннулируется

<b>🎵 Увидимся в студии!</b>
<b>🔥 Твори с душой!</b>"""
        
        # Создаём клавиатуру с кнопками навигации
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("📍 Контакты и как найти", callback_data="show_location_after_payment"))
        kb.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main_after_payment"))
        
        bot.send_message(chat_id, text, reply_markup=kb, parse_mode='HTML')
        log_info(f"Уведомление об оплате отправлено: booking_id={booking.get('id')}")
        
        # Уведомляем администратора об успешной оплате
        notify_admin_payment_success(booking)
        
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
    
    # Проверяем статус платежа, если есть payment_id
    payment_id = booking.get('yookassa_payment_id')
    if payment_id and booking.get('status') == 'awaiting_payment':
        log_info(f"Проверка статуса платежа для брони {booking_id}, payment_id={payment_id}")
        payment_status = check_payment_status(payment_id)
        if payment_status.get('success') and payment_status.get('paid'):
            # Платеж успешен, обновляем статус
            for i, b in enumerate(bookings):
                if b.get('id') == booking_id:
                    bookings[i]['status'] = 'paid'
                    bookings[i]['paid_at'] = datetime.now().isoformat()
                    save_bookings(bookings)
                    booking = bookings[i]
                    log_info(f"Статус брони {booking_id} обновлен на 'paid' после проверки")
                    notify_payment_success(booking)
                    notify_admin_payment_success(booking)
                    break
    
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
    
    # Если есть payment_url и статус awaiting_payment, показываем кнопку оплаты
    payment_url = booking.get('payment_url')
    
    text = f"""📋 <b>ДЕТАЛИ СЕАНСА</b>   

<b>{names.get(booking['service'], booking['service'])}</b>

<b>📅 Дата:</b> {df}
<b>⏰ Время:</b> {t_str}
<b>💰 Сумма:</b> {booking['price']} ₽

<b>📌 Статус:</b> {status_text}

<b>👤 Имя:</b> {booking['name']}
<b>☎️ Телефон:</b> {booking['phone']}
<b>💬 Комментарий:</b> {booking.get('comment', '-')}

<b>🎯 Что сделать?</b>"""
    
    kb = types.InlineKeyboardMarkup()
    
    # Если ожидает оплаты и есть payment_url, показываем кнопку оплаты
    if status == 'awaiting_payment' and payment_url:
        kb.add(types.InlineKeyboardButton("💳 Оплатить", url=payment_url))
        kb.add(types.InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_payment_{booking_id}"))
    
    kb.add(types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_booking_{booking_id}"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_bookings"))
    
    bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=kb, parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data.startswith("check_payment_"))
def cb_check_payment(c):
    """Проверка статуса оплаты по запросу пользователя"""
    chat_id = c.message.chat.id
    booking_id = int(c.data.replace("check_payment_", ""))
    bookings = load_bookings()
    booking = next((b for b in bookings if b.get('id') == booking_id), None)
    
    if not booking:
        bot.answer_callback_query(c.id, "❌ Бронь не найдена")
        return
    
    if booking.get('status') == 'paid':
        bot.answer_callback_query(c.id, "✅ Бронь уже оплачена")
        # Обновляем сообщение - создаём новый callback для cb_booking_detail
        class FakeCallback:
            def __init__(self, message, data, callback_id):
                self.message = message
                self.data = data
                self.id = callback_id
        
        fake_callback = FakeCallback(c.message, f"booking_detail_{booking_id}", c.id)
        cb_booking_detail(fake_callback)
        return
    
    payment_id = booking.get('yookassa_payment_id')
    if not payment_id:
        bot.answer_callback_query(c.id, "❌ ID платежа не найден")
        return
    
    bot.answer_callback_query(c.id, "🔄 Проверяю статус оплаты...")
    
    # Проверяем статус платежа
    payment_status = check_payment_status(payment_id)
    
    if payment_status.get('success'):
        if payment_status.get('paid'):
            # Платеж успешен, обновляем статус
            for i, b in enumerate(bookings):
                if b.get('id') == booking_id:
                    bookings[i]['status'] = 'paid'
                    bookings[i]['paid_at'] = datetime.now().isoformat()
                    save_bookings(bookings)
                    booking = bookings[i]
                    log_info(f"Статус брони {booking_id} обновлен на 'paid' после ручной проверки")
                    notify_payment_success(booking)
                    notify_admin_payment_success(booking)
                    break
            
            bot.answer_callback_query(c.id, "✅ Оплата подтверждена!")
            # Обновляем сообщение - создаём новый callback для cb_booking_detail
            class FakeCallback:
                def __init__(self, message, data, callback_id):
                    self.message = message
                    self.data = data
                    self.id = callback_id
            
            fake_callback = FakeCallback(c.message, f"booking_detail_{booking_id}", c.id)
            cb_booking_detail(fake_callback)
        else:
            current_status = payment_status.get('status', 'unknown')
            bot.answer_callback_query(c.id, f"⏳ Статус: {current_status}")
    else:
        error = payment_status.get('error', 'Неизвестная ошибка')
        log_error(f"Ошибка проверки платежа {payment_id}: {error}")
        bot.answer_callback_query(c.id, "❌ Ошибка проверки")

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
                f"\n⚠️ <b>БРОНЬ ОПЛАЧЕНА</b>   \n\n\n<b>Эта бронь уже оплачена.</b>\n\n\n\n<b>📞 Для отмены свяжись с нами:</b>\n\n📱 <b>Telegram:</b> {STUDIO_TELEGRAM}\n☎️ <b>Телефон:</b> +{STUDIO_CONTACT}\n\n\n\n💡 <b>Условия возврата:</b>\n   • Отмена менее чем за 24 часа → возврат 50%\n   • Отмена более чем за 24 часа → полный возврат\n\n<b>🎵 Мы всегда готовы помочь!</b>",
                reply_markup=main_menu_keyboard(chat_id),
                parse_mode='HTML'
            )
        else:
            bot.answer_callback_query(c.id, "✅ Отменена")
            bot.edit_message_text(
                "\n✅ <b>БРОНЬ ОТМЕНЕНА</b>   \n\n\n<b>⏰ Время освобождено</b>\n\n🎵 <b>Можешь забронировать другое время</b>\n\n\n\n<b>🙏 Спасибо, что уведомил нас!</b>\n\n💡 <b>Если передумаешь — мы всегда рады видеть тебя!</b>",
                chat_id, c.message.message_id,
                parse_mode='HTML'
            )
            bot.send_message(chat_id, "🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n\n<b>🎵 Выбери действие:</b>", reply_markup=main_menu_keyboard(chat_id), parse_mode='HTML')
    else:
        bot.answer_callback_query(c.id, "❌ Ошибка при отмене")

@bot.callback_query_handler(func=lambda c: c.data == "back_to_bookings")
def cb_back_to_bookings(c):
    chat_id = c.message.chat.id
    bookings = load_bookings()
    kb = bookings_keyboard(bookings, chat_id)
    
    if kb:
        bot.edit_message_text("<b>📋 Твои сеансы:</b>\n\nТапни для деталей:", chat_id, c.message.message_id, reply_markup=kb, parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "show_location_after_payment")
def cb_show_location_after_payment(c):
    """Показ контактов после оплаты - сразу переводим на вкладку КОНТАКТЫ"""
    chat_id = c.message.chat.id
    bot.answer_callback_query(c.id, "📍 Контакты")
    
    try:
        location_text = format_location()
        kb = types.InlineKeyboardMarkup(row_width=1)
        address_encoded = quote_plus("Москва, Загородное шоссе, 1 корпус 2")
        kb.add(types.InlineKeyboardButton("🚗 Яндекс.Карты - На машине", url=f"https://yandex.ru/maps/?rtext=&rtt=auto&text={address_encoded}"))
        kb.add(types.InlineKeyboardButton("🚇 Яндекс.Карты - Общественный транспорт", url=f"https://yandex.ru/maps/?rtext=&rtt=mt&text={address_encoded}"))
        kb.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main_after_payment"))
        bot.send_message(chat_id, location_text, reply_markup=kb, parse_mode='HTML')
    except Exception as e:
        log_error(f"Ошибка в cb_show_location_after_payment: {str(e)}", e)
        # Отправляем упрощённую версию
        simple_text = """📍 <b>КОНТАКТЫ</b>

<b>🎵 MACHATA studio</b>

<b>📞 СВЯЗЬ:</b>
☎️ <b>Телефон:</b> +7 (929) 909-09-89
📱 <b>Telegram:</b> @saxaffon
📱 <b>Telegram:</b> @majesticbudan
☎️ <b>Телефон:</b> +7 (977) 777-78-27

📍 <b>АДРЕС:</b>
Москва, Загородное шоссе, 1 корпус 2"""
        bot.send_message(chat_id, simple_text, parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == "back_to_main_after_payment")
def cb_back_to_main_after_payment(c):
    """Возврат в главное меню после оплаты"""
    chat_id = c.message.chat.id
    bot.send_message(chat_id, "🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n\n<b>🎵 Выбери действие:</b>", reply_markup=main_menu_keyboard(chat_id), parse_mode='HTML')
    bot.answer_callback_query(c.id, "🏠 Главное меню")


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_"))
def cb_admin(c):
    """Обработчики админ-панели"""
    chat_id = c.message.chat.id
    if not is_admin(chat_id):
        bot.answer_callback_query(c.id, "❌ Доступ запрещён")
        return
    
    bookings = load_bookings()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    if c.data == "admin_all_bookings":
        # Все бронирования
        active_bookings = [b for b in bookings if b.get('status') in ['paid', 'pending', 'awaiting_payment']]
        if not active_bookings:
            bot.answer_callback_query(c.id, "📭 Нет активных бронирований")
            bot.edit_message_text("📭 <b>Нет активных бронирований</b>", chat_id, c.message.message_id, parse_mode='HTML')
            return
        
        text = f"📋 <b>ВСЕ АКТИВНЫЕ БРОНИРОВАНИЯ ({len(active_bookings)})</b>\n\n"
        for booking in sorted(active_bookings, key=lambda x: (x.get('date', ''), min(x.get('times', [0])))):
            text += format_admin_booking(booking) + "\n\n"
        
        bot.edit_message_text(text, chat_id, c.message.message_id, parse_mode='HTML')
        bot.answer_callback_query(c.id, f"✅ Найдено {len(active_bookings)} бронирований")
    
    elif c.data == "admin_today_bookings":
        # Бронирования сегодня
        today_bookings = [b for b in bookings if b.get('date') == today and b.get('status') in ['paid', 'pending', 'awaiting_payment']]
        if not today_bookings:
            bot.answer_callback_query(c.id, "📭 Нет бронирований на сегодня")
            bot.edit_message_text(f"📭 <b>Нет бронирований на {today}</b>", chat_id, c.message.message_id, parse_mode='HTML')
            return
        
        text = f"📅 <b>БРОНИРОВАНИЯ СЕГОДНЯ ({len(today_bookings)})</b>\n\n"
        for booking in sorted(today_bookings, key=lambda x: min(x.get('times', [0]))):
            text += format_admin_booking(booking) + "\n\n"
        
        bot.edit_message_text(text, chat_id, c.message.message_id, parse_mode='HTML')
        bot.answer_callback_query(c.id, f"✅ Найдено {len(today_bookings)} бронирований")
    
    elif c.data == "admin_tomorrow_bookings":
        # Бронирования завтра
        tomorrow_bookings = [b for b in bookings if b.get('date') == tomorrow and b.get('status') in ['paid', 'pending', 'awaiting_payment']]
        if not tomorrow_bookings:
            bot.answer_callback_query(c.id, "📭 Нет бронирований на завтра")
            bot.edit_message_text(f"📭 <b>Нет бронирований на {tomorrow}</b>", chat_id, c.message.message_id, parse_mode='HTML')
            return
        
        text = f"📅 <b>БРОНИРОВАНИЯ ЗАВТРА ({len(tomorrow_bookings)})</b>\n\n"
        for booking in sorted(tomorrow_bookings, key=lambda x: min(x.get('times', [0]))):
            text += format_admin_booking(booking) + "\n\n"
        
        bot.edit_message_text(text, chat_id, c.message.message_id, parse_mode='HTML')
        bot.answer_callback_query(c.id, f"✅ Найдено {len(tomorrow_bookings)} бронирований")

# ====== СИСТЕМА УВЕДОМЛЕНИЙ ==============================================

def send_admin_notification(booking, notification_type):
    """Отправка уведомления администратору"""
    if not ADMIN_CHAT_ID or ADMIN_CHAT_ID <= 0:
        return
    
    names = {
        'repet': '🎸 Репетиция',
        'studio': '🎧 Студия (самостоятельная)',
        'full': '✨ Студия со звукорежем',
    }
    
    date_str = booking.get('date', '')
    times = booking.get('times', [])
    if times:
        start = min(times)
        end = max(times) + 1
        time_str = f"{start:02d}:00–{end:02d}:00 ({len(times)}ч)"
    else:
        time_str = "Время не указано"
    
    if notification_type == "24h":
        emoji = "⏰"
        title = "НАПОМИНАНИЕ: Бронь через 24 часа"
    elif notification_type == "30m":
        emoji = "🔔"
        title = "НАПОМИНАНИЕ: Бронь через 30 минут"
    else:
        return
    
    text = f"""{emoji} <b>{title}</b>

{format_admin_booking(booking)}

<b>📞 Контакты клиента для связи:</b>
☎️ {booking.get('phone', 'N/A')}
📧 {booking.get('email', 'N/A')}"""
    
    try:
        bot.send_message(ADMIN_CHAT_ID, text, parse_mode='HTML')
        log_info(f"Уведомление администратору отправлено: {notification_type} для брони {booking.get('id')}")
    except Exception as e:
        log_error(f"Ошибка отправки уведомления администратору: {str(e)}", e)

def check_and_send_notifications():
    """Проверка и отправка уведомлений администратору"""
    if not ADMIN_CHAT_ID or ADMIN_CHAT_ID <= 0:
        return
    
    try:
        bookings = load_bookings()
        now = datetime.now()
        
        for booking in bookings:
            if booking.get('status') not in ['paid', 'pending', 'awaiting_payment']:
                continue
            
            date_str = booking.get('date', '')
            times = booking.get('times', [])
            if not date_str or not times:
                continue
            
            try:
                booking_date = datetime.strptime(date_str, "%Y-%m-%d")
                start_hour = min(times)
                booking_datetime = booking_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                
                # Проверяем уведомление за 24 часа
                time_until = booking_datetime - now
                hours_until = time_until.total_seconds() / 3600
                
                # Проверяем, не отправляли ли уже уведомление за 24 часа
                notified_24h = booking.get('notified_24h', False)
                if 23.5 <= hours_until <= 24.5 and not notified_24h:
                    send_admin_notification(booking, "24h")
                    # Помечаем, что уведомление отправлено
                    for i, b in enumerate(bookings):
                        if b.get('id') == booking.get('id'):
                            bookings[i]['notified_24h'] = True
                            save_bookings(bookings)
                            break
                
                # Проверяем уведомление за 30 минут
                notified_30m = booking.get('notified_30m', False)
                if 0.4 <= hours_until <= 0.6 and not notified_30m:
                    send_admin_notification(booking, "30m")
                    # Помечаем, что уведомление отправлено
                    for i, b in enumerate(bookings):
                        if b.get('id') == booking.get('id'):
                            bookings[i]['notified_30m'] = True
                            save_bookings(bookings)
                            break
            except Exception as e:
                log_error(f"Ошибка проверки уведомления для брони {booking.get('id')}: {str(e)}", e)
    except Exception as e:
        log_error(f"Ошибка check_and_send_notifications: {str(e)}", e)

def notification_worker():
    """Фоновая задача для проверки уведомлений"""
    while True:
        try:
            check_and_send_notifications()
            # Проверяем каждые 5 минут
            time.sleep(300)
        except Exception as e:
            log_error(f"Ошибка в notification_worker: {str(e)}", e)
            time.sleep(60)

# ====== FLASK И WEBHOOK ==================================================

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 10000))

# Определение публичного URL для разных платформ
RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
RAILWAY_STATIC_URL = os.environ.get("RAILWAY_STATIC_URL", "")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "") or os.environ.get("RENDER_EXTERNAL_HOST", "")

PUBLIC_URL = ""

# Приоритет: Railway -> Render -> локальный режим
if RAILWAY_PUBLIC_DOMAIN:
    PUBLIC_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}" if not RAILWAY_PUBLIC_DOMAIN.startswith("http") else RAILWAY_PUBLIC_DOMAIN
    log_info(f"Railway: найден RAILWAY_PUBLIC_DOMAIN: {RAILWAY_PUBLIC_DOMAIN}")
elif RAILWAY_STATIC_URL:
    PUBLIC_URL = RAILWAY_STATIC_URL if RAILWAY_STATIC_URL.startswith("http") else f"https://{RAILWAY_STATIC_URL}"
    log_info(f"Railway: найден RAILWAY_STATIC_URL: {RAILWAY_STATIC_URL}")
elif RENDER_EXTERNAL_URL:
    PUBLIC_URL = RENDER_EXTERNAL_URL if RENDER_EXTERNAL_URL.startswith("http") else f"https://{RENDER_EXTERNAL_URL}"
    log_info(f"Render: найден RENDER_EXTERNAL_URL: {RENDER_EXTERNAL_URL}")

IS_LOCAL = not PUBLIC_URL

if PUBLIC_URL:
    log_info(f"✅ PUBLIC_URL установлен: {PUBLIC_URL}")
else:
    log_info("⚠️ PUBLIC_URL не установлен - будет использован локальный режим")

# Определение платформы по URL
def detect_platform():
    """Определяет платформу по PUBLIC_URL и переменным окружения"""
    if not PUBLIC_URL:
        return "Local"
    
    # Сначала проверяем URL напрямую (самый надёжный способ)
    url_lower = PUBLIC_URL.lower()
    if "railway" in url_lower or "railway.app" in url_lower:
        return "Railway"
    elif "render" in url_lower or "onrender.com" in url_lower:
        return "Render"
    
    # Если URL не помог, проверяем переменные окружения
    if RAILWAY_PUBLIC_DOMAIN:
        return "Railway"
    elif RENDER_EXTERNAL_URL:
        # Дополнительная проверка: может быть Railway URL в RENDER_EXTERNAL_URL
        render_url_lower = RENDER_EXTERNAL_URL.lower()
        if "railway" in render_url_lower:
            return "Railway"
        return "Render"
    
    return "Unknown"

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
            log_error("yookassa_webhook: пустой запрос")
            return "error", 400
        
        event_type = json_data.get("event")
        payment_object = json_data.get("object", {})
        payment_id = payment_object.get("id")
        payment_status = payment_object.get("status")
        metadata = payment_object.get("metadata", {})
        booking_id = metadata.get("booking_id")
        
        log_info(f"Вебхук ЮKassa получен: event={event_type}, payment_id={payment_id}, payment_status={payment_status}, booking_id={booking_id}")
        
        # Обрабатываем только события успешной оплаты
        if event_type == "payment.succeeded":
            if not booking_id:
                log_error(f"yookassa_webhook: booking_id не найден в metadata для payment_id={payment_id}")
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
                log_error(f"yookassa_webhook: бронь {booking_id} не найдена")
                return "error", 404
            
            # Обновляем статус только если ещё не оплачена
            if booking.get('status') != 'paid':
                log_info(f"Обновление статуса брони {booking_id} на 'paid' после успешной оплаты")
                bookings[booking_index]['status'] = 'paid'
                bookings[booking_index]['paid_at'] = datetime.now().isoformat()
                bookings[booking_index]['yookassa_payment_id'] = payment_id
                save_bookings(bookings)
                notify_payment_success(bookings[booking_index])
                notify_admin_payment_success(bookings[booking_index])
                log_info(f"Бронь {booking_id} успешно подтверждена после оплаты")
            else:
                log_info(f"Бронь {booking_id} уже была оплачена ранее")
            
            return "ok", 200
        
        elif event_type == "payment.waiting_for_capture":
            log_info(f"Платеж {payment_id} ожидает подтверждения (capture)")
        else:
            log_info(f"Событие {event_type} не обрабатывается")
        
        return "ok", 200
        
    except Exception as e:
        log_error(f"yookassa_webhook: {str(e)}", e)
        return "error", 500

# ====== ТОЧКА ВХОДА ======================================================

if __name__ == "__main__":
    log_info("=" * 60)
    log_info("🎵 MACHATA studio бот запущен!")
    log_info("✨ С полной поддержкой фискализации через ЮKassa")
    log_info(f"☎️ Контакт: {STUDIO_CONTACT}")
    log_info(f"📍 Telegram: {STUDIO_TELEGRAM}")
    if ADMIN_CHAT_ID > 0:
        log_info(f"👨‍💼 Админ-панель активна (ID: {ADMIN_CHAT_ID})")
        log_info("📋 Администратор может просматривать все бронирования")
        log_info("🔔 Система уведомлений администратора активна")
        # Запускаем фоновый поток для уведомлений
        notification_thread = threading.Thread(target=notification_worker, daemon=True)
        notification_thread.start()
        log_info("✅ Система уведомлений запущена (за 24ч и 30мин до брони)")
    else:
        log_info("⚠️ ADMIN_CHAT_ID не установлен - админ-панель недоступна")
        log_info("💡 Используйте команду /setadmin для временной настройки")
        log_info("💡 Или установите переменную ADMIN_CHAT_ID на Railway для постоянной настройки")
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
        platform_name = detect_platform()
        log_info(f"🌐 РЕЖИМ {platform_name} (webhook)")
        
        if not PUBLIC_URL:
            log_error("❌ PUBLIC_URL не установлен! Webhook не может быть настроен.")
            log_info("Переключаюсь на локальный режим (polling)...")
            try:
                bot.infinity_polling()
            except Exception as e:
                log_error(f"Ошибка polling: {str(e)}", e)
        else:
            webhook_url = f"{PUBLIC_URL}/{API_TOKEN}/"
            log_info(f"Webhook URL: {webhook_url}")
            
            try:
                # Удаляем старый webhook
                log_info("Удаление старого webhook...")
                bot.remove_webhook()
                time.sleep(1)
                
                # Устанавливаем новый webhook
                log_info("Установка нового webhook...")
                result = bot.set_webhook(url=webhook_url, drop_pending_updates=True)
                log_info(f"Результат установки webhook: {result}")
                
                # Проверяем статус webhook
                time.sleep(2)
                webhook_info = bot.get_webhook_info()
                log_info(f"✅ Webhook установлен")
                log_info(f"   URL: {webhook_info.url}")
                log_info(f"   Pending updates: {webhook_info.pending_update_count}")
                log_info(f"   Last error date: {webhook_info.last_error_date}")
                if webhook_info.last_error_message:
                    log_error(f"   Last error: {webhook_info.last_error_message}")
                
                log_info(f"🚀 Flask запущен на порту {PORT}")
                app.run(host="0.0.0.0", port=PORT, debug=False)
            except Exception as e:
                log_error(f"Ошибка webhook: {str(e)}", e)
            log_info("Переключаюсь на polling...")
            try:
                bot.infinity_polling()
            except Exception as e2:
                log_error(f"Ошибка polling: {str(e2)}", e2)
