#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from yookassa import Configuration, Payment
import uuid
from aiohttp import web
import calendar

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
WORKING_HOURS = list(range(10, 23))  # 10:00 - 22:00

# Хранилище бронирований и временных данных
bookings = {}
user_data = {}


def get_calendar_keyboard(year, month):
    """Создает клавиатуру календаря"""
    keyboard = []
    keyboard.append([InlineKeyboardButton(f"{calendar.month_name[month]} {year}", callback_data="ignore")])
    
    # Дни недели
    week_days = [InlineKeyboardButton(day, callback_data="ignore") for day in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']]
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
                    row.append(InlineKeyboardButton(str(day), callback_data=f"date_{year}_{month}_{day}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="book")])
    return InlineKeyboardMarkup(keyboard)


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
    
    user_id = query.from_user.id
    
    if query.data == 'ignore':
        return
    
    elif query.data == 'book':
        keyboard = [
            [InlineKeyboardButton("🕐 1 час (700₽)", callback_data='hours_1')],
            [InlineKeyboardButton("🕑 2 часа (1400₽)", callback_data='hours_2')],
            [InlineKeyboardButton("🕒 3 часа (2100₽)", callback_data='hours_3')],
            [InlineKeyboardButton("« Назад", callback_data='start')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⏱ Выберите продолжительность репетиции:",
            reply_markup=reply_markup
        )
    
    elif query.data.startswith('hours_'):
        hours = int(query.data.split('_')[1])
        user_data[user_id] = {'hours': hours, 'amount': hours * PRICE_PER_HOUR}
        
        now = datetime.now()
        calendar_markup = get_calendar_keyboard(now.year, now.month)
        await query.edit_message_text(
            "📅 Выберите дату репетиции:",
            reply_markup=calendar_markup
        )
    
    elif query.data.startswith('date_'):
        parts = query.data.split('_')
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        selected_date = datetime(year, month, day).date()
        
        user_data[user_id]['date'] = selected_date
        
        # Создаем кнопки для выбора времени
        keyboard = []
        for hour in WORKING_HOURS:
            keyboard.append([InlineKeyboardButton(f"{hour}:00", callback_data=f"time_{hour}")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"hours_{user_data[user_id]['hours']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🕕 Выберите время на {selected_date.strftime('%d.%m.%Y')}:",
            reply_markup=reply_markup
        )
    
    elif query.data.startswith('time_'):
        hour = int(query.data.split('_')[1])
        user_data[user_id]['time'] = f"{hour}:00"
        
        booking_data = user_data[user_id]
        hours = booking_data['hours']
        amount = booking_data['amount']
        date = booking_data['date']
        time = booking_data['time']
        prepayment = amount // 2
        
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
            [InlineKeyboardButton("❌ Отменить", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📋 Подтвердите бронирование:\n\n"
            f"📅 Дата: {date.strftime('%d.%m.%Y')}\n"
            f"🕐 Время: {time}\n"
            f"⏱ Продолжительность: {hours} ч.\n"
            f"💰 Стоимость: {amount}₽\n"
            f"💵 Предоплата: {prepayment}₽ (50%)\n\n"
            f"Для оплаты свяжитесь с администратором: [укажи контакт]",
            reply_markup=reply_markup
        )
