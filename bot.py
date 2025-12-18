import os
import logging
import calendar
import io
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio

# Загрузка переменных окружения из .env файла
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен, используем только системные переменные окружения

try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not QR_AVAILABLE:
    logger.warning("qrcode library not installed. QR code generation will be disabled.")

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
PAYMENT_CARD = os.getenv("PAYMENT_CARD", "[укажи номер карты/кошелька]")
PAYMENT_PHONE = os.getenv("PAYMENT_PHONE", "")  # Для СБП
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Константы
PRICE_PER_HOUR = 700
WORKING_HOURS = list(range(10, 23))  # 10:00 - 22:00

# Студии (можно добавить несколько)
STUDIOS = {
    'studio_main': {
        'name': 'Главная студия',
        'description': 'Репетиционная студия с полным оборудованием',
        'price_per_hour': PRICE_PER_HOUR
    }
}

# Хранилище бронирований
# Формат: {booking_id: {user_id, studio_id, date, time, hours, amount, status, created_at}}
bookings = {}
user_bookings = {}  # {user_id: [booking_ids]}

# FSM для бронирования
class BookingStates(StatesGroup):
    choosing_studio = State()
    choosing_hours = State()
    choosing_date = State()
    choosing_time = State()
    confirming = State()

# Главное меню
def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Забронировать репетицию")],
            [KeyboardButton(text="📊 Мои бронирования")],
            [KeyboardButton(text="💰 Цены"), KeyboardButton(text="📋 Правила студии")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Генерация полноценного календаря
def get_calendar_keyboard(year=None, month=None):
    """Создает клавиатуру календаря"""
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    keyboard = []
    # Заголовок с месяцем и годом
    keyboard.append([InlineKeyboardButton(
        f"{calendar.month_name[month]} {year}", 
        callback_data="ignore"
    )])
    
    # Дни недели
    week_days = [InlineKeyboardButton(day, callback_data="ignore") 
                 for day in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']]
    keyboard.append(week_days)
    
    # Получаем календарь месяца
    month_calendar = calendar.monthcalendar(year, month)
    today = datetime.now().date()
    
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            else:
                date = datetime(year, month, day).date()
                if date < today:
                    row.append(InlineKeyboardButton(" ", callback_data="ignore"))
                else:
                    row.append(InlineKeyboardButton(
                        str(day), 
                        callback_data=f"date_{year}_{month}_{day}"
                    ))
        keyboard.append(row)
    
    # Навигация по месяцам
    nav_row = []
    if month > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"month_{year}_{month-1}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="ignore"))
    
    nav_row.append(InlineKeyboardButton("Сегодня", callback_data="today"))
    
    if month < 12:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"month_{year}_{month+1}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="ignore"))
    
    keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Генерация кнопок времени
def generate_time_keyboard(selected_date, selected_hours=1):
    keyboard = []
    
    # Проверяем занятые слоты для этой даты
    booked_times = set()
    for booking_id, booking in bookings.items():
        if booking.get('date') == selected_date and booking.get('status') == 'confirmed':
            booked_times.add(booking.get('time'))
    
    row = []
    for hour in WORKING_HOURS:
        time_str = f"{hour:02d}:00"
        
        # Проверяем, не пересекается ли время с уже забронированными
        is_booked = False
        for booked_time in booked_times:
            booked_hour = int(booked_time.split(':')[0])
            # Проверяем пересечение временных интервалов
            if hour < booked_hour + selected_hours and hour + selected_hours > booked_hour:
                is_booked = True
                break
        
        if is_booked:
            button_text = f"❌ {time_str}"
            callback_data = "booked"
        else:
            button_text = f"✅ {time_str}"
            callback_data = f"time_{time_str}"
        
        row.append(InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        ))
        
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_calendar")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🎵 Добро пожаловать в Machata Studio!\n\n"
        "Я помогу вам забронировать репетицию.\n"
        "Выберите нужное действие:",
        reply_markup=main_menu()
    )

# Цены
@dp.message(lambda message: message.text == "💰 Цены")
async def show_prices(message: types.Message):
    text = "💰 Стоимость репетиции:\n\n"
    text += f"⏱ 1 час: {PRICE_PER_HOUR}₽\n"
    text += f"⏱ 2 часа: {PRICE_PER_HOUR * 2}₽\n"
    text += f"⏱ 3 часа: {PRICE_PER_HOUR * 3}₽\n\n"
    text += "🕐 Часы работы: 10:00 - 22:00\n"
    text += "💳 Предоплата: 50% от суммы\n"
    text += "Остаток оплачивается в студии после репетиции."
    
    await message.answer(text, reply_markup=main_menu())

