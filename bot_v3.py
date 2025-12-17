#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from yookassa import Configuration, Payment
import uuid

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get('BOT_TOKEN')
YOOKASSA_SHOP_ID = os.environ.get('YOOKASSA_SHOP_ID', '')
YOOKASSA_SECRET_KEY = os.environ.get('YOOKASSA_SECRET_KEY', '')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '')

# Настройка YooKassa
if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY

# Константы
PRICE_PER_HOUR = 700

# Хранилище бронирований (в продакшене использовать БД)
bookings = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = [
        [InlineKeyboardButton("📅 Забронировать репетицию", callback_data='book')],
        [InlineKeyboardButton("💰 Цены", callback_data='prices')],
        [InlineKeyboardButton("📍 Адрес студии", callback_data='address')],
        [InlineKeyboardButton("📞 Контакты", callback_data='contacts')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎵 Добро пожаловать в Machata Studio!\n\n"
        "Я помогу вам забронировать репетицию.\n"
        "Выберите нужное действие:",
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на inline кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'book':
        keyboard = [
            [InlineKeyboardButton("🕐 1 час (700₽)", callback_data='book_1')],
            [InlineKeyboardButton("🕑 2 часа (1400₽)", callback_data='book_2')],
            [InlineKeyboardButton("🕒 3 часа (2100₽)", callback_data='book_3')],
            [InlineKeyboardButton("« Назад", callback_data='start')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⏱ Выберите продолжительность репетиции:",
            reply_markup=reply_markup
        )
    
    elif query.data.startswith('book_'):
        hours = int(query.data.split('_')[1])
        amount = hours * PRICE_PER_HOUR
        
        # Создаём платёж через YooKassa
        if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
            try:
                payment = Payment.create({
                    "amount": {
                        "value": f"{amount}.00",
                        "currency": "RUB"
                    },
                    "confirmation": {
                        "type": "redirect",
                        "return_url": "https://t.me/MachataStudioBooking_bot"
                    },
                    "capture": True,
                    "description": f"Бронирование репетиции на {hours} ч.",
                    "metadata": {
                        "user_id": str(query.from_user.id),
                        "hours": str(hours)
                    }
                }, uuid.uuid4())
                
                # Сохраняем бронирование
                booking_id = payment.id
                bookings[booking_id] = {
                    'user_id': query.from_user.id,
                    'username': query.from_user.username,
                    'hours': hours,
                    'amount': amount,
                    'status': 'pending',
                    'created_at': datetime.now().isoformat()
                }
                
                keyboard = [
                    [InlineKeyboardButton("💳 Оплатить", url=payment.confirmation.confirmation_url)],
                    [InlineKeyboardButton("« Назад", callback_data='book')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ Бронирование создано!\n\n"
                    f"⏱ Длительность: {hours} ч.\n"
                    f"💰 Стоимость: {amount}₽\n\n"
                    f"Для подтверждения бронирования, пожалуйста, оплатите:\n",
                    reply_markup=reply_markup
                )
                
                # Уведомляем администратора
                if ADMIN_CHAT_ID:
                    try:
                        await context.bot.send_message(
                            chat_id=ADMIN_CHAT_ID,
                            text=f"🔔 Новое бронирование!\n\n"
                                 f"Пользователь: @{query.from_user.username or 'без username'}\n"
                                 f"ID: {query.from_user.id}\n"
                                 f"Длительность: {hours} ч.\n"
                                 f"Сумма: {amount}₽\n"
                                 f"ID платежа: {booking_id}\n"
                                 f"Статус: ⏳ Ожидает оплаты"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления администратору: {e}")
                
            except Exception as e:
                logger.error(f"Ошибка создания платежа: {e}")
                await query.edit_message_text(
                    "❌ Извините, произошла ошибка при создании платежа.\n"
                    "Пожалуйста, попробуйте позже или свяжитесь с нами напрямую."
                )
        else:
            await query.edit_message_text(
                f"📝 Ваш заказ:\n\n"
                f"⏱ Длительность: {hours} ч.\n"
                f"💰 Стоимость: {amount}₽\n\n"
                f"⚠️ Оплата временно недоступна. Свяжитесь с администратором для бронирования."
            )
    
    elif query.data == 'prices':
        keyboard = [[InlineKeyboardButton("« Назад", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "💰 Цены на аренду студии:\n\n"
            f"🕐 1 час — {PRICE_PER_HOUR}₽\n"
            f"🕑 2 часа — {PRICE_PER_HOUR * 2}₽\n"
            f"🕒 3 часа — {PRICE_PER_HOUR * 3}₽\n\n"
            "💳 Принимаем оплату картой через ЮKassa",
            reply_markup=reply_markup
        )
    
    elif query.data == 'address':
        keyboard = [[InlineKeyboardButton("« Назад", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📍 Адрес студии:\n\n"
            "Machata Studio\n"
            "г. Москва, ул. Примерная, д. 1\n\n"
            "🚇 Ближайшее метро: Примерная (5 мин пешком)",
            reply_markup=reply_markup
        )
    
    elif query.data == 'contacts':
        keyboard = [[InlineKeyboardButton("« Назад", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📞 Контакты:\n\n"
            "📱 Телефон: +7 (999) 123-45-67\n"
            "📧 Email: info@machatastudio.ru\n"
            "🌐 Сайт: machatastudio.ru\n\n"
            "Работаем ежедневно с 10:00 до 22:00",
            reply_markup=reply_markup
        )
    
    elif query.data == 'start':
        keyboard = [
            [InlineKeyboardButton("📅 Забронировать репетицию", callback_data='book')],
            [InlineKeyboardButton("💰 Цены", callback_data='prices')],
            [InlineKeyboardButton("📍 Адрес студии", callback_data='address')],
            [InlineKeyboardButton("📞 Контакты", callback_data='contacts')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🎵 Добро пожаловать в Machata Studio!\n\n"
            "Я помогу вам забронировать репетицию.\n"
            "Выберите нужное действие:",
            reply_markup=reply_markup
        )


async def check_payment_status(payment_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса платежа"""
    try:
        payment = Payment.find_one(payment_id)
        
        if payment.status == 'succeeded':
            booking = bookings.get(payment_id)
            if booking and booking['status'] == 'pending':
                booking['status'] = 'confirmed'
                
                # Уведомляем пользователя
                try:
                    await context.bot.send_message(
                        chat_id=booking['user_id'],
                        text=f"✅ Оплата успешно получена!\n\n"
                             f"Ваша репетиция на {booking['hours']} ч. подтверждена.\n"
                             f"Мы свяжемся с вами для уточнения времени."
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю: {e}")
                
                # Уведомляем администратора
                if ADMIN_CHAT_ID:
                    try:
                        await context.bot.send_message(
                            chat_id=ADMIN_CHAT_ID,
                            text=f"✅ Платёж подтверждён!\n\n"
                                 f"ID платежа: {payment_id}\n"
                                 f"Пользователь: @{booking.get('username', 'без username')}\n"
                                 f"Длительность: {booking['hours']} ч.\n"
                                 f"Сумма: {booking['amount']}₽"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления администратору: {e}")
        
        return payment.status
    except Exception as e:
        logger.error(f"Ошибка проверки статуса платежа: {e}")
        return None


def main():
    """Запуск бота"""
    if not TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return
    
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Запускаем бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
