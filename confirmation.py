"""
Обработчик подтверждения и оплаты бронирования
"""
import logging
import io
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, BufferedInputFile

from config import STUDIOS, ADMIN_CHAT_ID, PAYMENT_CARD, PAYMENT_PHONE
from database import BookingDatabase

from .booking_flow import BookingStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(
    F.data == "confirm_booking",
    StateFilter(BookingStates.confirming)
)
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    """Подтвердить бронирование и отправить инфу об оплате"""
    data = await state.get_data()

    required_fields = [
        "selected_date",
        "selected_time",
        "selected_hours",
        "amount",
        "studio_id",
    ]
    for field in required_fields:
        if field not in data:
            await callback.answer(
                "❌ Ошибка: не хватает данных бронирования",
                show_alert=True,
            )
            await state.clear()
            return

    user_id = callback.from_user.id
    studio_id = data["studio_id"]
    booking_date = data["selected_date"]
    booking_time = data["selected_time"]
    hours = data["selected_hours"]
    amount = data["amount"]

    booking_id = f"{user_id}_{booking_date}_{booking_time}_{datetime.now().timestamp()}"

    db = BookingDatabase()
    try:
        db.save_booking(
            {
                "id": booking_id,
                "user_id": user_id,
                "studio_id": studio_id,
                "date": booking_date,
                "time": booking_time,
                "hours": hours,
                "amount": amount,
            }
        )
    except Exception as e:
        logger.error(f"Ошибка при сохранении бронирования: {e}")
        await callback.answer(
            "❌ Ошибка при создании бронирования",
            show_alert=True,
        )
        await state.clear()
        return

    studio = STUDIOS[studio_id]
    date_obj = datetime.strptime(booking_date, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y (%A)")
    prepayment = amount // 2

    payment_text = (
        "<b>💰 Информация об оплате:</b>\n\n"
        f"📌 ID бронирования: <code>{booking_id}</code>\n"
        f"🎤 Студия: {studio.name}\n"
        f"📅 Дата: {date_formatted}\n"
        f"🕐 Время: {booking_time}:00\n"
        f"⏱️ Длительность: {hours} ч.\n\n"
        f"💳 Карта: <code>{PAYMENT_CARD}</code>\n"
        f"📱 Телефон: <code>{PAYMENT_PHONE}</code>\n"
        f"🤝 Сумма предоплаты: <b>{prepayment} ₽</b>\n\n"
        "<b>После оплаты:</b>\n"
        "1️⃣ Скиньте скрин платежа\n"
        "2️⃣ Напишите ID бронирования в чат\n"
        "3️⃣ Дождитесь подтверждения от администратора\n"
    )

    try:
        import qrcode

        qr_text = f"PAYMENT {prepayment} RUB for {studio.name} ({booking_id})"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_text)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        qr_file = BufferedInputFile(buf.read(), filename="payment_qr.png")
        await callback.message.edit_caption(
            caption=payment_text,
            parse_mode="HTML",
        )
        await callback.message.answer_photo(
            photo=qr_file,
            caption=payment_text,
            parse_mode="HTML",
        )
    except ImportError:
        await callback.message.edit_text(payment_text, parse_mode="HTML")
        logger.warning("qrcode not installed, отправлен только текст")
    except Exception as e:
        logger.error(f"Ошибка генерации QR: {e}")
        await callback.message.edit_text(payment_text, parse_mode="HTML")

    if ADMIN_CHAT_ID:
        admin_message = (
            "<b>🔔 Новое бронирование!</b>\n\n"
            f"👤 Пользователь: <code>{callback.from_user.full_name}</code>\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Username: @{callback.from_user.username or 'unknown'}\n\n"
            f"🎤 Студия: {studio.name}\n"
            f"📅 Дата: {date_formatted}\n"
            f"🕐 Время: {booking_time}:00\n"
            f"⏱️ Длительность: {hours} ч.\n\n"
            f"💰 Сумма: {amount} ₽\n"
            f"🤝 Предоплата: {prepayment} ₽\n\n"
            f"📌 ID бронирования: <code>{booking_id}</code>\n"
            "<b>Статус: ОЖИДАНИЕ ОПЛАТЫ</b>"
        )
        try:
            await callback.bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=admin_message,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить админа: {e}")

    await state.clear()
    await callback.answer(
        "✅ Бронирование создано! Ожидаем вашу оплату.",
        show_alert=True,
    )