# Правила студии
@dp.message(lambda message: message.text == "📋 Правила студии")
async def show_rules(message: types.Message):
    await message.answer(
        "Правила Machata studio:\n\n"
        "▪️ Работаем по предварительной записи.\n"
        "▪️ Бронь удерживается 30 минут до внесения предоплаты, затем слот может быть освобождён.\n"
        "▪️ При опоздании более 15 минут время не продлевается.\n"
        "▪️ Бережно относитесь к оборудованию, обо всех неисправностях сообщайте администратору.\n"
        "▪️ Отмена за 24 часа и ранее — без штрафа, позже — предоплата не возвращается.\n\n"
        "📍 Адрес студии: [укажи свой адрес]\n"
        "📞 Для связи с администратором: [укажи контакт]",
        reply_markup=main_menu()
    )

# Просмотр своих бронирований
@dp.message(lambda message: message.text == "📊 Мои бронирования")
async def show_my_bookings(message: types.Message):
    user_id = message.from_user.id
    user_booking_ids = user_bookings.get(user_id, [])
    
    if not user_booking_ids:
        await message.answer(
            "У вас пока нет бронирований.\n"
            "Забронируйте репетицию через главное меню.",
            reply_markup=main_menu()
        )
        return
    
    text = "📊 Ваши бронирования:\n\n"
    for booking_id in user_booking_ids:
        if booking_id in bookings:
            booking = bookings[booking_id]
            status_emoji = "✅" if booking.get('status') == 'confirmed' else "🕒"
            date_obj = datetime.strptime(booking['date'], "%Y-%m-%d")
            text += f"{status_emoji} {date_obj.strftime('%d.%m.%Y')}\n"
            text += f"   🕐 Время: {booking['time']}\n"
            text += f"   ⏱ Продолжительность: {booking['hours']} ч.\n"
            text += f"   💰 Сумма: {booking['amount']}₽\n"
            text += f"   📍 Статус: {booking.get('status', 'pending')}\n\n"
    
    await message.answer(text, reply_markup=main_menu())

