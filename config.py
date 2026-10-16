"""Настройки бота. Всё, что меняется под конкретного клиента, лежит здесь."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Токен бота от @BotFather и Telegram ID владельца бизнеса (кто получает уведомления)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# О бизнесе
BUSINESS_NAME = "Студия красоты «Шарм»"
ADDRESS = "Москва, ул. Пример, 10, 2 этаж"
PHONE = "+7 (900) 000-00-00"
WORK_HOURS_TEXT = "Пн–Сб, 10:00–19:00"

# Услуги: название -> цена
SERVICES = {
    "💇‍♀️ Стрижка": "1 500 ₽",
    "🎨 Окрашивание": "4 500 ₽",
    "💅 Маникюр": "2 000 ₽",
    "✨ Укладка": "1 200 ₽",
}

# Расписание
WORK_START_HOUR = 10   # первый слот в 10:00
WORK_END_HOUR = 19     # последний слот начинается в 18:00
SLOT_MINUTES = 60      # длительность одного слота
DAYS_AHEAD = 7         # на сколько дней вперёд можно записаться
DAYS_OFF = {6}         # выходные: 0 = понедельник ... 6 = воскресенье

DB_PATH = "bookings.db"
