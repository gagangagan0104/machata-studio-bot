#!/usr/bin/env python3
"""
Скрипт для проверки и удаления webhook бота
Используйте этот скрипт, если возникают конфликты с polling
"""
import os
import sys
import asyncio
from aiogram import Bot

async def check_and_delete_webhook():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not found in environment variables")
        sys.exit(1)
    
    bot = Bot(token=BOT_TOKEN)
    
    try:
        # Проверяем текущий webhook
        webhook_info = await bot.get_webhook_info()
        print(f"Current webhook info:")
        print(f"  URL: {webhook_info.url or 'Not set'}")
        print(f"  Pending updates: {webhook_info.pending_update_count}")
        
        if webhook_info.url:
            print(f"\nDeleting webhook: {webhook_info.url}")
            result = await bot.delete_webhook(drop_pending_updates=True)
            print(f"Delete result: {result}")
            
            # Проверяем снова
            webhook_info = await bot.get_webhook_info()
            print(f"\nAfter deletion:")
            print(f"  URL: {webhook_info.url or 'Not set (OK for polling)'}")
            print("✅ Webhook deleted successfully! Bot can now use polling.")
        else:
            print("\n✅ No webhook found. Bot can use polling.")
    
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    # Загружаем .env если есть
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    asyncio.run(check_and_delete_webhook())