# Начало бронирования
@dp.message(lambda message: message.text == "📅 Забронировать репетицию")
async def start_booking(message: types.Message, state: FSMContext):
    # Если несколько студий - показываем выбор, иначе сразу переходим к выбору продолжительности
    if len(STUDIOS) > 1:
        keyboard = []
        for studio_id, studio_info in STUDIOS.items():
            keyboard.append([InlineKeyboardButton(
                f"{studio_info['name']} - {studio_info['price_per_hour']}₽/час",
                callback_data=f"studio_{studio_id}"
            )])
        keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        
        await message.answer(
            "Выберите студию:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.set_state(BookingStates.choosing_studio)
    else:
        # Только одна студия - сразу выбираем продолжительность
        studio_id = list(STUDIOS.keys())[0]
        await state.update_data(studio_id=studio_id)
        await show_hours_selection(message, state)

# Выбор продолжительности
async def show_hours_selection(message_or_callback, state: FSMContext):
    keyboard = [
        [InlineKeyboardButton(text="🕐 1 час (700₽)", callback_data="hours_1")],
        [InlineKeyboardButton(text="🕑 2 часа (1400₽)", callback_data="hours_2")],
        [InlineKeyboardButton(text="🕒 3 часа (2100₽)", callback_data="hours_3")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ]
    
    text = "⏱ Выберите продолжительность репетиции:"
    
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    else:
        await message_or_callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await message_or_callback.answer()

# Обработка выбора студии
@dp.callback_query(F.data.startswith("studio_"), StateFilter(BookingStates.choosing_studio))
async def process_studio_selection(callback: types.CallbackQuery, state: FSMContext):
    studio_id = callback.data.split("_")[1]
    if studio_id not in STUDIOS:
        await callback.answer("Ошибка: студия не найдена", show_alert=True)
        return
    
    await state.update_data(studio_id=studio_id)
    await show_hours_selection(callback, state)
    await state.set_state(BookingStates.choosing_hours)

# Обработка выбора продолжительности
@dp.callback_query(F.data.startswith("hours_"), StateFilter(BookingStates.choosing_hours))
async def process_hours_selection(callback: types.CallbackQuery, state: FSMContext):
    hours = int(callback.data.split("_")[1])
    data = await state.get_data()
    studio_id = data.get("studio_id", list(STUDIOS.keys())[0])
    studio_info = STUDIOS[studio_id]
    
    amount = studio_info['price_per_hour'] * hours
    await state.update_data(hours=hours, amount=amount)
    
    # Показываем календарь
    now = datetime.now()
    await callback.message.edit_text(
        "📅 Выберите дату репетиции:",
        reply_markup=get_calendar_keyboard(now.year, now.month)
    )
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()

# Обработка навигации по месяцам
@dp.callback_query(F.data.startswith("month_"), StateFilter(BookingStates.choosing_date))
async def process_month_navigation(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    year = int(parts[1])
    month = int(parts[2])
    
    await callback.message.edit_text(
        "📅 Выберите дату репетиции:",
        reply_markup=get_calendar_keyboard(year, month)
    )
    await callback.answer()

# Обработка выбора "Сегодня"
@dp.callback_query(F.data == "today", StateFilter(BookingStates.choosing_date))
async def process_today_selection(callback: types.CallbackQuery, state: FSMContext):
    now = datetime.now()
    selected_date = now.strftime("%Y-%m-%d")
    await state.update_data(date=selected_date)
    
    data = await state.get_data()
    hours = data.get("hours", 1)
    
    date_formatted = now.strftime("%d.%m.%Y")
    await callback.message.edit_text(
        f"Выбрана дата: {date_formatted}\n\nВыберите время:\n"
        f"✅ — свободно | ❌ — занято",
        reply_markup=generate_time_keyboard(selected_date, hours)
    )
    await state.set_state(BookingStates.choosing_time)
    await callback.answer()

# Обработка выбора даты
@dp.callback_query(F.data.startswith("date_"), StateFilter(BookingStates.choosing_date))
async def process_date_selection(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    year = int(parts[1])
    month = int(parts[2])
    day = int(parts[3])
    
    selected_date = datetime(year, month, day).strftime("%Y-%m-%d")
    await state.update_data(date=selected_date)
    
    data = await state.get_data()
    hours = data.get("hours", 1)
    
    date_formatted = datetime(year, month, day).strftime("%d.%m.%Y")
    await callback.message.edit_text(
        f"Выбрана дата: {date_formatted}\n\nВыберите время:\n"
        f"✅ — свободно | ❌ — занято",
        reply_markup=generate_time_keyboard(selected_date, hours)
    )
    await state.set_state(BookingStates.choosing_time)
    await callback.answer()

# Обработка выбора времени
@dp.callback_query(F.data.startswith("time_"), StateFilter(BookingStates.choosing_time))
async def process_time_selection(callback: types.CallbackQuery, state: FSMContext):
    selected_time = callback.data.split("_")[1]
    await state.update_data(time=selected_time)
    
    data = await state.get_data()
    date = data["date"]
    hours = data["hours"]
    amount = data["amount"]
    studio_id = data.get("studio_id", list(STUDIOS.keys())[0])
    studio_info = STUDIOS[studio_id]
    
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")
    prepayment = amount // 2
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")
        ]
    ])
    
    await callback.message.edit_text(
        f"📋 Подтвердите бронирование:\n\n"
        f"📍 Студия: {studio_info['name']}\n"
        f"📅 Дата: {date_formatted}\n"
        f"🕐 Время: {selected_time}\n"
        f"⏱ Продолжительность: {hours} ч.\n"
        f"💰 Стоимость: {amount}₽\n"
        f"💳 Предоплата: {prepayment}₽ (50%)\n\n"
        f"После подтверждения вы получите QR-код для оплаты.",
        reply_markup=keyboard
    )
    await state.set_state(BookingStates.confirming)
    await callback.answer()

# Подтверждение бронирования
@dp.callback_query(F.data == "confirm", StateFilter(BookingStates.confirming))
async def confirm_booking(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "date" not in data or "time" not in data or "hours" not in data:
        await callback.answer("Ошибка: данные бронирования не найдены. Начните заново.", show_alert=True)
        await state.clear()
        return
    
    date = data["date"]
    time = data["time"]
    hours = data["hours"]
    amount = data["amount"]
    studio_id = data.get("studio_id", list(STUDIOS.keys())[0])
    studio_info = STUDIOS[studio_id]
    user_id = callback.from_user.id
    
    # Проверяем, не занят ли уже этот слот
    for booking_id, booking in bookings.items():
        if (booking.get('date') == date and 
            booking.get('status') == 'confirmed' and
            booking.get('time') == time):
            await callback.answer("⚠️ Этот слот уже забронирован. Выберите другое время.", show_alert=True)
            await state.clear()
            return
    
    # Создаем ID бронирования
    booking_id = f"{user_id}_{date}_{time}_{datetime.now().timestamp()}"
    
    # Сохраняем бронирование
    bookings[booking_id] = {
        'user_id': user_id,
        'studio_id': studio_id,
        'date': date,
        'time': time,
        'hours': hours,
        'amount': amount,
        'status': 'pending',
        'created_at': datetime.now().isoformat()
    }
    
    # Добавляем в список бронирований пользователя
    if user_id not in user_bookings:
        user_bookings[user_id] = []
    user_bookings[user_id].append(booking_id)
    
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")
    prepayment = amount // 2
    
    # Формируем текст для QR-кода (СБП формат)
    qr_text = ""
    if PAYMENT_PHONE:
        # Формат для СБП: ST00012|Name=...|PersonalAcc=...|Sum=...|Purpose=...
        qr_text = f"ST00012|Name=Machata Studio|PersonalAcc={PAYMENT_PHONE}|Sum={prepayment}00|Purpose=Бронь {date_formatted} {time}"
    else:
        # Простой текст с реквизитами
        qr_text = f"Оплата {prepayment}₽\nБронь: {date_formatted} {time}\nКарта: {PAYMENT_CARD}"
    
    # Отправляем информацию о бронировании
    await callback.message.edit_text(
        f"✅ Бронирование создано!\n\n"
        f"📅 Дата: {date_formatted}\n"
        f"🕐 Время: {time}\n"
        f"⏱ Продолжительность: {hours} ч.\n"
        f"💰 Сумма: {amount}₽\n"
        f"💳 Предоплата: {prepayment}₽ (50%)\n\n"
        f"📱 Для оплаты отправьте {prepayment}₽ на:\n"
        f"💳 {PAYMENT_CARD}\n\n"
        f"После оплаты администратор подтвердит бронирование.\n\n"
        f"📞 Контакт администратора: [укажи контакт]"
    )
    
    # Генерируем и отправляем QR-код
    if QR_AVAILABLE:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_text)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Сохраняем в буфер
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            
            # Отправляем QR-код как фото
            qr_file = BufferedInputFile(buf.read(), filename="payment_qr.png")
            await callback.message.answer_photo(
                photo=qr_file,
                caption=f"📱 QR-код для оплаты {prepayment}₽"
            )
        except Exception as e:
            logger.error(f"Ошибка при генерации QR-кода: {e}")
            await callback.message.answer(
                f"💳 Для оплаты используйте реквизиты выше или свяжитесь с администратором."
            )
    
    # Здесь можно отправить QR-код как изображение
    # Для этого нужно установить библиотеку qrcode и pillow
    # Пример: await callback.message.answer_photo(photo=qr_image)
    
    # Уведомляем администратора
    if ADMIN_CHAT_ID:
        admin_message = (
            f"🆕 Новое бронирование!\n\n"
            f"👤 Пользователь: {callback.from_user.full_name} (@{callback.from_user.username})\n"
            f"🆔 ID: {user_id}\n"
            f"📍 Студия: {studio_info['name']}\n"
            f"📅 Дата: {date_formatted}\n"
            f"🕐 Время: {time}\n"
            f"⏱ Продолжительность: {hours} ч.\n"
            f"💰 Сумма: {amount}₽\n"
            f"💳 Предоплата: {prepayment}₽\n"
            f"📋 ID бронирования: {booking_id}"
        )
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление администратору: {e}")
    
    await state.clear()
    await callback.answer("Бронирование успешно создано!")

# Отмена бронирования
@dp.callback_query(F.data == "cancel")
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Бронирование отменено.")
    await callback.answer()

# Возврат к календарю
@dp.callback_query(F.data == "back_to_calendar", StateFilter(BookingStates.choosing_time))
async def back_to_calendar(callback: types.CallbackQuery, state: FSMContext):
    now = datetime.now()
    await callback.message.edit_text(
        "📅 Выберите дату репетиции:",
        reply_markup=get_calendar_keyboard(now.year, now.month)
    )
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()

# Обработка занятых слотов
@dp.callback_query(F.data == "booked")
async def booked_slot(callback: types.CallbackQuery):
    await callback.answer("⚠️ Этот слот уже забронирован", show_alert=True)

# Игнорирование служебных кнопок календаря
@dp.callback_query(F.data == "ignore")
async def ignore_callback(callback: types.CallbackQuery):
    await callback.answer()

# Healthcheck endpoint для Render
async def healthcheck(request):
    return web.Response(text="OK")

# Запуск бота и веб-сервера
async def main():
    # Создаём веб-приложение для healthcheck
    app = web.Application()
    app.router.add_get("/", healthcheck)
    app.router.add_get("/health", healthcheck)
    
    # Запускаем веб-сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logging.info(f"Web server started on port {PORT}")
    logging.info("Bot started")
    
    # Очищаем webhook и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling в фоне
    async def run_polling():
        await dp.start_polling(bot)
    
    asyncio.create_task(run_polling())
    
    # Держим сервис живым
    while True:
        await asyncio.sleep(3600)  # Проверяем каждый час

if __name__ == "__main__":
    asyncio.run(main())
