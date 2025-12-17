import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

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

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Это Machata studio bot.\n"
        "Здесь можно забронировать репетицию и узнать правила студии.\n\n"
        "Выберите действие:",
        reply_markup=main_menu()
    )

# Цены
@dp.message(lambda message: message.text == "💰 Цены")
async def show_prices(message: types.Message):
    await message.answer(
        "Machata studio — почасовая аренда репетиционной комнаты.\n\n"
        "Стоимость:\n"
        "▪️ 1 час — 700₽\n"
        "▪️ 2 часа — 1200₽\n\n"
        "Предоплата — 50% от суммы.\n"
        "Остаток оплачивается в студии после репетиции.",
        reply_markup=main_menu()
    )

# Правила студии
@dp.message(lambda message: message.text == "📋 Правила студии")
async def show_rules(message: types.Message):
    await message.answer(
        "Правила Machata studio:\n\n"
        "▪️ Работаем круглосуточно по предварительной записи.\n"
        "▪️ Бронь удерживается 30 минут до внесения предоплаты, затем слот может быть освобождён.\n"
        "▪️ При опоздании более 15 минут время не продлевается.\n"
        "▪️ Бережно относитесь к оборудованию, обо всех неисправностях сообщайте администратору.\n"
        "▪️ Отмена за 24 часа и ранее — без штрафа, позже — предоплата не возвращается.\n\n"
        "Адрес студии: [укажи свой адрес]\n"
        "Для связи с администратором: [укажи контакт]",
        reply_markup=main_menu()
    )

# Бронирование (заглушка)
@dp.message(lambda message: message.text == "📅 Забронировать репетицию")
async def book_rehearsal(message: types.Message):
    await message.answer(
        "Функция бронирования в разработке.\n"
        "Пока свяжитесь с администратором для записи: [укажи контакт]",
        reply_markup=main_menu()
    )

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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
