"""Telegram-бот для записи клиентов.

Клиент: выбирает услугу -> день -> время -> вводит имя -> отправляет телефон -> подтверждает.
Владелец: получает уведомление о каждой новой записи и отмене, смотрит записи командой /today.
"""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import date, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import config
import db

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

BTN_BOOK = "📅 Записаться"
BTN_MY = "🗓 Мои записи"
BTN_CONTACTS = "📍 Контакты"

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_BOOK)], [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_CONTACTS)]],
    resize_keyboard=True,
)

dp = Dispatcher()


class Booking(StatesGroup):
    """Шаги диалога записи (машина состояний)."""
    service = State()
    day = State()
    time = State()
    name = State()
    phone = State()
    confirm = State()


# ---------- вспомогательные функции ----------

def fmt_day(iso: str) -> str:
    """2026-10-20 -> 'Пн, 20 окт' (сегодня/завтра подписываются словами)."""
    d = date.fromisoformat(iso)
    text = f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"
    if d == date.today():
        return f"Сегодня, {d.day} {MONTHS[d.month - 1]}"
    if d == date.today() + timedelta(days=1):
        return f"Завтра, {d.day} {MONTHS[d.month - 1]}"
    return text


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """Собирает inline-клавиатуру из списка строк [(текст, callback_data), ...]."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=c) for t, c in row] for row in rows]
    )


def chunks(items: list, n: int) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def service_keys() -> list[str]:
    return list(config.SERVICES)


def services_kb() -> InlineKeyboardMarkup:
    # в callback_data передаём номер услуги: так короче и не ломается от эмодзи
    return kb([[(f"{name} · {price}", f"svc:{i}")] for i, (name, price) in enumerate(config.SERVICES.items())])


def booking_text(b) -> str:
    return f"{b['service']}, {fmt_day(b['day'])} в {b['time']}"


def summary(data: dict) -> str:
    lines = [f"Услуга: {data['service']} · {config.SERVICES[data['service']]}"]
    if "day" in data:
        lines.append(f"Дата: {fmt_day(data['day'])}")
    if "time" in data:
        lines.append(f"Время: {data['time']}")
    return "\n".join(lines)


async def notify_admin(bot: Bot, text: str) -> None:
    if config.ADMIN_ID:
        try:
            await bot.send_message(config.ADMIN_ID, text)
        except Exception as e:  # владелец мог не запустить бота — это не должно ломать запись
            logging.warning("Не удалось уведомить владельца: %s", e)


# ---------- главное меню (кнопки работают на любом шаге) ----------

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Здравствуйте, {html.escape(message.from_user.first_name)}! 👋\n\n"
        f"Это бот записи в <b>{config.BUSINESS_NAME}</b>.\n"
        "Запишитесь на удобное время за минуту, без звонков и ожидания.\n\n"
        "Выберите, что вас интересует 👇",
        reply_markup=MAIN_MENU,
    )


@dp.message(F.text == BTN_BOOK)
@dp.message(Command("book"))
async def book(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Booking.service)
    await message.answer("Какая услуга вас интересует?", reply_markup=services_kb())


@dp.message(F.text == BTN_CONTACTS)
@dp.message(Command("contacts"))
async def contacts(message: Message):
    await message.answer(
        f"<b>{config.BUSINESS_NAME}</b>\n\n"
        f"📍 {config.ADDRESS}\n"
        f"🕐 {config.WORK_HOURS_TEXT}\n"
        f"📞 {config.PHONE}",
        reply_markup=MAIN_MENU,
    )


@dp.message(Command("cancel"))
async def cancel_dialog(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Запись прервана. Можно начать заново в любой момент.", reply_markup=MAIN_MENU)


# ---------- шаг 1: услуга ----------

@dp.callback_query(Booking.service, F.data.startswith("svc:"))
async def choose_service(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":", 1)[1])
    keys = service_keys()
    if not 0 <= idx < len(keys):
        await call.answer("Такой услуги нет", show_alert=True)
        return
    await state.update_data(service=keys[idx])
    await show_days(call, state)


async def show_days(call: CallbackQuery, state: FSMContext):
    days = db.available_days()
    if not days:
        await call.message.edit_text("😔 К сожалению, на ближайшую неделю всё занято. Позвоните нам, подберём время.")
        await state.clear()
        return
    buttons = [(fmt_day(d.isoformat()), f"day:{d.isoformat()}") for d in days]
    rows = chunks(buttons, 2) + [[("« Назад", "back:service")]]
    await state.set_state(Booking.day)
    data = await state.get_data()
    await call.message.edit_text(f"{summary(data)}\n\n📅 Выберите день:", reply_markup=kb(rows))
    await call.answer()


# ---------- шаг 2: день ----------

@dp.callback_query(Booking.day, F.data.startswith("day:"))
async def choose_day(call: CallbackQuery, state: FSMContext):
    await state.update_data(day=call.data.split(":", 1)[1])
    await show_times(call, state)


async def show_times(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    slots = db.free_slots(date.fromisoformat(data["day"]))
    if not slots:
        await call.answer("На этот день всё занято, выберите другой", show_alert=True)
        await show_days(call, state)
        return
    rows = chunks([(s, f"time:{s}") for s in slots], 4) + [[("« Назад", "back:day")]]
    await state.set_state(Booking.time)
    await call.message.edit_text(f"{summary(data)}\n\n🕐 Выберите время:", reply_markup=kb(rows))
    await call.answer()


# ---------- кнопки «Назад» ----------

@dp.callback_query(F.data == "back:service")
async def back_to_service(call: CallbackQuery, state: FSMContext):
    await state.set_state(Booking.service)
    await call.message.edit_text("Какая услуга вас интересует?", reply_markup=services_kb())
    await call.answer()


@dp.callback_query(F.data == "back:day")
async def back_to_day(call: CallbackQuery, state: FSMContext):
    await show_days(call, state)


# ---------- шаг 3: время ----------

@dp.callback_query(Booking.time, F.data.startswith("time:"))
async def choose_time(call: CallbackQuery, state: FSMContext):
    t = call.data.split(":", 1)[1]
    data = await state.get_data()
    if t not in db.free_slots(date.fromisoformat(data["day"])):
        await call.answer("Это время только что заняли, выберите другое", show_alert=True)
        await show_times(call, state)
        return
    await state.update_data(time=t)
    await state.set_state(Booking.name)
    data = await state.get_data()
    await call.message.edit_text(f"{summary(data)}\n\n✍️ Как к вам обращаться? Напишите имя.")
    await call.answer()


# ---------- шаг 4: имя ----------

@dp.message(Booking.name, F.text)
async def enter_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not 2 <= len(name) <= 50:
        await message.answer("Напишите, пожалуйста, имя (от 2 до 50 символов).")
        return
    await state.update_data(name=name)
    await state.set_state(Booking.phone)
    await message.answer(
        f"Приятно познакомиться, {html.escape(name)}! 😊\n\n"
        "📱 Оставьте номер телефона, чтобы мастер мог связаться с вами. "
        "Нажмите кнопку ниже или напишите номер вручную.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


# ---------- шаг 5: телефон ----------

@dp.message(Booking.phone, F.contact | F.text)
async def enter_phone(message: Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    else:
        phone = message.text.strip()
        digits = "".join(ch for ch in phone if ch.isdigit())
        if not 10 <= len(digits) <= 15:
            await message.answer("Похоже, в номере ошибка. Например: +7 900 123-45-67")
            return
    await state.update_data(phone=phone)
    await state.set_state(Booking.confirm)
    data = await state.get_data()
    await message.answer("Почти готово!", reply_markup=MAIN_MENU)
    await message.answer(
        "<b>Проверьте, всё ли верно:</b>\n\n"
        f"{summary(data)}\n"
        f"Имя: {html.escape(data['name'])}\n"
        f"Телефон: {html.escape(phone)}",
        reply_markup=kb([[("✅ Подтвердить", "confirm:yes"), ("❌ Отменить", "confirm:no")]]),
    )


# ---------- шаг 6: подтверждение ----------

@dp.callback_query(Booking.confirm, F.data.startswith("confirm:"))
async def confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    if call.data == "confirm:no":
        await call.message.edit_text("Запись отменена. Будем рады видеть вас в другой раз!")
        await call.answer()
        return

    booking_id = db.add_booking(
        call.from_user.id, data["service"], data["day"], data["time"], data["name"], data["phone"]
    )
    if booking_id is None:
        await call.message.edit_text("😔 Увы, это время только что заняли. Нажмите «Записаться» и выберите другое.")
        await call.answer()
        return

    await call.message.edit_text(
        "🎉 <b>Вы записаны!</b>\n\n"
        f"{summary(data)}\n\n"
        f"📍 {config.ADDRESS}\n"
        f"📞 {config.PHONE}\n\n"
        "Ждём вас! Если планы изменятся, отменить запись можно в разделе «Мои записи»."
    )
    await call.answer("Готово!")
    await notify_admin(
        bot,
        f"🆕 <b>Новая запись #{booking_id}</b>\n\n"
        f"{data['service']}\n"
        f"{fmt_day(data['day'])} в {data['time']}\n"
        f"👤 {html.escape(data['name'])}\n"
        f"📞 {html.escape(data['phone'])}",
    )


# ---------- мои записи и отмена ----------

@dp.message(F.text == BTN_MY)
@dp.message(Command("my"))
async def my_bookings(message: Message, state: FSMContext):
    await state.clear()
    rows = db.user_bookings(message.from_user.id)
    if not rows:
        await message.answer("У вас пока нет записей. Нажмите «📅 Записаться» 👇", reply_markup=MAIN_MENU)
        return
    text = "<b>Ваши записи:</b>\n\n" + "\n".join(f"• {booking_text(b)}" for b in rows)
    buttons = [[(f"❌ Отменить: {fmt_day(b['day'])}, {b['time']}", f"del:{b['id']}")] for b in rows]
    await message.answer(text, reply_markup=kb(buttons))


@dp.callback_query(F.data.startswith("del:"))
async def delete_booking(call: CallbackQuery, bot: Bot):
    booking_id = int(call.data.split(":", 1)[1])
    b = db.get_booking(booking_id)
    if b and db.cancel_booking(booking_id, call.from_user.id):
        await call.message.edit_text(f"Запись отменена: {booking_text(b)}\n\nБудем рады видеть вас снова!")
        await notify_admin(
            bot,
            f"🚫 <b>Отмена записи #{booking_id}</b>\n\n{booking_text(b)}\n👤 {html.escape(b['name'])}\n📞 {html.escape(b['phone'])}",
        )
    else:
        await call.message.edit_text("Эта запись уже отменена.")
    await call.answer()


# ---------- для владельца ----------

@dp.message(Command("today", "tomorrow"))
async def admin_day(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    d = date.today()
    if message.text.startswith("/tomorrow"):
        d += timedelta(days=1)
    rows = db.bookings_for_day(d.isoformat())
    if not rows:
        await message.answer(f"{fmt_day(d.isoformat())}: записей нет.")
        return
    lines = [f"<b>{b['time']}</b> · {b['service']}\n     {html.escape(b['name'])}, {html.escape(b['phone'])}" for b in rows]
    await message.answer(f"📋 <b>{fmt_day(d.isoformat())}</b>, записей: {len(rows)}\n\n" + "\n\n".join(lines))


async def main():
    if not config.BOT_TOKEN:
        raise SystemExit("Не задан BOT_TOKEN. Создайте файл .env по образцу .env.example")
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    from aiogram.client.default import DefaultBotProperties
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    # меню команд слева от поля ввода
    await bot.set_my_commands([
        BotCommand(command="book", description="Записаться"),
        BotCommand(command="my", description="Мои записи"),
        BotCommand(command="contacts", description="Контакты"),
        BotCommand(command="start", description="Главное меню"),
    ])
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
