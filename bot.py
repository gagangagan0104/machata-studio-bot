import os
import logging
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Простое хранилище бронирований (в памяти)
bookings = {}  # {date: {time: user_id}}

# FSM для бронирования
class BookingStates(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    confirming = State()

# Главное меню
def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Забронировать репетицию")],
            [KeyboardButton(text="💰 Цены"), KeyboardButton(text="📋 Правила студии")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Генерация календаря на следующие 7 дней
def generate_calendar_keyboard():
    keyboard = []
    today = datetime.now()
    
    row = []
    for i in range(7):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m")
        callback_data = date.strftime("%Y-%m-%d")
        
        row.append(InlineKeyboardButton(
            text=date_str,
            callback_data=f"date_{callback_data}"
        ))
        
        if len(row) == 3 or i == 6:
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Генерация кнопок времени (с 9:00 до 23:00, 24/7)
def generate_time_keyboard(selected_date):
    keyboard = []
    
    # Генерируем слоты по часам
    hours = list(range(9, 24))  # 9:00-23:00
    
    row = []
    for hour in hours:
        time_str = f"{hour:02d}:00"
        
        # Проверяем, занят ли слот
        is_booked = selected_date in bookings and time_str in bookings[selected_date]
        
        if is_booked:
            # Занятый слот
            button_text = f"❌ {time_str}"
            callback_data = "booked"
        else:
            # Свободный слот
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
        "Привет! Это Machata studio bot.\\n"
        "Здесь можно забронировать репетицию и узнать правила студии.\\n\\n"
        "Выберите действие:",
        reply_markup=main_menu()
    )

# Цены
@dp.message(lambda message: message.text == "💰 Цены")
async def show_prices(message: types.Message):
    await message.answer(
        "Machata studio — почасовая аренда репетиционной комнаты.\\n\\n"
        "Стоимость:\\n"
        "▪️ 1 час — 700₽\\n"
        "▪️ 2 часа — 1200₽\\n\\n"
        "Предоплата — 50% от суммы.\\n"
        "Остаток оплачивается в студии после репетиции.",
        reply_markup=main_menu()
    )

# Правила студии
@dp.message(lambda message: message.text == "📋 Правила студии")
async def show_rules(message: types.Message):
    await message.answer(
        "Правила Machata studio:\\n\\n"
        "▪️ Работаем круглосуточно по предварительной записи.\\n"
        "▪️ Бронь удерживается 30 минут до внесения предоплаты, затем слот может быть освобождён.\\n"
        "▪️ При опоздании более 15 минут время не продлевается.\\n"
        "▪️ Бережно относитесь к оборудованию, обо всех неисправностях сообщайте администратору.\\n"
        "▪️ Отмена за 24 часа и ранее — без штрафа, позже — предоплата не возвращается.\\n\\n"
        "Адрес студии: [укажи свой адрес]\\n"
        "Для связи с администратором: [укажи контакт]",
        reply_markup=main_menu()
    )

# Начало бронирования
@dp.message(lambda message: message.text == "📅 Забронировать репетицию")
async def start_booking(message: types.Message, state: FSMContext):
    await message.answer(
        "Выберите дату репетиции:",
        reply_markup=generate_calendar_keyboard()
    )
    await state.set_state(BookingStates.choosing_date)

# Обработка выбора даты
@dp.callback_query(F.data.startswith("date_"), StateFilter(BookingStates.choosing_date))
async def process_date_selection(callback: types.CallbackQuery, state: FSMContext):
    selected_date = callback.data.split("_")[1]
    await state.update_data(date=selected_date)
    
    date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")
    
    await callback.message.edit_text(
        f"Выбрана дата: {date_formatted}\\n\\nВыберите время:\\n"
        f"✅ — свободно | ❌ — занято",
        reply_markup=generate_time_keyboard(selected_date)
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
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")
        ]
    ])
    
    await callback.message.edit_text(
        f"Подтвердите бронирование:\\n\\n"
        f"📅 Дата: {date_formatted}\\n"
        f"🕐 Время: {selected_time}\\n"
        f"💰 Стоимость: 700₽\\n"
        f"💳 Предоплата: 350₽ (50%)\\n\\n"
        f"Для оплаты свяжитесь с администратором: [укажи контакт]",
        reply_markup=keyboard
    )
    await state.set_state(BookingStates.confirming)
    await callback.answer()

# Подтверждение бронирования
@dp.callback_query(F.data == "confirm", StateFilter(BookingStates.confirming))
async def confirm_booking(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    date = data["date"]
    time = data["time"]
    user_id = callback.from_user.id
    
    # Сохраняем бронирование
    if date not in bookings:
        bookings[date] = {}
    bookings[date][time] = user_id
    
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")
    
    await callback.message.edit_text(
        f"✅ Бронирование подтверждено!\\n\\n"
        f"📅 Дата: {date_formatted}\\n"
        f"🕐 Время: {time}\\n\\n"
        f"Внесите предоплату 350₽ в течение 30 минут.\\n"
        f"После оплаты слот будет зарезервирован за вами.\\n\\n"
        f"Контакт администратора: [укажи контакт]"
    )
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
    await callback.message.edit_text(
        "Выберите дату репетиции:",
        reply_markup=generate_calendar_keyboard()
    )
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()

# Обработка занятых слотов
@dp.callback_query(F.data == "booked")
async def booked_slot(callback: types.CallbackQuery):
    await callback.answer("⚠️ Этот слот уже забронирован", show_alert=True)

# Healthcheck endpoint для Render
async def healthcheck(request):
    return web.Response(text="OK")

# Запуск бота и веб-сервера
async def main():
    # Создаём веб-приложение для healthcheck
    app = web.Application()
    app.router.add_get("/", healthcheck)
    app.router.add_get("/health", healthcheck)

    # Запускаем веб-сервер и бота параллельно
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info(f"Web server started on port {PORT}")
    logging.info("Bot started")

    # Запускаем polling бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
