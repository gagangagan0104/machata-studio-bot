# -*- coding: utf-8 -*-
import os

try:
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover - optional dependency for local runs
    psycopg2 = None


def _log(msg):
    # Локальный логгер, чтобы не зависеть от machata_bot.py
    print(msg, flush=True)


def get_database_url():
    return os.environ.get("DATABASE_URL", "").strip()


_is_enabled_cache = None

def is_enabled():
    global _is_enabled_cache
    if _is_enabled_cache is not None:
        return _is_enabled_cache
    
    db_url = get_database_url()
    has_url = bool(db_url)
    has_psycopg2 = psycopg2 is not None
    result = has_url and has_psycopg2
    _is_enabled_cache = result
    
    if not result:
        _log(f"[DB] ❌ БД отключена (DATABASE_URL: {has_url}, psycopg2: {has_psycopg2})")
    else:
        _log(f"[DB] ✅ БД включена и будет использоваться")
    return result


def _get_connection():
    db_url = get_database_url()
    if not db_url or psycopg2 is None:
        return None
    try:
        conn = psycopg2.connect(db_url, sslmode="require")
        _log("[DB] ✅ Подключение к БД установлено")
        return conn
    except Exception as e:
        _log(f"[DB] ❌ Ошибка подключения к БД: {e}")
        return None


def init_database():
    """Инициализация PostgreSQL, если DATABASE_URL задан."""
    _log("[DB] Начинаю инициализацию базы данных...")
    db_url = get_database_url()
    if not db_url:
        _log("[DB] ❌ DATABASE_URL не задан — используются JSON файлы")
        return
    if psycopg2 is None:
        _log("[DB] ❌ psycopg2 не установлен — используются JSON файлы")
        _log("[DB] 💡 Установите: pip install psycopg2-binary")
        return
    
    _log(f"[DB] ✅ DATABASE_URL найден (длина: {len(db_url)} символов)")
    _log(f"[DB] ✅ psycopg2 установлен: {psycopg2.__version__ if hasattr(psycopg2, '__version__') else 'да'}")
    
    try:
        conn = _get_connection()
        if conn is None:
            _log("[DB] ❌ Не удалось подключиться к БД — используются JSON файлы")
            return

        conn.autocommit = True
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id BIGINT PRIMARY KEY,
                user_id BIGINT,
                service TEXT,
                date TEXT,
                times JSONB,
                duration INTEGER,
                name TEXT,
                email TEXT,
                phone TEXT,
                comment TEXT,
                price INTEGER,
                status TEXT,
                created_at TEXT,
                paid_at TEXT,
                yookassa_payment_id TEXT,
                payment_url TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS vip_users (
                user_id BIGINT PRIMARY KEY,
                name TEXT,
                discount INTEGER,
                custom_price_repet INTEGER
            )
            """
        )

        cur.close()
        conn.close()
        _log("[DB] ✅ Таблицы проверены/созданы успешно")
        _log("[DB] ✅ Инициализация БД завершена")
    except Exception as e:
        _log(f"[DB] ❌ Ошибка инициализации БД: {e}")
        import traceback
        _log(f"[DB] Трассировка: {traceback.format_exc()}")


def get_all_bookings():
    conn = _get_connection()
    if conn is None:
        return []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM bookings ORDER BY created_at ASC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(row) for row in rows]
    except Exception:
        conn.close()
        raise


def get_booking_by_id(booking_id):
    conn = _get_connection()
    if conn is None:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception:
        conn.close()
        raise


def add_booking(booking):
    conn = _get_connection()
    if conn is None:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bookings (
                id, user_id, service, date, times, duration, name, email, phone,
                comment, price, status, created_at, paid_at, yookassa_payment_id, payment_url
            )
            VALUES (%(id)s, %(user_id)s, %(service)s, %(date)s, %(times)s, %(duration)s,
                    %(name)s, %(email)s, %(phone)s, %(comment)s, %(price)s, %(status)s,
                    %(created_at)s, %(paid_at)s, %(yookassa_payment_id)s, %(payment_url)s)
            ON CONFLICT (id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                service = EXCLUDED.service,
                date = EXCLUDED.date,
                times = EXCLUDED.times,
                duration = EXCLUDED.duration,
                name = EXCLUDED.name,
                email = EXCLUDED.email,
                phone = EXCLUDED.phone,
                comment = EXCLUDED.comment,
                price = EXCLUDED.price,
                status = EXCLUDED.status,
                created_at = EXCLUDED.created_at,
                paid_at = EXCLUDED.paid_at,
                yookassa_payment_id = EXCLUDED.yookassa_payment_id,
                payment_url = EXCLUDED.payment_url
            """,
            {
                **booking,
                "times": psycopg2.extras.Json(booking.get("times", [])),
            },
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        conn.close()
        raise


def save_bookings(bookings):
    for booking in bookings:
        add_booking(booking)


def cancel_booking(booking_id):
    conn = _get_connection()
    if conn is None:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = %s RETURNING *",
            (booking_id,),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception:
        conn.close()
        raise


def get_all_vip_users():
    conn = _get_connection()
    if conn is None:
        return {}
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM vip_users")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {int(row["user_id"]): dict(row) for row in rows}
    except Exception:
        conn.close()
        raise


def get_vip_user(user_id):
    conn = _get_connection()
    if conn is None:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM vip_users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception:
        conn.close()
        raise


def save_vip_users(vip_users):
    if not is_enabled():
        _log("[DB] save_vip_users: БД не включена, пропускаю")
        return
    _log(f"[DB] Сохранение {len(vip_users)} VIP пользователей в БД...")
    for user_id, data in vip_users.items():
        upsert_vip_user(user_id, data)
    _log(f"[DB] ✅ {len(vip_users)} VIP пользователей сохранено в БД")


def upsert_vip_user(user_id, data):
    conn = _get_connection()
    if conn is None:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO vip_users (user_id, name, discount, custom_price_repet)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                name = EXCLUDED.name,
                discount = EXCLUDED.discount,
                custom_price_repet = EXCLUDED.custom_price_repet
            """,
            (
                int(user_id),
                data.get("name"),
                data.get("discount"),
                data.get("custom_price_repet"),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        conn.close()
        raise


def remove_vip_user(user_id):
    conn = _get_connection()
    if conn is None:
        return
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM vip_users WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        conn.close()
        raise


def is_vip_user(user_id):
    return get_vip_user(user_id) is not None
