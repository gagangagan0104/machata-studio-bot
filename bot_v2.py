import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
import json
from yookassa import Configuration, Payment
import uuid

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
YOOKASSA_SHOP_ID = os.environ.get('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.environ.get('YOOKASSA_SECRET_KEY')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID')

# Настройка YooKassa
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# Хранилище бронирований (в реальном проекте использовать базу данных)
bookings = {}

# Цены на студии (в рублях)
PRICES = {
    'studio_a': {'name': 'Студия A', 'hourly_rate': 1500, 'description': 'Большая студия со звукоизоляцией'},
    'studio_b': {'name': 'Студия B', 'hourly_rate': 1200, 'description': 'Средняя студия с базовым оборудованием'},
    'studio_c': {'name': 'Студия C', 'hourly_rate': 800, 'description': 'Малая репетиционная студия'}
}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎸 Забронировать студию", callback_data='book_studio')],
        [InlineKeyboardButton("📊 Мои брони", callback_data='my_bookings')],
        [InlineKeyboardButton("ℹ️ Информация", callback_data='info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        'Добро пожаловать в Machata Music Studio! 🎵\n\n'
        'Здесь вы можете забронировать репетиционную студию.\n'
        'Выберите действие:',
        reply_markup=reply_markup
    )

# Обработка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'book_studio':
        await show_studios(query, context)
    elif query.data == 'my_bookings':
        await show_my_bookings(query, context)
    elif query.data == 'info':
        await show_info(query, context)
    elif query.data.startswith('select_studio_'):
        studio_id = query.data.replace('select_studio_', '')
        await show_date_selection(query, context, studio_id)
    elif query.data.startswith('select_date_'):
        await handle_date_selection(query, context)
    elif query.data.startswith('select_time_'):
        await handle_time_selection(query, context)
    elif query.data.startswith('select_hours_'):
        await handle_hours_selection(query, context)
    elif query.data.startswith('confirm_booking_'):
        await confirm_booking(query, context)
    elif query.data == 'back_to_main':
        await back_to_main(query, context)

# Показать список студий
async def show_studios(query, context):
    keyboard = []
    for studio_id, studio_info in PRICES.items():
        keyboard.append([
            InlineKeyboardButton(
                f"{studio_info['name']} - {studio_info['hourly_rate']}₽/час",
                callback_data=f'select_studio_{studio_id}'
            )
        ])
    keyboard.append([InlineKeyboardButton("← Назад", callback_data='back_to_main')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        'Выберите студию:',
        reply_markup=reply_markup
    )

# Показать выбор даты
async def show_date_selection(query, context, studio_id):
    context.user_data['selected_studio'] = studio_id
    
    keyboard = []
    # Показываем следующие 7 дней
    for i in range(7):
        date = datetime.now() + timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        date_display = date.strftime('%d.%m.%Y (%A)')
        keyboard.append([
            InlineKeyboardButton(date_display, callback_data=f'select_date_{date_str}')
        ])
    
    keyboard.append([InlineKeyboardButton("← Назад", callback_data='book_studio')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    studio_info = PRICES[studio_id]
    await query.edit_message_text(
        f'Выбрана {studio_info["name"]}\n'
        f'{studio_info["description"]}\n\n'
        f'Выберите дату:',
        reply_markup=reply_markup
    )

# Обработка выбора даты
async def handle_date_selection(query, context):
    date_str = query.data.replace('select_date_', '')
    context.user_data['selected_date'] = date_str
    
    # Показываем время (с 9:00 до 21:00)
    keyboard = []
    for hour in range(9, 21):
        time_str = f"{hour:02d}:00"
        keyboard.append([
            InlineKeyboardButton(time_str, callback_data=f'select_time_{hour}')
        ])
    
    keyboard.append([InlineKeyboardButton("← Назад", callback_data=f"select_studio_{context.user_data['selected_studio']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f'Дата: {date_str}\n'
        f'Выберите время начала:',
        reply_markup=reply_markup
    )

# Обработка выбора времени
async def handle_time_selection(query, context):
    hour = int(query.data.replace('select_time_', ''))
    context.user_data['selected_hour'] = hour
    
    # Показываем выбор количества часов (1-4 часа)
    keyboard = []
    studio_id = context.user_data['selected_studio']
    hourly_rate = PRICES[studio_id]['hourly_rate']
    
    for hours in range(1, 5):
        total_price = hourly_rate * hours
        keyboard.append([
            InlineKeyboardButton(
                f"{hours} час - {total_price}₽",
                callback_data=f'select_hours_{hours}'
            )
        ])
    
    keyboard.append([InlineKeyboardButton("← Назад", callback_data=f"select_date_{context.user_data['selected_date']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f'Время: {hour:02d}:00\n'
        f'Выберите продолжительность:',
        reply_markup=reply_markup
    )

# Обработка выбора количества часов
async def handle_hours_selection(query, context):
    hours = int(query.data.replace('select_hours_', ''))
    context.user_data['selected_hours'] = hours
    
    # Подготовка подтверждения
    studio_id = context.user_data['selected_studio']
    studio_info = PRICES[studio_id]
    date_str = context.user_data['selected_date']
    hour = context.user_data['selected_hour']
    total_price = studio_info['hourly_rate'] * hours
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить и оплатить", callback_data='confirm_booking_yes')],
        [InlineKeyboardButton("← Назад", callback_data=f'select_time_{hour}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f'Подтвердите бронирование:\n\n'
        f'Студия: {studio_info["name"]}\n'
        f'Дата: {date_str}\n'
        f'Время: {hour:02d}:00\n'
        f'Продолжительность: {hours} час\n'
        f'\n💳 Сумма к оплате: {total_price}₽',
        reply_markup=reply_markup
    )

# Подтверждение бронирования и создание платежа
async def confirm_booking(query, context):
    user_id = query.from_user.id
    studio_id = context.user_data['selected_studio']
    studio_info = PRICES[studio_id]
    date_str = context.user_data['selected_date']
    hour = context.user_data['selected_hour']
    hours = context.user_data['selected_hours']
    total_price = studio_info['hourly_rate'] * hours
    
    # Создаем платеж через YooKassa
    try:
        payment = Payment.create({
            "amount": {
                "value": f"{total_price}.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/your_bot_name"  # Заменить на вашего бота
            },
            "capture": True,
            "description": f"Бронь {studio_info['name']} на {date_str} в {hour:02d}:00",
            "metadata": {
                "user_id": str(user_id),
                "studio_id": studio_id,
                "date": date_str,
                "hour": str(hour),
                "hours": str(hours)
            }
        }, uuid.uuid4())
        
        # Сохраняем бронирование в ожидании оплаты
        booking_id = payment.id
        bookings[booking_id] = {
            'user_id': user_id,
            'studio_id': studio_id,
            'date': date_str,
            'hour': hour,
            'hours': hours,
            'total_price': total_price,
            'status': 'pending',
            'payment_id': payment.id
        }
        
        # Получаем ссылку на оплату
        payment_url = payment.confirmation.confirmation_url
        
        keyboard = [[InlineKeyboardButton("💳 Оплатить", url=payment_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f'Бронирование создано! \u2705\n\n'
            f'Студия: {studio_info["name"]}\n'
            f'Дата: {date_str}\n'
            f'Время: {hour:02d}:00\n'
            f'Продолжительность: {hours} час\n'
            f'Сумма: {total_price}₽\n\n'
            f'Нажмите кнопку ниже для оплаты.',
            reply_markup=reply_markup
        )
        
        # Уведомляем админа
        if ADMIN_CHAT_ID:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f'✨ Новое бронирование!\n'
                     f'User ID: {user_id}\n'
                     f'Студия: {studio_info["name"]}\n'
                     f'Дата: {date_str}\n'
                     f'Время: {hour:02d}:00\n'
                     f'Продолжительность: {hours} час\n'
                     f'Сумма: {total_price}₽\n'
                     f'Статус: Ожидает оплаты'
            )
    
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        await query.edit_message_text(
            f'❗️ Ошибка при создании платежа. Попробуйте позже.'
        )

# Показать мои брони
async def show_my_bookings(query, context):
    user_id = query.from_user.id
    user_bookings = [b for b in bookings.values() if b['user_id'] == user_id]
    
    if not user_bookings:
        keyboard = [[InlineKeyboardButton("← Назад", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            'У вас пока нет бронирований.',
            reply_markup=reply_markup
        )
        return
    
    text = 'Ваши бронирования:\n\n'
    for booking in user_bookings:
        studio_info = PRICES[booking['studio_id']]
        status_emoji = '✅' if booking['status'] == 'confirmed' else '🕒'
        text += f"{status_emoji} {studio_info['name']}\n"
        text += f"Дата: {booking['date']}\n"
        text += f"Время: {booking['hour']:02d}:00\n"
        text += f"Статус: {booking['status']}\n\n"
    
    keyboard = [[InlineKeyboardButton("← Назад", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

# Показать информацию
async def show_info(query, context):
    text = (
        '🎵 Machata Music Studio\n\n'
        'Мы предлагаем профессиональные репетиционные студии:\n\n'
    )
    
    for studio_id, studio_info in PRICES.items():
        text += f"• {studio_info['name']} - {studio_info['hourly_rate']}₽/час\n"
        text += f"  {studio_info['description']}\n\n"
    
    text += 'Рабочие часы: 9:00 - 21:00\n'
    text += 'Минимальное время брони: 1 час\n'
    text += 'Максимальное время брони: 4 часа'
    
    keyboard = [[InlineKeyboardButton("← Назад", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

# Вернуться в главное меню
async def back_to_main(query, context):
    keyboard = [
        [InlineKeyboardButton("🎸 Забронировать студию", callback_data='book_studio')],
        [InlineKeyboardButton("📊 Мои брони", callback_data='my_bookings')],
        [InlineKeyboardButton("ℹ️ Информация", callback_data='info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        'Добро пожаловать в Machata Music Studio! 🎵\n\n'
        'Здесь вы можете забронировать репетиционную студию.\n'
        'Выберите действие:',
        reply_markup=reply_markup
    )

# Webhook для YooKassa
async def yookassa_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Здесь должна быть логика обработки webhook от YooKassa
    # При получении уведомления об успешной оплате:
    # 1. Проверяем подпись
    # 2. Обновляем статус бронирования
    # 3. Уведомляем пользователя и админа
    pass

# Основная функция
def main():
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
