"""Работа с базой данных SQLite: хранение записей и проверка занятого времени."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import config


def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        # UNIQUE(day, time) не даёт двум клиентам занять один и тот же слот
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                service    TEXT    NOT NULL,
                day        TEXT    NOT NULL,   -- 2026-10-20
                time       TEXT    NOT NULL,   -- 14:00
                name       TEXT    NOT NULL,
                phone      TEXT    NOT NULL,
                created_at TEXT    NOT NULL,
                UNIQUE(day, time)
            )
            """
        )


def available_days(today: date | None = None) -> list[date]:
    """Рабочие дни на ближайшие DAYS_AHEAD дней, в которых ещё есть свободные слоты."""
    today = today or date.today()
    days = []
    for i in range(config.DAYS_AHEAD):
        d = today + timedelta(days=i)
        if d.weekday() not in config.DAYS_OFF and free_slots(d):
            days.append(d)
    return days


def all_slots() -> list[str]:
    slots = []
    t = datetime(2000, 1, 1, config.WORK_START_HOUR)
    end = datetime(2000, 1, 1, config.WORK_END_HOUR)
    while t < end:
        slots.append(t.strftime("%H:%M"))
        t += timedelta(minutes=config.SLOT_MINUTES)
    return slots


def free_slots(d: date, now: datetime | None = None) -> list[str]:
    """Свободное время на день: без занятых слотов и без уже прошедшего времени."""
    now = now or datetime.now()
    with connect() as conn:
        rows = conn.execute("SELECT time FROM bookings WHERE day = ?", (d.isoformat(),))
        busy = {r["time"] for r in rows}
    result = []
    for s in all_slots():
        if s in busy:
            continue
        slot_dt = datetime.combine(d, datetime.strptime(s, "%H:%M").time())
        if slot_dt <= now:
            continue
        result.append(s)
    return result


def add_booking(user_id: int, service: str, d: str, t: str, name: str, phone: str) -> int | None:
    """Сохраняет запись. Возвращает её id или None, если слот уже успели занять."""
    try:
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO bookings (user_id, service, day, time, name, phone, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, service, d, t, name, phone, datetime.now().isoformat(timespec="seconds")),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def user_bookings(user_id: int) -> list[sqlite3.Row]:
    today = date.today().isoformat()
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM bookings WHERE user_id = ? AND day >= ? ORDER BY day, time",
            (user_id, today),
        ).fetchall()


def bookings_for_day(d: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM bookings WHERE day = ? ORDER BY time", (d,)).fetchall()


def get_booking(booking_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()


def cancel_booking(booking_id: int, user_id: int) -> bool:
    """Отменяет запись, только если она принадлежит этому пользователю."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM bookings WHERE id = ? AND user_id = ?", (booking_id, user_id)
        )
        return cur.rowcount > 0
