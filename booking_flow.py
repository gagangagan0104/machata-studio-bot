"""
Основной обработчик процесса бронирования
"""
import logging
import calendar
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
)

from config import STUDIOS, WORKING_HOURS
from database import BookingDatabase

logger = logging.getLogger(__name__)
router = Router()

# ============= FSM СОСТОЯНИЯ =============
class BookingStates(StatesGroup):
    choosing_studio = State()
    choosing_hours = State()
    choosing_date = State()
    choosing_time = State()
    confirming = State()

# ============= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =============
def format_date(date_str: str) -> str:
    """Форматировать дату для вывода"""
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%d.%m.%Y (%A)")


def generate_calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    """Генерировать календарь"""
    keyboard: list[list[InlineKeyboardButton]] = []

    # Заголовок месяц+год
    month_name = calendar.month_name[month]
    keyboard.append(
        [InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore")]
    )

    # Дни недели
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append(
        [InlineKeyboardButton(text=day, callback_data="ignore") for day in weekdays]
    )

    # Даты
    month_calendar = calendar.monthcalendar(year, month)
    today = datetime.now().date()

    for week in month_calendar:
        row: list[InlineKeyboardButton] = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                date = datetime(year, month, day).date()
                if date < today:
                    row.append(InlineKeyboardButton(text=str(day), callback_data="ignore"))
                else:
                    row.append(
                        InlineKeyboardButton(
                            text=str(day),
                            callback_data=f"date:{year}:{month}:{day}",
                        )
                    )
        keyboard.append(row)

    # Навигация по месяцам
    nav_row: list[InlineKeyboardButton] = []
    if month > 1:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️ Назад", callback_data=f"month:{year}:{month-1}"
            )
        )
    else:
        nav_row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))

    nav_row.append(InlineKeyboardButton(text="Сегодня", callback_data="today"))

    if month < 12:
        nav_row.append(
            InlineKeyboardButton(
                text="Вперед ▶️", callback_data=f"month:{year}:{month+1}"
            )
        )
    else:
        nav_row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))

    keyboard.append(nav_row)
    keyboard.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def generate_time_keyboard(
    db: BookingDatabase,
    studio_id: str,
    selected_date: str,
    selected_hours: int = 1,
) -> InlineKeyboardMarkup:
    """Генерировать клавиатуру с доступным временем"""
    booked_slots = db.get_booked_slots(studio_id, selected_date)

    keyboard: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for hour in WORKING_HOURS:
        time_str = f"{hour:02d}:00"

        is_available = db.is_time_available(
            studio_id, selected_date, time_str, selected_hours
        )

        if is_available:
            button_text = f"✅ {time_str}"
            callback_data = f"time:{time_str}"
        else:
            button_text = f"❌ {time_str}"
            callback_data = "booked"

        row.append(
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        )

        if len(row) == 3:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад к календарю", callback_data="back_to_calendar"
            ),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ============= ОБРАБОТЧИКИ =============

@router.message(lambda msg: msg.text and "Забронировать" in msg.text)
async def start_booking(message: Message, state: FSMContext):
    """Начать процесс бронирования"""
    if len(STUDIOS) == 1:
        studio_id = list(STUDIOS.keys())[0]
        await state.update_data(studio_id=studio_id)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="1 час (700₽)", callback_data="hours:1"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="2 часа (1400₽)", callback_data="hours:2"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="3 часа (2100₽)", callback_data="hours:3"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="cancel_booking"
                    )
                ],
            ]
        )
        await message.answer(
            "🎵 <b>Выберите длительность репетиции:</b>",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        await state.set_state(BookingStates.choosing_hours)
    else:
        keyboard_rows: list[list[InlineKeyboardButton]] = []
        for studio_id, studio in STUDIOS.items():
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{studio.name} - {studio.price_per_hour}₽/ч",
                        callback_data=f"studio:{studio_id}",
                    )
                ]
            )
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="cancel_booking"
                )
            ]
        )

        await message.answer(
            "🎤 <b>Выберите студию:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
            parse_mode="HTML",
        )
        await state.set_state(BookingStates.choosing_studio)


