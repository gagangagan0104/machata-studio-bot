"""
Главный entry point для бота Machata Studio v2
"""
import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, USE_WEBHOOK, WEBHOOK_URL, PORT, LOG_LEVEL, DATABASE_PATH
from handlers.start import router as start_router
from handlers.booking_flow import router as booking_router
from handlers.confirmation import router as confirmation_router

# ============= ЛОГИРОВАНИЕ =============
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============= ИНИЦИАЛИЗАЦИЯ БОТА =============
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Регистрируем обработчики
dp.include_router(start_router)
dp.include_router(booking_router)
dp.include_router(confirmation_router)

# ============= WEBHOOK ОБРАБОТЧИКИ =============
async def webhook_handler(request: web.Request) -> web.Response:
    """Обработчик webhook от Telegram"""
    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Error processing webhook update: {e}")
        return web.Response(status=500, text="Error")


async def health_check(request: web.Request) -> web.Response:
    """Проверка здоровья сервиса"""
    return web.Response(text="OK")

# ============= MAIN =============
async def main():
    logger.info(f"BOT_TOKEN={'***' if BOT_TOKEN else 'NOT SET'}")
    logger.info(f"DATABASE_PATH={DATABASE_PATH}")
    logger.info(f"USE_WEBHOOK={USE_WEBHOOK}")

    if USE_WEBHOOK and WEBHOOK_URL:
        # ===== WEBHOOK (Render / production) =====
        logger.info("Starting bot in WEBHOOK mode")
        logger.info(f"WEBHOOK_URL={WEBHOOK_URL}")

        app = web.Application()
        app.router.add_get("/health", health_check)
        app.router.add_post("/webhook", webhook_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()

        logger.info(f"Web server started on port {PORT}")
        logger.info(f"Setting webhook to {WEBHOOK_URL}/webhook")

        try:
            await bot.set_webhook(
                url=f"{WEBHOOK_URL}/webhook",
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )
            logger.info("Webhook set successfully!")
            logger.info("Bot is ready to receive updates via webhook")
        except Exception as e:
            logger.error(f"Error setting webhook: {e}")
            raise

        try:
            # Держим процесс живым
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            await bot.delete_webhook()
            await runner.cleanup()

    else:
        # ===== POLLING (локально / VPS) =====
        logger.info("Starting bot in POLLING mode (local/VPS)")
        logger.info("Using polling to fetch updates from Telegram")

        # Удаляем старый webhook, если он есть
        try:
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                logger.info(f"Deleting existing webhook: {webhook_info.url}")
                await bot.delete_webhook(drop_pending_updates=True)
                await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Error checking/deleting webhook: {e}")
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                await asyncio.sleep(2)
            except Exception:
                pass

        # Запускаем polling
        try:
            logger.info("Starting polling...")
            await dp.start_polling(
                bot,
                allowed_updates=["message", "callback_query"],
            )
        except Exception as e:
            logger.error(f"Error in polling: {e}")
            raise

# ============= ENTRY POINT =============
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical error: {e}")
        raise