@router.callback_query(
    F.data.startswith("studio:"), StateFilter(BookingStates.choosing_studio)
)
async def select_studio(callback: CallbackQuery, state: FSMContext):
    studio_id = callback.data.split(":", 1)[1]

    if studio_id not in STUDIOS:
        await callback.answer("❌ Студия не найдена", show_alert=True)
        return

    await state.update_data(studio_id=studio_id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 час (700₽)", callback_data="hours:1")],
            [InlineKeyboardButton(text="2 часа (1400₽)", callback_data="hours:2")],
            [InlineKeyboardButton(text="3 часа (2100₽)", callback_data="hours:3")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")],
        ]
    )

    await callback.message.edit_text(
        "🎵 <b>Выберите длительность репетиции:</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(BookingStates.choosing_hours)
    await callback.answer()


@router.callback_query(
    F.data.startswith("hours:"), StateFilter(BookingStates.choosing_hours)
)
async def select_hours(callback: CallbackQuery, state: FSMContext):
    hours = int(callback.data.split(":", 1)[1])
    amount = 700 * hours

    await state.update_data(selected_hours=hours, amount=amount)

    now = datetime.now()
    keyboard = generate_calendar_keyboard(now.year, now.month)

    await callback.message.edit_text(
        f"📅 <b>Выберите дату (выбрано: {hours} ч. за {amount}₽):</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()


@router.callback_query(
    F.data.startswith("month:"), StateFilter(BookingStates.choosing_date)
)
async def navigate_month(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year = int(parts[1])
    month = int(parts[2])

    data = await state.get_data()
    hours = data.get("selected_hours", 1)
    amount = data.get("amount", 700)

    keyboard = generate_calendar_keyboard(year, month)

    await callback.message.edit_text(
        f"📅 <b>Выберите дату (выбрано: {hours} ч. за {amount}₽):</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    F.data == "today", StateFilter(BookingStates.choosing_date)
)
async def select_today(callback: CallbackQuery, state: FSMContext):
    now = datetime.now()

    data = await state.get_data()
    selected_hours = data.get("selected_hours", 1)
    studio_id = data.get("studio_id")

    selected_date = now.strftime("%Y-%m-%d")
    await state.update_data(selected_date=selected_date)

    db = BookingDatabase()
    keyboard = generate_time_keyboard(
        db, studio_id, selected_date, selected_hours
    )

    date_formatted = now.strftime("%d.%m.%Y")
    await callback.message.edit_text(
        f"🕐 <b>Выберите время начала (дата: {date_formatted}):</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(BookingStates.choosing_time)
    await callback.answer()


@router.callback_query(
    F.data.startswith("date:"), StateFilter(BookingStates.choosing_date)
)
async def select_date(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year = int(parts[1])
    month = int(parts[2])
    day = int(parts[3])

    selected_date = datetime(year, month, day).strftime("%Y-%m-%d")

    data = await state.get_data()
    selected_hours = data.get("selected_hours", 1)
    studio_id = data.get("studio_id")

    await state.update_data(selected_date=selected_date)

    db = BookingDatabase()
    keyboard = generate_time_keyboard(
        db, studio_id, selected_date, selected_hours
    )

    date_formatted = datetime(year, month, day).strftime("%d.%m.%Y")
    await callback.message.edit_text(
        f"🕐 <b>Выберите время начала (дата: {date_formatted}):</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(BookingStates.choosing_time)
    await callback.answer()


@router.callback_query(
    F.data.startswith("time:"), StateFilter(BookingStates.choosing_time)
)
async def select_time(callback: CallbackQuery, state: FSMContext):
    """КРИТИЧНЫЙ ОБРАБОТЧИК: выбор времени"""
    time_str = callback.data.split(":", 1)[1]

    data = await state.get_data()
    selected_date = data.get("selected_date")
    selected_hours = data.get("selected_hours", 1)
    studio_id = data.get("studio_id")
    amount = data.get("amount")

    db = BookingDatabase()
    if not db.is_time_available(studio_id, selected_date, time_str, selected_hours):
        await callback.answer("❌ Это время уже занято!", show_alert=True)
        keyboard = generate_time_keyboard(
            db, studio_id, selected_date, selected_hours
        )
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        return

    await state.update_data(selected_time=time_str)

    studio = STUDIOS[studio_id]
    date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")
    prepayment = amount // 2

    confirmation_text = (
        "<b>✅ Проверьте данные бронирования:</b>\n\n"
        f"📍 Студия: {studio.name}\n"
        f"📅 Дата: {date_formatted}\n"
        f"🕐 Время начала: <b>{time_str}:00</b>\n"
        f"⏱️ Длительность: <b>{selected_hours} ч.</b>\n"
        f"💰 Сумма: <b>{amount} ₽</b>\n"
        f"🤝 Предоплата (50%): <b>{prepayment} ₽</b>\n\n"
        "<i>Рабочее время: 10:00 - 22:00</i>"
    )

    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="confirm_booking"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к календарю", callback_data="back_to_calendar"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="cancel_booking"
                )
            ],
        ]
    )

    await callback.message.edit_text(
        confirmation_text,
        reply_markup=confirm_keyboard,
        parse_mode="HTML",
    )
    await state.set_state(BookingStates.confirming)
    await callback.answer()


@router.callback_query(
    F.data == "back_to_calendar", StateFilter(BookingStates.choosing_time)
)
async def back_to_calendar(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_hours = data.get("selected_hours", 1)
    amount = data.get("amount", 700)

    now = datetime.now()
    keyboard = generate_calendar_keyboard(now.year, now.month)

    await callback.message.edit_text(
        f"📅 <b>Выберите дату (выбрано: {selected_hours} ч. за {amount}₽):</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()


@router.callback_query(F.data == "booked")
async def booked_slot(callback: CallbackQuery):
    await callback.answer("❌ Это время уже забронировано", show_alert=True)


@router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Бронирование отменено")
    await callback.answer()


@router.callback_query(F.data == "ignore")
async def ignore_button(callback: CallbackQuery):
    await callback.answer()
