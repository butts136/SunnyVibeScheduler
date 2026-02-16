import base64
import calendar as pycalendar
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-me')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

DATA_DIR = Path(__file__).resolve().parent / 'data'
ADMIN_STORE_PATH = DATA_DIR / 'admin_account.json'
ADMIN_KEY_PATH = DATA_DIR / 'admin_account.key'
OPENING_HOURS_PATH = DATA_DIR / 'opening_hours.json'
DATABASE_PATH = DATA_DIR / 'sunnyvibe.db'
RESERVATION_CONFIG_PATH = DATA_DIR / 'reservation_config.json'
INVITATION_CONFIG_PATH = DATA_DIR / 'invitation_config.json'

DAY_CONFIG = [
    ('monday', 'Lundi', 1),
    ('tuesday', 'Mardi', 2),
    ('wednesday', 'Mercredi', 3),
    ('thursday', 'Jeudi', 4),
    ('friday', 'Vendredi', 5),
    ('saturday', 'Samedi', 6),
    ('sunday', 'Dimanche', 0),
]

VALID_SLOT_INTERVALS = {15, 30, 60}
FRENCH_MONTHS = {
    1: 'Janvier',
    2: 'Février',
    3: 'Mars',
    4: 'Avril',
    5: 'Mai',
    6: 'Juin',
    7: 'Juillet',
    8: 'Août',
    9: 'Septembre',
    10: 'Octobre',
    11: 'Novembre',
    12: 'Décembre',
}
SESSION_IDLE_TIMEOUT_SECONDS = 60 * 60
BLOCKED_SLOT_REPEAT_OPTIONS = [
    ('once', 'Une seule fois'),
    ('weekly', 'Chaque semaine'),
    ('yearly', 'Chaque année (même date)'),
    ('holiday', 'À chaque journée fériée'),
]
BLOCKED_SLOT_REPEAT_LABELS = {
    option_key: option_label for option_key, option_label in BLOCKED_SLOT_REPEAT_OPTIONS
}
DEFAULT_HOLIDAY_ALERT = "Congé férié du Québec. Horaire spécial possible pour cette journée."
QUEBEC_FIXED_HOLIDAYS = [
    ('Jour de l’an', '01-01'),
    ('Fête nationale du Québec', '06-24'),
    ('Fête du Canada', '07-01'),
    ('Noël', '12-25'),
]


def _get_db_connection():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _init_db():
    conn = _get_db_connection()
    try:
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                phone TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                is_blocked INTEGER NOT NULL DEFAULT 0,
                reservation_limit INTEGER,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CHECK (email IS NOT NULL OR phone IS NOT NULL)
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                start DATETIME NOT NULL,
                end DATETIME NOT NULL,
                title TEXT,
                allow_companion INTEGER NOT NULL DEFAULT 0,
                companion_count INTEGER NOT NULL DEFAULT 0,
                is_private INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_bookings_start ON bookings(start);
            CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings(user_id);

            CREATE TABLE IF NOT EXISTS invitation_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                expires_at DATETIME NOT NULL,
                used_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS blocked_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                repeat_type TEXT NOT NULL DEFAULT 'once',
                date_value TEXT,
                weekday INTEGER,
                month_day TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                range_start TEXT,
                range_end TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_blocked_slots_repeat ON blocked_slots(repeat_type);
            '''
        )
        user_columns = {
            row['name'] for row in conn.execute('PRAGMA table_info(users)').fetchall()
        }
        if 'is_blocked' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0')
        if 'reservation_limit' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN reservation_limit INTEGER')
        if 'must_change_password' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0')
        if 'birth_date' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN birth_date TEXT')
        if 'security_question_1' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN security_question_1 TEXT')
        if 'security_answer_hash_1' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN security_answer_hash_1 TEXT')
        if 'security_question_2' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN security_question_2 TEXT')
        if 'security_answer_hash_2' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN security_answer_hash_2 TEXT')
        if 'security_question_3' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN security_question_3 TEXT')
        if 'security_answer_hash_3' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN security_answer_hash_3 TEXT')
        booking_columns = {
            row['name'] for row in conn.execute('PRAGMA table_info(bookings)').fetchall()
        }
        if 'allow_companion' not in booking_columns:
            conn.execute('ALTER TABLE bookings ADD COLUMN allow_companion INTEGER NOT NULL DEFAULT 0')
        if 'companion_count' not in booking_columns:
            conn.execute('ALTER TABLE bookings ADD COLUMN companion_count INTEGER NOT NULL DEFAULT 0')
        if 'is_private' not in booking_columns:
            conn.execute('ALTER TABLE bookings ADD COLUMN is_private INTEGER NOT NULL DEFAULT 0')
        conn.commit()
    finally:
        conn.close()


def _default_opening_hours():
    return {
        'monday': {'closed': False, 'start': '09:00', 'end': '17:00'},
        'tuesday': {'closed': False, 'start': '08:00', 'end': '14:00'},
        'wednesday': {'closed': False, 'start': '10:00', 'end': '18:00'},
        'thursday': {'closed': False, 'start': '09:00', 'end': '15:00'},
        'friday': {'closed': False, 'start': '09:00', 'end': '16:00'},
        'saturday': {'closed': False, 'start': '10:00', 'end': '13:00'},
        'sunday': {'closed': True, 'start': '09:00', 'end': '09:00'},
    }


def _time_text_to_minutes(time_text):
    if not re.fullmatch(r'\d{2}:\d{2}', time_text):
        return None

    hour_text, minute_text = time_text.split(':', 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    return hour * 60 + minute


def _normalize_opening_hours(raw_hours):
    normalized = _default_opening_hours()
    if not isinstance(raw_hours, dict):
        return normalized

    for day_key, _, _ in DAY_CONFIG:
        day_value = raw_hours.get(day_key, {})
        if not isinstance(day_value, dict):
            continue

        closed = bool(day_value.get('closed', False))
        start = str(day_value.get('start', normalized[day_key]['start']))
        end = str(day_value.get('end', normalized[day_key]['end']))

        if _time_text_to_minutes(start) is None:
            start = normalized[day_key]['start']
        if _time_text_to_minutes(end) is None:
            end = normalized[day_key]['end']

        normalized[day_key] = {
            'closed': closed,
            'start': start,
            'end': end,
        }

    return normalized


def _normalize_holidays(raw_holidays):
    if not isinstance(raw_holidays, list):
        return []

    normalized = []
    for item in raw_holidays:
        if not isinstance(item, dict):
            continue

        name = str(item.get('name', '')).strip()
        if not name:
            continue

        date_text = str(item.get('date', '')).strip()
        month_day_text = str(item.get('month_day', '')).strip()
        alert = str(item.get('alert', '')).strip()

        has_valid_date = bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', date_text))
        has_valid_month_day = bool(re.fullmatch(r'\d{2}-\d{2}', month_day_text))
        if not has_valid_date and not has_valid_month_day:
            continue

        normalized.append(
            {
                'name': name,
                'date': date_text if has_valid_date else '',
                'month_day': month_day_text if has_valid_month_day else '',
                'alert': alert or "L'horaire officiel est affiché ici. De légères différences peuvent survenir selon les options de configuration à venir.",
            }
        )

    return normalized


def _calculate_easter_sunday(year):
    # Computus (calendrier grégorien)
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = ((19 * a) + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + (2 * e) + (2 * i) - h - k) % 7
    m = (a + (11 * h) + (22 * l)) // 451
    month = (h + l - (7 * m) + 114) // 31
    day = ((h + l - (7 * m) + 114) % 31) + 1
    return datetime(year, month, day).date()


def _first_weekday_in_month(year, month, weekday):
    current = datetime(year, month, 1).date()
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current


def _nth_weekday_in_month(year, month, weekday, nth):
    first = _first_weekday_in_month(year, month, weekday)
    return first + timedelta(days=7 * max(nth - 1, 0))


def _quebec_dynamic_holidays_for_year(year):
    easter = _calculate_easter_sunday(year)
    good_friday = easter - timedelta(days=2)
    easter_monday = easter + timedelta(days=1)

    patriots_day = datetime(year, 5, 24).date()
    while patriots_day.weekday() != 0:
        patriots_day -= timedelta(days=1)

    labour_day = _first_weekday_in_month(year, 9, 0)
    thanksgiving = _nth_weekday_in_month(year, 10, 0, 2)

    return [
        ('Vendredi saint', good_friday.strftime('%Y-%m-%d')),
        ('Lundi de Pâques', easter_monday.strftime('%Y-%m-%d')),
        ('Journée nationale des Patriotes', patriots_day.strftime('%Y-%m-%d')),
        ('Fête du Travail', labour_day.strftime('%Y-%m-%d')),
        ('Action de grâce', thanksgiving.strftime('%Y-%m-%d')),
    ]


def _merge_with_quebec_holidays(holidays):
    now_year = datetime.now().year
    generated = []

    for name, month_day in QUEBEC_FIXED_HOLIDAYS:
        generated.append(
            {
                'name': name,
                'date': '',
                'month_day': month_day,
                'alert': DEFAULT_HOLIDAY_ALERT,
            }
        )

    for year in range(now_year - 1, now_year + 11):
        for name, date_text in _quebec_dynamic_holidays_for_year(year):
            generated.append(
                {
                    'name': name,
                    'date': date_text,
                    'month_day': '',
                    'alert': DEFAULT_HOLIDAY_ALERT,
                }
            )

    merged = {}
    for item in generated:
        key = f"date:{item['date']}" if item.get('date') else f"month_day:{item.get('month_day', '')}"
        if key in {'date:', 'month_day:'}:
            continue
        merged[key] = item

    for item in holidays:
        key = f"date:{item['date']}" if item.get('date') else f"month_day:{item.get('month_day', '')}"
        if key in {'date:', 'month_day:'}:
            continue
        # Les entrées personnalisées de l’admin ont priorité.
        merged[key] = item

    def sort_key(item):
        if item.get('date'):
            return (0, item['date'])
        return (1, item.get('month_day', '99-99'))

    return sorted(merged.values(), key=sort_key)


def _normalize_special_dates(raw_special_dates):
    if not isinstance(raw_special_dates, list):
        return []

    normalized = []
    for item in raw_special_dates:
        if not isinstance(item, dict):
            continue

        date_text = str(item.get('date', '')).strip()
        if not _is_valid_iso_date_text(date_text):
            continue

        closed = bool(item.get('closed', False))
        start = str(item.get('start', '09:00')).strip()
        end = str(item.get('end', '17:00')).strip()
        reason = str(item.get('reason', '')).strip()

        if closed:
            start = '00:00'
            end = '00:00'
        else:
            start_minutes = _time_text_to_minutes(start)
            end_minutes = _time_text_to_minutes(end)
            if start_minutes is None or end_minutes is None or end_minutes <= start_minutes:
                continue

        normalized.append(
            {
                'date': date_text,
                'closed': closed,
                'start': start,
                'end': end,
                'reason': reason,
            }
        )

    by_date = {}
    for item in normalized:
        by_date[item['date']] = item

    return [by_date[date_key] for date_key in sorted(by_date.keys())]


def _load_opening_hours_payload():
    if not OPENING_HOURS_PATH.exists():
        return {
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'opening_hours': _default_opening_hours(),
            'holidays': [],
            'special_dates': [],
        }

    try:
        payload = json.loads(OPENING_HOURS_PATH.read_text(encoding='utf-8'))
        raw_hours = payload.get('opening_hours', payload)
        return {
            'updated_at': payload.get('updated_at', datetime.now(timezone.utc).isoformat()),
            'opening_hours': _normalize_opening_hours(raw_hours),
            'holidays': _normalize_holidays(payload.get('holidays', [])),
            'special_dates': _normalize_special_dates(payload.get('special_dates', [])),
        }
    except (json.JSONDecodeError, OSError, ValueError):
        return {
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'opening_hours': _default_opening_hours(),
            'holidays': [],
            'special_dates': [],
        }


def _load_opening_hours():
    return _load_opening_hours_payload()['opening_hours']


def _load_holidays():
    stored_holidays = _load_opening_hours_payload()['holidays']
    return _merge_with_quebec_holidays(stored_holidays)


def _load_special_dates():
    return _load_opening_hours_payload()['special_dates']


def _save_opening_hours_payload(opening_hours=None, holidays=None, special_dates=None):
    DATA_DIR.mkdir(exist_ok=True)
    current_payload = _load_opening_hours_payload()
    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'opening_hours': _normalize_opening_hours(
            opening_hours if opening_hours is not None else current_payload.get('opening_hours', {})
        ),
        'holidays': _normalize_holidays(
            holidays if holidays is not None else current_payload.get('holidays', [])
        ),
        'special_dates': _normalize_special_dates(
            special_dates if special_dates is not None else current_payload.get('special_dates', [])
        ),
    }
    OPENING_HOURS_PATH.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _save_opening_hours(opening_hours):
    _save_opening_hours_payload(opening_hours=opening_hours)


def _save_special_dates(special_dates):
    _save_opening_hours_payload(special_dates=special_dates)


def _default_reservation_config():
    return {
        'max_simultaneous_bookings': 3,
        'min_duration_minutes': 30,
        'max_duration_minutes': 120,
        'latest_start_before_close_minutes': 30,
        'slot_interval_enabled': True,
        'slot_interval_minutes': 30,
        'allow_back_to_back': True,
        'fixed_time_only': True,
        'fixed_time_interval_minutes': 15,
        'allow_companion_booking': True,
        'allow_private_room_choice': False,
        'single_booking_per_day': False,
        'frequency_limit_enabled': False,
        'frequency_limit_metric': 'bookings',
        'frequency_limit_value': 3,
        'frequency_limit_period_value': 1,
        'frequency_limit_period_unit': 'weeks',
    }


def _normalize_reservation_config(raw_config):
    config = _default_reservation_config()
    if not isinstance(raw_config, dict):
        return config

    try:
        max_simultaneous = int(raw_config.get('max_simultaneous_bookings', config['max_simultaneous_bookings']))
        min_duration = int(raw_config.get('min_duration_minutes', config['min_duration_minutes']))
        max_duration = int(raw_config.get('max_duration_minutes', config['max_duration_minutes']))
        latest_start_before_close = int(raw_config.get('latest_start_before_close_minutes', config['latest_start_before_close_minutes']))
        slot_interval_minutes = int(raw_config.get('slot_interval_minutes', config['slot_interval_minutes']))
        fixed_time_interval = int(raw_config.get('fixed_time_interval_minutes', config['fixed_time_interval_minutes']))
        frequency_limit_value = int(raw_config.get('frequency_limit_value', config['frequency_limit_value']))
        frequency_limit_period_value = int(raw_config.get('frequency_limit_period_value', config['frequency_limit_period_value']))
    except (TypeError, ValueError):
        return config

    if max_simultaneous < 1:
        max_simultaneous = config['max_simultaneous_bookings']
    if min_duration < 1:
        min_duration = config['min_duration_minutes']
    if max_duration < min_duration:
        max_duration = max(min_duration, config['max_duration_minutes'])
    if latest_start_before_close < 0:
        latest_start_before_close = config['latest_start_before_close_minutes']
    if slot_interval_minutes not in VALID_SLOT_INTERVALS:
        slot_interval_minutes = config['slot_interval_minutes']
    if fixed_time_interval not in VALID_SLOT_INTERVALS:
        fixed_time_interval = config['fixed_time_interval_minutes']
    if frequency_limit_value < 1:
        frequency_limit_value = config['frequency_limit_value']
    if frequency_limit_period_value < 1:
        frequency_limit_period_value = config['frequency_limit_period_value']

    frequency_limit_metric = str(raw_config.get('frequency_limit_metric', config['frequency_limit_metric'])).strip().lower()
    if frequency_limit_metric not in {'bookings', 'hours'}:
        frequency_limit_metric = config['frequency_limit_metric']

    frequency_limit_period_unit = str(raw_config.get('frequency_limit_period_unit', config['frequency_limit_period_unit'])).strip().lower()
    if frequency_limit_period_unit not in {'days', 'weeks', 'months'}:
        frequency_limit_period_unit = config['frequency_limit_period_unit']
    allow_private_room_choice = bool(
        raw_config.get(
            'allow_private_room_choice',
            raw_config.get('allow_solo_booking', config['allow_private_room_choice']),
        )
    )
    allow_companion_booking = bool(
        raw_config.get(
            'allow_companion_booking',
            raw_config.get('allow_companion', config['allow_companion_booking']),
        )
    )

    config.update(
        {
            'max_simultaneous_bookings': max_simultaneous,
            'min_duration_minutes': min_duration,
            'max_duration_minutes': max_duration,
            'latest_start_before_close_minutes': latest_start_before_close,
            'slot_interval_enabled': bool(raw_config.get('slot_interval_enabled', config['slot_interval_enabled'])),
            'slot_interval_minutes': slot_interval_minutes,
            'allow_back_to_back': bool(raw_config.get('allow_back_to_back', config['allow_back_to_back'])),
            'fixed_time_only': bool(raw_config.get('fixed_time_only', config['fixed_time_only'])),
            'fixed_time_interval_minutes': fixed_time_interval,
            'allow_companion_booking': allow_companion_booking,
            'allow_private_room_choice': allow_private_room_choice,
            'single_booking_per_day': bool(raw_config.get('single_booking_per_day', config['single_booking_per_day'])),
            'frequency_limit_enabled': bool(raw_config.get('frequency_limit_enabled', config['frequency_limit_enabled'])),
            'frequency_limit_metric': frequency_limit_metric,
            'frequency_limit_value': frequency_limit_value,
            'frequency_limit_period_value': frequency_limit_period_value,
            'frequency_limit_period_unit': frequency_limit_period_unit,
        }
    )
    return config


def _default_invitation_config():
    return {
        'custom_code_enabled': False,
        'custom_code': '',
        'one_time_validity_days': 15,
    }


def _normalize_invitation_config(raw_config):
    config = _default_invitation_config()
    if not isinstance(raw_config, dict):
        return config

    custom_code_raw = str(raw_config.get('custom_code', '')).strip()
    custom_code = custom_code_raw[:32]
    try:
        one_time_validity_days = int(raw_config.get('one_time_validity_days', config['one_time_validity_days']))
    except (TypeError, ValueError):
        one_time_validity_days = config['one_time_validity_days']

    if one_time_validity_days < 1:
        one_time_validity_days = config['one_time_validity_days']
    if one_time_validity_days > 365:
        one_time_validity_days = 365

    config.update(
        {
            'custom_code_enabled': bool(raw_config.get('custom_code_enabled', False)),
            'custom_code': custom_code,
            'one_time_validity_days': one_time_validity_days,
        }
    )
    return config


def _load_invitation_config():
    if not INVITATION_CONFIG_PATH.exists():
        return _default_invitation_config()

    try:
        payload = json.loads(INVITATION_CONFIG_PATH.read_text(encoding='utf-8'))
        raw_config = payload.get('invitation_config', payload)
        return _normalize_invitation_config(raw_config)
    except (json.JSONDecodeError, OSError, ValueError):
        return _default_invitation_config()


def _save_invitation_config(invitation_config):
    DATA_DIR.mkdir(exist_ok=True)
    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'invitation_config': _normalize_invitation_config(invitation_config),
    }
    INVITATION_CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _generate_one_time_invitation_code(conn, validity_days):
    now = datetime.now()
    expires_at = now + timedelta(days=validity_days)
    expires_text = expires_at.isoformat(timespec='minutes')

    for _ in range(20):
        code = f"{secrets.randbelow(1000000):06d}"
        try:
            conn.execute(
                '''
                INSERT INTO invitation_codes (code, expires_at)
                VALUES (?, ?)
                ''',
                (code, expires_text),
            )
            return code, expires_text
        except sqlite3.IntegrityError:
            continue

    raise RuntimeError("Impossible de générer un code d'invitation unique.")


def _load_invitation_codes_for_admin(limit=30):
    conn = _get_db_connection()
    try:
        rows = conn.execute(
            '''
            SELECT id, code, expires_at, used_at, created_at
            FROM invitation_codes
            ORDER BY created_at DESC
            LIMIT ?
            ''',
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    now = datetime.now()
    result = []
    for row in rows:
        expires_dt = _parse_stored_datetime(row['expires_at'])
        used_dt = _parse_stored_datetime(row['used_at'])
        is_expired = bool(expires_dt and expires_dt < now and not used_dt)
        status = 'Actif'
        if used_dt:
            status = 'Utilisé'
        elif is_expired:
            status = 'Expiré'

        result.append(
            {
                'id': row['id'],
                'code': row['code'],
                'expires_at': row['expires_at'],
                'used_at': row['used_at'] or '',
                'created_at': row['created_at'] or '',
                'status': status,
            }
        )

    return result


def _validate_invitation_for_registration(conn, submitted_code):
    code = str(submitted_code or '').strip()
    if not code:
        return False, "Le code d'invitation est requis.", None

    invitation_config = _load_invitation_config()
    if invitation_config['custom_code_enabled']:
        configured_code = invitation_config['custom_code'].strip()
        if not configured_code:
            return False, "Code personnalisé actif mais non configuré. Contactez l'administrateur.", None
        if code != configured_code:
            return False, "Code d'invitation invalide.", None
        return True, "", None

    now_text = datetime.now().isoformat(timespec='minutes')
    row = conn.execute(
        '''
        SELECT id
        FROM invitation_codes
        WHERE code = ? AND used_at IS NULL AND expires_at >= ?
        LIMIT 1
        ''',
        (code, now_text),
    ).fetchone()
    if not row:
        return False, "Code d'invitation invalide ou expiré.", None

    return True, "", int(row['id'])


def _load_reservation_config():
    if not RESERVATION_CONFIG_PATH.exists():
        return _default_reservation_config()

    try:
        payload = json.loads(RESERVATION_CONFIG_PATH.read_text(encoding='utf-8'))
        raw_config = payload.get('reservation_config', payload)
        return _normalize_reservation_config(raw_config)
    except (json.JSONDecodeError, OSError, ValueError):
        return _default_reservation_config()


def _save_reservation_config(reservation_config):
    DATA_DIR.mkdir(exist_ok=True)
    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'reservation_config': _normalize_reservation_config(reservation_config),
    }
    RESERVATION_CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _opening_hours_for_calendar(opening_hours):
    calendar_hours = {}

    for day_key, _, js_day_index in DAY_CONFIG:
        day_data = opening_hours.get(day_key, {'closed': True, 'start': '09:00', 'end': '09:00'})
        if day_data['closed']:
            calendar_hours[str(js_day_index)] = []
            continue

        calendar_hours[str(js_day_index)] = [
            {
                'start': day_data['start'],
                'end': day_data['end'],
            }
        ]

    return calendar_hours


def _python_weekday_to_day_key(python_weekday):
    mapping = {
        0: 'monday',
        1: 'tuesday',
        2: 'wednesday',
        3: 'thursday',
        4: 'friday',
        5: 'saturday',
        6: 'sunday',
    }
    return mapping.get(python_weekday, 'monday')


def _day_windows_minutes(day_key, opening_hours):
    day_data = opening_hours.get(day_key, {})
    if day_data.get('closed', True):
        return []

    start_minutes = _time_text_to_minutes(str(day_data.get('start', '')))
    end_minutes = _time_text_to_minutes(str(day_data.get('end', '')))
    if start_minutes is None or end_minutes is None or end_minutes <= start_minutes:
        return []

    return [(start_minutes, end_minutes)]


def _special_date_for_date(date_obj, special_dates=None):
    if special_dates is None:
        special_dates = _load_special_dates()

    date_key = date_obj.strftime('%Y-%m-%d')
    for item in special_dates:
        if not isinstance(item, dict):
            continue
        if item.get('date') == date_key:
            return item
    return None


def _windows_for_date_minutes(date_obj, opening_hours=None, special_dates=None):
    if opening_hours is None:
        opening_hours = _load_opening_hours()
    if special_dates is None:
        special_dates = _load_special_dates()

    special_day = _special_date_for_date(date_obj, special_dates)
    if special_day:
        if special_day.get('closed', False):
            return []

        start_minutes = _time_text_to_minutes(str(special_day.get('start', '')))
        end_minutes = _time_text_to_minutes(str(special_day.get('end', '')))
        if start_minutes is None or end_minutes is None or end_minutes <= start_minutes:
            return []

        return [(start_minutes, end_minutes)]

    day_key = _python_weekday_to_day_key(date_obj.weekday())
    return _day_windows_minutes(day_key, opening_hours)


def _date_and_time_to_storage(date_text, time_text):
    dt = datetime.strptime(f'{date_text} {time_text}', '%Y-%m-%d %H:%M')
    return dt.isoformat(timespec='minutes')


def _parse_stored_datetime(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _add_months(date_value, months):
    month_index = (date_value.month - 1) + months
    year = date_value.year + (month_index // 12)
    month = (month_index % 12) + 1
    last_day = pycalendar.monthrange(year, month)[1]
    day = min(date_value.day, last_day)
    return date_value.replace(year=year, month=month, day=day)


def _frequency_window_start(reference_dt, period_unit, period_value):
    safe_value = max(int(period_value or 1), 1)
    if period_unit == 'days':
        return reference_dt - timedelta(days=safe_value)
    if period_unit == 'weeks':
        return reference_dt - timedelta(weeks=safe_value)
    return _add_months(reference_dt, -safe_value)


def _is_valid_iso_date_text(value):
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        return False
    try:
        datetime.strptime(text, '%Y-%m-%d')
    except ValueError:
        return False
    return True


def _is_valid_month_day_text(value):
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not re.fullmatch(r'\d{2}-\d{2}', text):
        return False
    try:
        datetime.strptime(f'2000-{text}', '%Y-%m-%d')
    except ValueError:
        return False
    return True


def _holiday_for_date(date_obj, holidays=None):
    if holidays is None:
        holidays = _load_holidays()
    date_key = date_obj.strftime('%Y-%m-%d')
    month_day = date_obj.strftime('%m-%d')
    for item in holidays:
        if not isinstance(item, dict):
            continue
        if item.get('date') == date_key or item.get('month_day') == month_day:
            return item
    return None


def _blocked_slot_applies_to_date(slot, date_obj, holiday_match=False):
    repeat_type = slot.get('repeat_type')
    date_key = date_obj.strftime('%Y-%m-%d')

    range_start = slot.get('range_start') or ''
    range_end = slot.get('range_end') or ''
    if range_start and date_key < range_start:
        return False
    if range_end and date_key > range_end:
        return False

    if repeat_type == 'once':
        return date_key == (slot.get('date_value') or '')
    if repeat_type == 'weekly':
        return date_obj.weekday() == int(slot.get('weekday', -1))
    if repeat_type == 'yearly':
        return date_obj.strftime('%m-%d') == (slot.get('month_day') or '')
    if repeat_type == 'holiday':
        return bool(holiday_match)
    return False


def _normalize_blocked_slot_row(row):
    start_time = str(row['start_time'] or '').strip()
    end_time = str(row['end_time'] or '').strip()
    start_minutes = _time_text_to_minutes(start_time)
    end_minutes = _time_text_to_minutes(end_time)
    if start_minutes is None or end_minutes is None or end_minutes <= start_minutes:
        return None

    repeat_type = str(row['repeat_type'] or 'once').strip()
    if repeat_type not in {'once', 'weekly', 'yearly', 'holiday'}:
        repeat_type = 'once'

    date_value = str(row['date_value'] or '').strip()
    month_day = str(row['month_day'] or '').strip()
    weekday = row['weekday']

    if repeat_type == 'once':
        if not _is_valid_iso_date_text(date_value):
            return None
    if repeat_type == 'weekly':
        try:
            weekday = int(weekday)
        except (TypeError, ValueError):
            return None
        if weekday < 0 or weekday > 6:
            return None
    if repeat_type == 'yearly':
        if not _is_valid_month_day_text(month_day):
            return None

    range_start = str(row['range_start'] or '').strip()
    range_end = str(row['range_end'] or '').strip()
    if range_start and not _is_valid_iso_date_text(range_start):
        range_start = ''
    if range_end and not _is_valid_iso_date_text(range_end):
        range_end = ''
    if range_start and range_end and range_end < range_start:
        range_start = ''
        range_end = ''

    title = str(row['title'] or '').strip()
    if not title:
        title = 'Blocage administrateur'

    description = BLOCKED_SLOT_REPEAT_LABELS.get(repeat_type, 'Répétition inconnue')
    if repeat_type == 'once':
        description = f"Une seule fois ({date_value})"
    elif repeat_type == 'weekly':
        weekday_labels = {
            0: 'Lundi',
            1: 'Mardi',
            2: 'Mercredi',
            3: 'Jeudi',
            4: 'Vendredi',
            5: 'Samedi',
            6: 'Dimanche',
        }
        description = f"Chaque semaine ({weekday_labels.get(weekday, 'Jour inconnu')})"
    elif repeat_type == 'yearly':
        description = f"Chaque année ({month_day})"

    return {
        'id': int(row['id']),
        'title': title,
        'repeat_type': repeat_type,
        'repeat_label': BLOCKED_SLOT_REPEAT_LABELS.get(repeat_type, repeat_type),
        'repeat_description': description,
        'date_value': date_value if _is_valid_iso_date_text(date_value) else '',
        'weekday': weekday if isinstance(weekday, int) else None,
        'month_day': month_day if _is_valid_month_day_text(month_day) else '',
        'start_time': start_time,
        'end_time': end_time,
        'start_minutes': start_minutes,
        'end_minutes': end_minutes,
        'range_start': range_start,
        'range_end': range_end,
        'created_at': str(row['created_at'] or '').strip(),
    }


def _load_blocked_slot_rules():
    conn = _get_db_connection()
    try:
        rows = conn.execute(
            '''
            SELECT
                id,
                title,
                repeat_type,
                date_value,
                weekday,
                month_day,
                start_time,
                end_time,
                range_start,
                range_end,
                created_at
            FROM blocked_slots
            ORDER BY created_at DESC, id DESC
            '''
        ).fetchall()
    finally:
        conn.close()

    rules = []
    for row in rows:
        normalized = _normalize_blocked_slot_row(row)
        if normalized:
            rules.append(normalized)
    return rules


def _load_blocked_slots_for_admin(limit=200):
    rows = _load_blocked_slot_rules()
    now_local = datetime.now()
    today_key = now_local.strftime('%Y-%m-%d')

    active_rows = []
    for row in rows:
        range_end = row.get('range_end') or ''
        if range_end and range_end < today_key:
            continue

        if row.get('repeat_type') == 'once':
            date_value = row.get('date_value') or ''
            if date_value and date_value < today_key:
                continue

        active_rows.append(row)

    return active_rows[:limit]


def _load_blocked_intervals_for_date(date_obj):
    rules = _load_blocked_slot_rules()
    holiday_match = _holiday_for_date(date_obj) is not None
    intervals = []

    for rule in rules:
        if not _blocked_slot_applies_to_date(rule, date_obj, holiday_match=holiday_match):
            continue
        intervals.append(
            {
                'id': rule['id'],
                'title': rule['title'],
                'start_minutes': rule['start_minutes'],
                'end_minutes': rule['end_minutes'],
                'start_time': rule['start_time'],
                'end_time': rule['end_time'],
            }
        )

    return intervals


def _load_bookings_for_calendar():
    bookings_by_date = {}

    conn = _get_db_connection()
    try:
        rows = conn.execute(
            '''
            SELECT id, start, end, companion_count, is_private
            FROM bookings
            ORDER BY start ASC
            '''
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        start_dt = _parse_stored_datetime(row['start'])
        end_dt = _parse_stored_datetime(row['end'])

        if not start_dt or not end_dt or end_dt <= start_dt:
            continue

        date_key = start_dt.strftime('%Y-%m-%d')
        companion_count = max(int(row['companion_count'] or 0), 0)
        bookings_by_date.setdefault(date_key, []).append(
            {
                'booking_id': int(row['id']),
                'start': start_dt.strftime('%H:%M'),
                'end': end_dt.strftime('%H:%M'),
                'people_count': companion_count + 1,
                'is_private': bool(row['is_private']),
            }
        )

    return bookings_by_date


def _load_bookings_for_admin(limit=200):
    conn = _get_db_connection()
    try:
        rows = conn.execute(
            '''
            SELECT
                b.id,
                b.user_id,
                b.start,
                b.end,
                b.title,
                b.allow_companion,
                b.companion_count,
                b.is_private,
                b.created_at,
                u.full_name,
                u.email,
                u.phone
            FROM bookings b
            JOIN users u ON u.id = b.user_id
            ORDER BY b.start ASC
            LIMIT ?
            ''',
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    now_local = datetime.now()
    today_key = now_local.strftime('%Y-%m-%d')
    bookings = []
    for row in rows:
        start_dt = _parse_stored_datetime(row['start'])
        end_dt = _parse_stored_datetime(row['end'])
        is_past_today = False
        if start_dt and end_dt:
            comparison_now = datetime.now(end_dt.tzinfo) if end_dt.tzinfo else now_local
            is_past_today = start_dt.strftime('%Y-%m-%d') == today_key and end_dt < comparison_now
        bookings.append(
            {
                'id': row['id'],
                'user_id': row['user_id'],
                'start_display': start_dt.strftime('%Y-%m-%d %H:%M') if start_dt else str(row['start']),
                'end_display': end_dt.strftime('%Y-%m-%d %H:%M') if end_dt else str(row['end']),
                'date_key': start_dt.strftime('%Y-%m-%d') if start_dt else '',
                'date_title': f"{start_dt.day} {FRENCH_MONTHS.get(start_dt.month, '')}" if start_dt else '',
                'start_time': start_dt.strftime('%H:%M') if start_dt else '',
                'end_time': end_dt.strftime('%H:%M') if end_dt else '',
                'title': row['title'] or '',
                'allow_companion': bool(row['allow_companion']),
                'companion_count': int(row['companion_count'] or 0),
                'people_count': int(row['companion_count'] or 0) + 1,
                'is_private': bool(row['is_private']),
                'user_name': row['full_name'] or '',
                'user_email': row['email'] or '',
                'user_phone': row['phone'] or '',
                'created_at': row['created_at'] or '',
                'is_past_today': is_past_today,
            }
        )

    return bookings


def _group_bookings_by_date(bookings):
    grouped = []
    current_date_key = None
    current_day_key = datetime.now().strftime('%Y-%m-%d')

    for booking in bookings:
        date_key = booking.get('date_key', '')
        if date_key != current_date_key:
            grouped.append(
                {
                    'date_key': date_key,
                    'date_title': booking.get('date_title', date_key),
                    'items': [],
                    'upcoming_items': [],
                    'past_today_items': [],
                }
            )
            current_date_key = date_key

        grouped[-1]['items'].append(booking)
        if date_key == current_day_key and booking.get('is_past_today'):
            grouped[-1]['past_today_items'].append(booking)
        else:
            grouped[-1]['upcoming_items'].append(booking)

    return grouped


def _load_users_for_admin(limit=300):
    conn = _get_db_connection()
    try:
        user_rows = conn.execute(
            '''
            SELECT
                u.id,
                u.full_name,
                u.email,
                u.phone,
                u.created_at,
                u.is_blocked,
                u.reservation_limit,
                u.must_change_password
            FROM users u
            ORDER BY u.created_at DESC
            LIMIT ?
            ''',
            (limit,),
        ).fetchall()

        booking_rows = conn.execute(
            '''
            SELECT
                b.user_id,
                b.start,
                b.end,
                b.title
            FROM bookings b
            ORDER BY b.start DESC
            '''
        ).fetchall()
    finally:
        conn.close()

    user_ids = {row['id'] for row in user_rows}
    now_utc = datetime.now(timezone.utc)

    booking_count_by_user = {}
    last_booking_by_user = {}
    next_booking_by_user = {}
    recent_by_user = {}
    for row in booking_rows:
        user_id = row['user_id']
        if user_id not in user_ids:
            continue

        start_dt = _parse_stored_datetime(row['start'])
        end_dt = _parse_stored_datetime(row['end'])
        if not start_dt or not end_dt:
            continue

        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        booking_count_by_user[user_id] = booking_count_by_user.get(user_id, 0) + 1

        current_last = last_booking_by_user.get(user_id)
        if current_last is None or start_dt > current_last:
            last_booking_by_user[user_id] = start_dt

        if start_dt >= now_utc:
            current_next = next_booking_by_user.get(user_id)
            if current_next is None or start_dt < current_next:
                next_booking_by_user[user_id] = start_dt

        recent_by_user.setdefault(user_id, [])
        if len(recent_by_user[user_id]) >= 5:
            continue

        recent_by_user[user_id].append(
            {
                'start_display': start_dt.strftime('%Y-%m-%d %H:%M') if start_dt else str(row['start']),
                'end_display': end_dt.strftime('%Y-%m-%d %H:%M') if end_dt else str(row['end']),
                'title': row['title'] or '',
            }
        )

    users = []
    for row in user_rows:
        first_name, last_name = _split_full_name(row['full_name'])
        last_booking_dt = last_booking_by_user.get(row['id'])
        next_booking_dt = next_booking_by_user.get(row['id'])
        if not first_name and row['email']:
            first_name = str(row['email']).split('@', 1)[0]

        users.append(
            {
                'id': row['id'],
                'full_name': row['full_name'] or '',
                'first_name': first_name,
                'last_name': last_name,
                'email': row['email'] or '',
                'phone': row['phone'] or '',
                'created_at': row['created_at'] or '',
                'is_blocked': bool(row['is_blocked']),
                'reservation_limit': row['reservation_limit'],
                'must_change_password': bool(row['must_change_password']),
                'booking_count': int(booking_count_by_user.get(row['id'], 0)),
                'last_booking_start': last_booking_dt.strftime('%Y-%m-%d %H:%M') if last_booking_dt else '',
                'next_booking_start': next_booking_dt.strftime('%Y-%m-%d %H:%M') if next_booking_dt else '',
                'recent_bookings': recent_by_user.get(row['id'], []),
            }
        )

    return users


def _load_existing_bookings_for_date(date_text):
    day_start = f'{date_text}T00:00'
    next_day = (datetime.strptime(date_text, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    day_end = f'{next_day}T00:00'

    conn = _get_db_connection()
    try:
        rows = conn.execute(
            '''
            SELECT id, user_id, start, end, companion_count, is_private
            FROM bookings
            WHERE start >= ? AND start < ?
            ORDER BY start ASC
            ''',
            (day_start, day_end),
        ).fetchall()
    finally:
        conn.close()

    bookings = []
    for row in rows:
        start_dt = _parse_stored_datetime(row['start'])
        end_dt = _parse_stored_datetime(row['end'])
        if not start_dt or not end_dt or end_dt <= start_dt:
            continue

        start_minutes = (start_dt.hour * 60) + start_dt.minute
        end_minutes = (end_dt.hour * 60) + end_dt.minute
        bookings.append(
            {
                'id': row['id'],
                'user_id': row['user_id'],
                'start_minutes': start_minutes,
                'end_minutes': end_minutes,
                'companion_count': max(int(row['companion_count'] or 0), 0),
                'people_count': max(int(row['companion_count'] or 0), 0) + 1,
                'is_private': bool(row['is_private']),
            }
        )

    return bookings


def _validate_booking_request(
    user_id,
    date_text,
    start_text,
    end_text,
    companion_count=0,
    is_private=False,
    exclude_booking_id=None,
):
    try:
        date_obj = datetime.strptime(date_text, '%Y-%m-%d').date()
    except ValueError:
        return False, "Date invalide.", None

    start_minutes = _time_text_to_minutes(start_text)
    end_minutes = _time_text_to_minutes(end_text)
    if start_minutes is None or end_minutes is None:
        return False, "Heure de début ou de fin invalide.", None
    if end_minutes <= start_minutes:
        return False, "L'heure de fin doit être après l'heure de début.", None

    opening_hours = _load_opening_hours()
    holidays = _load_holidays()
    special_dates = _load_special_dates()
    reservation_config = _load_reservation_config()
    windows = _windows_for_date_minutes(date_obj, opening_hours, special_dates)
    if not windows:
        return False, "La salle est fermée cette journée.", None

    selected_window = None
    for window_start, window_end in windows:
        if start_minutes >= window_start and end_minutes <= window_end:
            selected_window = (window_start, window_end)
            break

    if selected_window is None:
        return False, "Réservation en dehors des heures d'ouverture.", None

    duration = end_minutes - start_minutes
    if duration < reservation_config['min_duration_minutes']:
        return False, "Durée inférieure au minimum autorisé.", None
    if duration > reservation_config['max_duration_minutes']:
        return False, "Durée supérieure au maximum autorisé.", None

    if companion_count < 0:
        return False, "Le nombre d'accompagnateurs ne peut pas être négatif.", None
    if companion_count > 0 and not reservation_config.get('allow_companion_booking', True):
        return False, "Les accompagnateurs sont désactivés. Chaque place doit être réservée par un compte utilisateur.", None

    if is_private and not reservation_config.get('allow_private_room_choice', False):
        return False, "L'option de réservation privée n'est pas activée.", None

    capacity_limit = reservation_config['max_simultaneous_bookings']
    people_count = companion_count + 1
    if people_count > capacity_limit:
        return False, "Le nombre total de personnes dépasse la capacité maximale.", None

    if reservation_config['slot_interval_enabled']:
        slot_interval = reservation_config['slot_interval_minutes']
        if duration % slot_interval != 0:
            return False, f"La durée doit respecter un multiple de {slot_interval} minutes.", None

    if reservation_config['fixed_time_only']:
        fixed_interval = reservation_config['fixed_time_interval_minutes']
        if (start_minutes % fixed_interval) != 0 or (end_minutes % fixed_interval) != 0:
            return False, f"Heures fixes requises par tranches de {fixed_interval} minutes.", None

    latest_before_close = reservation_config['latest_start_before_close_minutes']
    window_end = selected_window[1]
    if start_minutes > (window_end - latest_before_close):
        return False, "Cette heure de début est trop proche de la fermeture.", None

    conn = _get_db_connection()
    try:
        user_row = conn.execute(
            '''
            SELECT id, is_blocked, reservation_limit
            FROM users
            WHERE id = ?
            ''',
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if not user_row:
        return False, "Utilisateur introuvable.", None
    if bool(user_row['is_blocked']):
        return False, "Votre compte est bloqué.", None

    reservation_limit = user_row['reservation_limit']
    if reservation_limit is not None:
        now_text = datetime.now().isoformat(timespec='minutes')
        conn = _get_db_connection()
        try:
            if exclude_booking_id:
                row = conn.execute(
                    '''
                    SELECT COUNT(*) AS total
                    FROM bookings
                    WHERE user_id = ? AND end >= ? AND id != ?
                    ''',
                    (user_id, now_text, int(exclude_booking_id)),
                ).fetchone()
            else:
                row = conn.execute(
                    '''
                    SELECT COUNT(*) AS total
                    FROM bookings
                    WHERE user_id = ? AND end >= ?
                    ''',
                    (user_id, now_text),
                ).fetchone()
        finally:
            conn.close()
        if row and int(row['total'] or 0) >= int(reservation_limit):
            return False, "Vous avez atteint votre limite de réservations autorisées.", None

    requested_start_dt = datetime.combine(date_obj, datetime.min.time()) + timedelta(minutes=start_minutes)
    requested_end_dt = datetime.combine(date_obj, datetime.min.time()) + timedelta(minutes=end_minutes)

    if reservation_config.get('single_booking_per_day', False):
        day_start_text = datetime.combine(date_obj, datetime.min.time()).isoformat(timespec='minutes')
        next_day_text = (datetime.combine(date_obj, datetime.min.time()) + timedelta(days=1)).isoformat(timespec='minutes')
        conn = _get_db_connection()
        try:
            if exclude_booking_id:
                row = conn.execute(
                    '''
                    SELECT COUNT(*) AS total
                    FROM bookings
                    WHERE user_id = ? AND start >= ? AND start < ? AND id != ?
                    ''',
                    (user_id, day_start_text, next_day_text, int(exclude_booking_id)),
                ).fetchone()
            else:
                row = conn.execute(
                    '''
                    SELECT COUNT(*) AS total
                    FROM bookings
                    WHERE user_id = ? AND start >= ? AND start < ?
                    ''',
                    (user_id, day_start_text, next_day_text),
                ).fetchone()
        finally:
            conn.close()
        if row and int(row['total'] or 0) >= 1:
            return False, "Limite atteinte: une seule réservation par jour est autorisée.", None

    if reservation_config.get('frequency_limit_enabled', False):
        metric = str(reservation_config.get('frequency_limit_metric', 'bookings'))
        limit_value = max(int(reservation_config.get('frequency_limit_value') or 1), 1)
        period_value = max(int(reservation_config.get('frequency_limit_period_value') or 1), 1)
        period_unit = str(reservation_config.get('frequency_limit_period_unit', 'weeks'))
        if period_unit not in {'days', 'weeks', 'months'}:
            period_unit = 'weeks'
        if metric not in {'bookings', 'hours'}:
            metric = 'bookings'

        window_start_dt = _frequency_window_start(requested_start_dt, period_unit, period_value)
        window_start_text = window_start_dt.isoformat(timespec='minutes')
        window_end_text = requested_start_dt.isoformat(timespec='minutes')
        conn = _get_db_connection()
        try:
            if exclude_booking_id:
                rows = conn.execute(
                    '''
                    SELECT start, end
                    FROM bookings
                    WHERE user_id = ? AND start >= ? AND start < ? AND id != ?
                    ''',
                    (user_id, window_start_text, window_end_text, int(exclude_booking_id)),
                ).fetchall()
            else:
                rows = conn.execute(
                    '''
                    SELECT start, end
                    FROM bookings
                    WHERE user_id = ? AND start >= ? AND start < ?
                    ''',
                    (user_id, window_start_text, window_end_text),
                ).fetchall()
        finally:
            conn.close()

        existing_count = 0
        existing_hours = 0.0
        for row in rows:
            start_dt = _parse_stored_datetime(row['start'])
            end_dt = _parse_stored_datetime(row['end'])
            if not start_dt or not end_dt or end_dt <= start_dt:
                continue
            existing_count += 1
            existing_hours += (end_dt - start_dt).total_seconds() / 3600.0

        requested_hours = (requested_end_dt - requested_start_dt).total_seconds() / 3600.0
        period_label = f"{period_value} {period_unit}"
        if metric == 'bookings':
            if (existing_count + 1) > limit_value:
                return False, f"Limite atteinte: maximum {limit_value} réservation(s) par {period_label}.", None
        else:
            if (existing_hours + requested_hours) > float(limit_value):
                return False, f"Limite atteinte: maximum {limit_value} heure(s) par {period_label}.", None

    existing = _load_existing_bookings_for_date(date_text)
    blocked_intervals = _load_blocked_intervals_for_date(date_obj)

    for blocked in blocked_intervals:
        overlap_start = max(start_minutes, blocked['start_minutes'])
        overlap_end = min(end_minutes, blocked['end_minutes'])
        if overlap_end > overlap_start:
            return False, f"Cette plage est bloquée par l'administrateur ({blocked['title']}).", None

    if not reservation_config['allow_back_to_back']:
        for booking in existing:
            if booking['end_minutes'] == start_minutes or booking['start_minutes'] == end_minutes:
                return False, "Les réservations subséquentes ne sont pas permises.", None

    overlapping_bookings = []
    for booking in existing:
        if exclude_booking_id and int(booking.get('id') or 0) == int(exclude_booking_id):
            continue
        overlap_start = max(start_minutes, booking['start_minutes'])
        overlap_end = min(end_minutes, booking['end_minutes'])
        if overlap_end > overlap_start:
            if int(booking.get('user_id') or 0) == int(user_id):
                return False, "Vous avez déjà une réservation qui chevauche cette plage horaire.", None
            overlapping_bookings.append(
                {
                    'overlap_start': overlap_start,
                    'overlap_end': overlap_end,
                    'people_count': booking.get('people_count', 1),
                    'is_private': booking.get('is_private', False),
                }
            )

    if is_private and overlapping_bookings:
        return False, "Réservation privée impossible: une autre réservation existe déjà sur cette plage.", None

    if not is_private:
        for booking in overlapping_bookings:
            if booking['is_private']:
                return False, "Cette plage contient une réservation privée qui interdit le partage.", None

    events = []
    for booking in overlapping_bookings:
        events.append((booking['overlap_start'], booking['people_count']))
        events.append((booking['overlap_end'], -booking['people_count']))

    events.append((start_minutes, people_count))
    events.append((end_minutes, -people_count))
    events.sort(key=lambda event: (event[0], event[1]))

    concurrent = 0
    for _, delta in events:
        concurrent += delta
        if concurrent > capacity_limit:
            return False, "Capacité maximale atteinte sur cette plage horaire.", None

    return True, "", reservation_config


def _load_bookings_for_user(user_id):
    conn = _get_db_connection()
    try:
        rows = conn.execute(
            '''
            SELECT id, start, end, title, companion_count, is_private, created_at
            FROM bookings
            WHERE user_id = ?
            ORDER BY start ASC
            ''',
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    now_local = datetime.now()
    bookings = []
    for row in rows:
        start_dt = _parse_stored_datetime(row['start'])
        end_dt = _parse_stored_datetime(row['end'])
        if not start_dt or not end_dt or end_dt <= start_dt:
            continue

        comparison_now = datetime.now(end_dt.tzinfo) if end_dt.tzinfo else now_local
        is_past = end_dt < comparison_now
        bookings.append(
            {
                'id': int(row['id']),
                'date_key': start_dt.strftime('%Y-%m-%d'),
                'date_label': start_dt.strftime('%Y-%m-%d'),
                'start_time': start_dt.strftime('%H:%M'),
                'end_time': end_dt.strftime('%H:%M'),
                'title': row['title'] or '',
                'companion_count': max(int(row['companion_count'] or 0), 0),
                'people_count': max(int(row['companion_count'] or 0), 0) + 1,
                'is_private': bool(row['is_private']),
                'created_at': row['created_at'] or '',
                'is_past': is_past,
            }
        )

    return bookings


def _get_admin_cipher():
    DATA_DIR.mkdir(exist_ok=True)

    if not ADMIN_KEY_PATH.exists():
        ADMIN_KEY_PATH.write_bytes(Fernet.generate_key())

    key = ADMIN_KEY_PATH.read_bytes().strip()
    return Fernet(key)


def _hash_password(password, salt=None):
    effective_salt = salt or os.urandom(16)
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        effective_salt,
        120000,
    )
    return {
        'salt': base64.b64encode(effective_salt).decode('utf-8'),
        'hash': base64.b64encode(password_hash).decode('utf-8'),
    }


def _verify_password(password, encoded_salt, encoded_hash):
    salt = base64.b64decode(encoded_salt.encode('utf-8'))
    expected_hash = base64.b64decode(encoded_hash.encode('utf-8'))
    computed_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        120000,
    )
    return hmac.compare_digest(computed_hash, expected_hash)


def _make_user_password_hash(password):
    password_data = _hash_password(password)
    return f"{password_data['salt']}${password_data['hash']}"


def _verify_user_password(password, stored_password_hash):
    if '$' not in stored_password_hash:
        return False

    encoded_salt, encoded_hash = stored_password_hash.split('$', 1)
    try:
        return _verify_password(password, encoded_salt, encoded_hash)
    except (ValueError, TypeError):
        return False


def _normalize_security_answer(value):
    text = str(value or '').strip().lower()
    if not text:
        return ''
    without_accents = ''.join(
        char for char in unicodedata.normalize('NFD', text)
        if unicodedata.category(char) != 'Mn'
    )
    # Garde uniquement les lettres/chiffres pour tolérer espaces et ponctuation.
    return re.sub(r'[^a-z0-9]', '', without_accents)


def _make_security_answer_hash(answer_text):
    normalized = _normalize_security_answer(answer_text)
    return _make_user_password_hash(normalized)


def _verify_security_answer(answer_text, stored_hash):
    normalized = _normalize_security_answer(answer_text)
    if not normalized:
        return False
    return _verify_user_password(normalized, stored_hash or '')


def _generate_temporary_password_code():
    return f"{secrets.randbelow(1000000):06d}"


def _split_full_name(full_name):
    text = (full_name or '').strip()
    if not text:
        return '', ''

    parts = text.split()
    first_name = parts[0]
    last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
    return first_name, last_name


def _load_admin_account():
    if not ADMIN_STORE_PATH.exists():
        return None

    try:
        encrypted_container = json.loads(ADMIN_STORE_PATH.read_text(encoding='utf-8'))
        encrypted_payload = encrypted_container.get('encrypted_payload', '')
        if not encrypted_payload:
            return None

        cipher = _get_admin_cipher()
        payload_json = cipher.decrypt(encrypted_payload.encode('utf-8')).decode('utf-8')
        return json.loads(payload_json)
    except (json.JSONDecodeError, InvalidToken, OSError, ValueError):
        return None


def _save_admin_account(identifier, password):
    password_data = _hash_password(password)
    payload = {
        'identifier': identifier.lower(),
        'password_salt': password_data['salt'],
        'password_hash': password_data['hash'],
        'created_at': datetime.now(timezone.utc).isoformat(),
    }

    cipher = _get_admin_cipher()
    encrypted_payload = cipher.encrypt(json.dumps(payload).encode('utf-8')).decode('utf-8')
    container = {
        'version': 1,
        'encrypted_payload': encrypted_payload,
    }
    ADMIN_STORE_PATH.write_text(json.dumps(container, indent=2), encoding='utf-8')


def _admin_account_exists():
    return _load_admin_account() is not None


def _any_user_account_exists():
    conn = _get_db_connection()
    try:
        row = conn.execute('SELECT 1 FROM users LIMIT 1').fetchone()
    finally:
        conn.close()
    return bool(row)


def _parse_session_activity_timestamp(raw_value):
    if isinstance(raw_value, (int, float)):
        return int(raw_value)
    if isinstance(raw_value, str) and raw_value.strip().isdigit():
        return int(raw_value.strip())
    return None


def _auth_status_context():
    is_admin_authenticated = bool(session.get('is_admin_authenticated'))
    is_user_authenticated = bool(session.get('user_id'))

    if is_admin_authenticated:
        return {
            'is_admin_authenticated': True,
            'is_user_authenticated': False,
            'connection_status_text': 'Connecté en administrateur',
            'connection_status_kind': 'admin',
            'connection_display_name': 'Administrateur',
        }
    if is_user_authenticated:
        display_name = ''
        user_id = session.get('user_id')
        conn = _get_db_connection()
        try:
            row = conn.execute(
                '''
                SELECT full_name, email, phone
                FROM users
                WHERE id = ?
                LIMIT 1
                ''',
                (user_id,),
            ).fetchone()
        finally:
            conn.close()

        if row:
            display_name = (row['full_name'] or '').strip()
            if not display_name:
                display_name = (row['email'] or '').strip()
            if not display_name:
                display_name = (row['phone'] or '').strip()
        if not display_name:
            display_name = 'Utilisateur'

        return {
            'is_admin_authenticated': False,
            'is_user_authenticated': True,
            'connection_status_text': 'Connecté en utilisateur',
            'connection_status_kind': 'user',
            'connection_display_name': display_name,
        }
    return {
        'is_admin_authenticated': False,
        'is_user_authenticated': False,
        'connection_status_text': 'Non connecté',
        'connection_status_kind': 'guest',
        'connection_display_name': '',
    }


@app.before_request
def _enforce_session_idle_timeout():
    if request.endpoint == 'static':
        return None

    is_admin_authenticated = bool(session.get('is_admin_authenticated'))
    is_user_authenticated = bool(session.get('user_id'))
    if not is_admin_authenticated and not is_user_authenticated:
        return None

    now_ts = int(datetime.now(timezone.utc).timestamp())
    last_activity_ts = _parse_session_activity_timestamp(session.get('last_activity_ts'))

    if last_activity_ts is not None and (now_ts - last_activity_ts) > SESSION_IDLE_TIMEOUT_SECONDS:
        session.clear()
        if request.path.startswith('/api/'):
            return jsonify({'ok': False, 'error': 'Session expirée après 1h d’inactivité. Reconnectez-vous.'}), 401
        return redirect(url_for('login'))

    session.permanent = True
    session['last_activity_ts'] = now_ts
    return None


@app.context_processor
def _inject_auth_status():
    return _auth_status_context()


_init_db()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/horaire')
@app.route('/horaires')
def horaire():
    opening_hours = _load_opening_hours()
    holidays = _load_holidays()
    special_dates = _load_special_dates()
    day_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    hours_by_day = []
    for day_key in day_order:
        day_data = opening_hours.get(day_key, {'closed': True, 'start': '09:00', 'end': '09:00'})
        if day_data.get('closed', True):
            hours_by_day.append('Fermé')
        else:
            hours_by_day.append(f"{day_data.get('start', '09:00')} - {day_data.get('end', '17:00')}")

    return render_template(
        'horaire.html',
        hours_by_day=hours_by_day,
        holidays_json=holidays,
        special_dates_json=special_dates,
    )


@app.route('/register', methods=['GET', 'POST'])
def register():
    errors = []
    created_user_id = None
    form_data = {
        'first_name': '',
        'last_name': '',
        'email': '',
        'phone': '',
        'invitation_code': '',
        'birth_date': '',
        'security_question_1': '',
        'security_question_2': '',
        'security_question_3': '',
    }

    if request.method == 'POST':
        form_data['first_name'] = request.form.get('first_name', '').strip()
        form_data['last_name'] = request.form.get('last_name', '').strip()
        form_data['email'] = request.form.get('email', '').strip()
        form_data['phone'] = request.form.get('phone', '').strip()
        form_data['invitation_code'] = request.form.get('invitation_code', '').strip()
        form_data['birth_date'] = request.form.get('birth_date', '').strip()
        form_data['security_question_1'] = request.form.get('security_question_1', '').strip()
        form_data['security_question_2'] = request.form.get('security_question_2', '').strip()
        form_data['security_question_3'] = request.form.get('security_question_3', '').strip()

        security_answer_1 = request.form.get('security_answer_1', '').strip()
        security_answer_2 = request.form.get('security_answer_2', '').strip()
        security_answer_3 = request.form.get('security_answer_3', '').strip()

        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')

        if not form_data['first_name']:
            errors.append("Le prénom est requis.")

        if not form_data['last_name']:
            errors.append("Le nom est requis.")

        if not form_data['email'] and not form_data['phone']:
            errors.append("Veuillez fournir au minimum une adresse courriel ou un numéro de téléphone.")

        if form_data['email'] and '@' not in form_data['email']:
            errors.append("L'adresse courriel semble invalide.")

        if form_data['phone']:
            phone_digits = re.sub(r'\D', '', form_data['phone'])
            if len(phone_digits) < 7:
                errors.append("Le numéro de téléphone semble invalide.")

        birth_date_obj = None
        if not form_data['birth_date']:
            errors.append("La date de naissance est requise.")
        else:
            try:
                birth_date_obj = datetime.strptime(form_data['birth_date'], '%Y-%m-%d').date()
                if birth_date_obj > datetime.now().date():
                    errors.append("La date de naissance ne peut pas être dans le futur.")
            except ValueError:
                errors.append("La date de naissance est invalide.")

        for question_index, question_text in enumerate(
            [form_data['security_question_1'], form_data['security_question_2'], form_data['security_question_3']],
            start=1,
        ):
            if not question_text:
                errors.append(f"La question de sécurité #{question_index} est requise.")
            elif len(question_text) < 5:
                errors.append(f"La question de sécurité #{question_index} est trop courte.")

        question_values = [form_data['security_question_1'], form_data['security_question_2'], form_data['security_question_3']]
        normalized_questions = [re.sub(r'\s+', ' ', value).strip().lower() for value in question_values if value]
        if len(normalized_questions) != len(set(normalized_questions)):
            errors.append("Les 3 questions de sécurité doivent être différentes.")

        for answer_index, answer_text in enumerate([security_answer_1, security_answer_2, security_answer_3], start=1):
            if not answer_text:
                errors.append(f"La réponse de sécurité #{answer_index} est requise.")
                continue
            if len(_normalize_security_answer(answer_text)) < 2:
                errors.append(f"La réponse de sécurité #{answer_index} est invalide.")

        if len(password) < 8:
            errors.append("Le mot de passe doit contenir au moins 8 caractères.")

        if password != password_confirm:
            errors.append("La confirmation du mot de passe ne correspond pas.")

        if not errors:
            email = form_data['email'].lower() if form_data['email'] else None
            phone = form_data['phone'] or None
            full_name = f"{form_data['first_name']} {form_data['last_name']}".strip()
            password_hash = _make_user_password_hash(password)
            birth_date_text = birth_date_obj.strftime('%Y-%m-%d') if birth_date_obj else None
            security_answer_hash_1 = _make_security_answer_hash(security_answer_1)
            security_answer_hash_2 = _make_security_answer_hash(security_answer_2)
            security_answer_hash_3 = _make_security_answer_hash(security_answer_3)

            conn = _get_db_connection()
            try:
                is_invitation_valid, invitation_error, invitation_row_id = _validate_invitation_for_registration(
                    conn,
                    form_data['invitation_code'],
                )
                if not is_invitation_valid:
                    errors.append(invitation_error)

                if not errors and invitation_row_id is not None:
                    now_text = datetime.now().isoformat(timespec='minutes')
                    cursor = conn.execute(
                        '''
                        UPDATE invitation_codes
                        SET used_at = ?
                        WHERE id = ? AND used_at IS NULL
                        ''',
                        (now_text, invitation_row_id),
                    )
                    if cursor.rowcount != 1:
                        errors.append("Ce code d'invitation a déjà été utilisé.")

                if errors:
                    conn.rollback()
                    return render_template(
                        'register.html',
                        errors=errors,
                        form_data=form_data,
                    )

                cursor = conn.execute(
                    '''
                    INSERT INTO users (
                        email,
                        phone,
                        password_hash,
                        full_name,
                        birth_date,
                        security_question_1,
                        security_answer_hash_1,
                        security_question_2,
                        security_answer_hash_2,
                        security_question_3,
                        security_answer_hash_3
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        email,
                        phone,
                        password_hash,
                        full_name,
                        birth_date_text,
                        form_data['security_question_1'],
                        security_answer_hash_1,
                        form_data['security_question_2'],
                        security_answer_hash_2,
                        form_data['security_question_3'],
                        security_answer_hash_3,
                    ),
                )
                created_user_id = int(cursor.lastrowid)
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                message = str(exc).lower()
                if 'users.email' in message:
                    errors.append("Cette adresse courriel est déjà utilisée.")
                elif 'users.phone' in message:
                    errors.append("Ce numéro de téléphone est déjà utilisé.")
                else:
                    errors.append("Impossible de créer le compte pour le moment.")
            finally:
                conn.close()

        if not errors and created_user_id is not None:
            session.clear()
            session['user_id'] = created_user_id
            session['is_admin_authenticated'] = False
            session['must_change_password'] = False
            session.permanent = True
            session['last_activity_ts'] = int(datetime.now(timezone.utc).timestamp())
            return redirect(url_for('calendar'))

    return render_template(
        'register.html',
        errors=errors,
        form_data=form_data,
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    errors = []
    success_message = None

    if session.get('is_admin_authenticated'):
        return redirect(url_for('admin_dashboard'))
    if session.get('user_id'):
        if session.get('must_change_password'):
            return redirect(url_for('force_password_change'))
        return redirect(url_for('calendar'))

    admin_exists = _admin_account_exists()
    user_exists = _any_user_account_exists()
    form_data = {
        'identifier': '',
        'admin_identifier': '',
    }

    if request.method == 'POST':
        form_action = request.form.get('form_action', 'login').strip()

        if form_action == 'create_admin':
            form_data['admin_identifier'] = request.form.get('admin_identifier', '').strip()
            admin_password = request.form.get('admin_password', '')
            admin_password_confirm = request.form.get('admin_password_confirm', '')

            if admin_exists:
                errors.append("Le compte administrateur existe déjà.")
            if not form_data['admin_identifier']:
                errors.append("Le courriel administrateur est requis.")
            if len(admin_password) < 8:
                errors.append("Le mot de passe administrateur doit contenir au moins 8 caractères.")
            if admin_password != admin_password_confirm:
                errors.append("La confirmation du mot de passe ne correspond pas.")

            if not errors:
                _save_admin_account(form_data['admin_identifier'], admin_password)
                admin_exists = True
                success_message = "Compte administrateur créé. Vous pouvez maintenant vous connecter."

        if form_action == 'login':
            form_data['identifier'] = request.form.get('identifier', '').strip()
            password = request.form.get('password', '')

            if not form_data['identifier']:
                errors.append("L'adresse courriel ou le téléphone est requis.")
            if not password:
                errors.append("Le mot de passe est requis.")

            if not errors:
                admin_account = _load_admin_account()
                identifier_lower = form_data['identifier'].lower()
                if admin_account and identifier_lower == admin_account['identifier']:
                    password_ok = _verify_password(
                        password,
                        admin_account['password_salt'],
                        admin_account['password_hash'],
                    )
                    if password_ok:
                        session['is_admin_authenticated'] = True
                        session.pop('password_reset_user_id', None)
                        session.pop('password_reset_verified_at', None)
                        session.permanent = True
                        session['last_activity_ts'] = int(datetime.now(timezone.utc).timestamp())
                        return redirect(url_for('admin_dashboard'))

            if not errors:
                identifier = form_data['identifier']
                identifier_lower = identifier.lower()

                conn = _get_db_connection()
                try:
                    user_row = conn.execute(
                        '''
                        SELECT id, email, phone, password_hash, is_blocked, must_change_password
                        FROM users
                        WHERE lower(email) = lower(?) OR phone = ?
                        LIMIT 1
                        ''',
                        (identifier_lower, identifier),
                    ).fetchone()
                finally:
                    conn.close()

                if not user_row:
                    errors.append("Identifiants invalides.")
                elif bool(user_row['is_blocked']):
                    errors.append("Ce compte utilisateur est bloqué.")
                elif not _verify_user_password(password, user_row['password_hash']):
                    errors.append("Identifiants invalides.")
                else:
                    session['user_id'] = user_row['id']
                    session['is_admin_authenticated'] = False
                    session.pop('password_reset_user_id', None)
                    session.pop('password_reset_verified_at', None)
                    session['must_change_password'] = bool(user_row['must_change_password'])
                    session.permanent = True
                    session['last_activity_ts'] = int(datetime.now(timezone.utc).timestamp())
                    if session.get('must_change_password'):
                        return redirect(url_for('force_password_change'))
                    return redirect(url_for('calendar'))

    return render_template(
        'login.html',
        errors=errors,
        success_message=success_message,
        form_data=form_data,
        admin_exists=admin_exists,
        user_exists=user_exists,
    )


@app.route('/account/password-reset', methods=['GET', 'POST'])
def password_reset():
    if session.get('is_admin_authenticated'):
        return redirect(url_for('admin_dashboard'))
    if session.get('user_id') and not session.get('must_change_password'):
        return redirect(url_for('calendar'))

    errors = []
    success_message = None
    reset_lookup_data = {
        'identifier': '',
        'birth_date': '',
    }
    reset_password_data = {
        'question_index': '1',
    }
    reset_questions = []
    reset_user_id = session.get('password_reset_user_id')

    if reset_user_id:
        conn = _get_db_connection()
        try:
            reset_row = conn.execute(
                '''
                SELECT id, security_question_1, security_question_2, security_question_3
                FROM users
                WHERE id = ?
                LIMIT 1
                ''',
                (reset_user_id,),
            ).fetchone()
        finally:
            conn.close()
        if reset_row:
            reset_questions = [
                {'index': 1, 'text': reset_row['security_question_1'] or ''},
                {'index': 2, 'text': reset_row['security_question_2'] or ''},
                {'index': 3, 'text': reset_row['security_question_3'] or ''},
            ]
        else:
            session.pop('password_reset_user_id', None)
            session.pop('password_reset_verified_at', None)

    if request.method == 'POST':
        form_action = request.form.get('form_action', 'reset_lookup').strip()

        if form_action == 'reset_lookup':
            reset_lookup_data['identifier'] = request.form.get('reset_identifier', '').strip()
            reset_lookup_data['birth_date'] = request.form.get('reset_birth_date', '').strip()

            if not reset_lookup_data['identifier']:
                errors.append("Le courriel ou le téléphone est requis pour la récupération.")
            if not reset_lookup_data['birth_date']:
                errors.append("La date de naissance est requise pour la récupération.")

            if not errors:
                try:
                    datetime.strptime(reset_lookup_data['birth_date'], '%Y-%m-%d')
                except ValueError:
                    errors.append("Date de naissance invalide.")

            if not errors:
                identifier = reset_lookup_data['identifier']
                identifier_lower = identifier.lower()
                conn = _get_db_connection()
                try:
                    user_row = conn.execute(
                        '''
                        SELECT id, security_question_1, security_question_2, security_question_3
                        FROM users
                        WHERE (lower(email) = lower(?) OR phone = ?)
                          AND birth_date = ?
                        LIMIT 1
                        ''',
                        (identifier_lower, identifier, reset_lookup_data['birth_date']),
                    ).fetchone()
                finally:
                    conn.close()

                if not user_row:
                    errors.append("Informations de récupération invalides.")
                    session.pop('password_reset_user_id', None)
                    session.pop('password_reset_verified_at', None)
                    reset_questions = []
                else:
                    session['password_reset_user_id'] = int(user_row['id'])
                    session['password_reset_verified_at'] = int(datetime.now(timezone.utc).timestamp())
                    reset_questions = [
                        {'index': 1, 'text': user_row['security_question_1'] or ''},
                        {'index': 2, 'text': user_row['security_question_2'] or ''},
                        {'index': 3, 'text': user_row['security_question_3'] or ''},
                    ]
                    success_message = "Vérification réussie. Répondez à une question pour définir un nouveau mot de passe."

        if form_action == 'reset_password':
            reset_password_data['question_index'] = request.form.get('reset_question_index', '1').strip()
            reset_answer = request.form.get('reset_answer', '').strip()
            new_password = request.form.get('reset_new_password', '')
            new_password_confirm = request.form.get('reset_new_password_confirm', '')

            reset_user_id = session.get('password_reset_user_id')
            if not reset_user_id:
                errors.append("Commencez par vérifier votre identité.")
            if reset_password_data['question_index'] not in {'1', '2', '3'}:
                errors.append("Question de sécurité invalide.")
            if not reset_answer:
                errors.append("La réponse de sécurité est requise.")
            if len(new_password) < 8:
                errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")
            if new_password != new_password_confirm:
                errors.append("La confirmation du mot de passe ne correspond pas.")

            user_row = None
            if not errors:
                conn = _get_db_connection()
                try:
                    user_row = conn.execute(
                        '''
                        SELECT id, security_answer_hash_1, security_answer_hash_2, security_answer_hash_3, security_question_1, security_question_2, security_question_3
                        FROM users
                        WHERE id = ?
                        LIMIT 1
                        ''',
                        (int(reset_user_id),),
                    ).fetchone()
                finally:
                    conn.close()

                if not user_row:
                    errors.append("Session de récupération expirée. Recommencez.")
                    session.pop('password_reset_user_id', None)
                    session.pop('password_reset_verified_at', None)

            if not errors and user_row:
                answer_hash = user_row[f'security_answer_hash_{reset_password_data["question_index"]}']
                if not _verify_security_answer(reset_answer, answer_hash):
                    errors.append("Réponse de sécurité invalide.")

            if not errors and user_row:
                new_password_hash = _make_user_password_hash(new_password)
                conn = _get_db_connection()
                try:
                    conn.execute(
                        'UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?',
                        (new_password_hash, int(reset_user_id)),
                    )
                    conn.commit()
                finally:
                    conn.close()
                session.pop('password_reset_user_id', None)
                session.pop('password_reset_verified_at', None)
                return redirect(url_for('login'))

    return render_template(
        'password_reset.html',
        errors=errors,
        success_message=success_message,
        reset_lookup_data=reset_lookup_data,
        reset_password_data=reset_password_data,
        reset_questions=reset_questions,
    )


@app.route('/admin/setup', methods=['GET', 'POST'])
def admin_setup():
    return redirect(url_for('login'))


@app.route('/account/password-change', methods=['GET', 'POST'])
def force_password_change():
    user_id = session.get('user_id')
    must_change = session.get('must_change_password', False)

    if not user_id:
        return redirect(url_for('login'))

    if not must_change:
        return redirect(url_for('calendar'))

    errors = []

    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        new_password_confirm = request.form.get('new_password_confirm', '')

        if len(new_password) < 8:
            errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")

        if new_password != new_password_confirm:
            errors.append("La confirmation du nouveau mot de passe ne correspond pas.")

        if not errors:
            new_password_hash = _make_user_password_hash(new_password)
            conn = _get_db_connection()
            try:
                conn.execute(
                    'UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?',
                    (new_password_hash, user_id),
                )
                conn.commit()
            finally:
                conn.close()

            session['must_change_password'] = False
            return redirect(url_for('calendar'))

    return render_template('force_password_change.html', errors=errors)


@app.route('/api/bookings', methods=['POST'])
def create_booking():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False, 'error': 'Connexion requise.'}), 401

    if session.get('must_change_password'):
        return jsonify({'ok': False, 'error': 'Vous devez d’abord changer votre mot de passe.'}), 403

    payload = request.get_json(silent=True) or request.form
    date_text = str(payload.get('date', '')).strip()
    start_text = str(payload.get('start_time', '')).strip()
    end_text = str(payload.get('end_time', '')).strip()
    title = str(payload.get('title', '')).strip()
    raw_companion_count = str(payload.get('companion_count', '0')).strip()
    if raw_companion_count == '':
        companion_count = 0
    elif raw_companion_count.isdigit():
        companion_count = int(raw_companion_count)
    else:
        return jsonify({'ok': False, 'error': "Nombre d'accompagnateurs invalide."}), 400

    raw_is_private = payload.get('is_private', False)
    if isinstance(raw_is_private, str):
        is_private = raw_is_private.strip().lower() in {'1', 'true', 'on', 'yes'}
    else:
        is_private = bool(raw_is_private)

    is_valid, error_message, _ = _validate_booking_request(
        user_id,
        date_text,
        start_text,
        end_text,
        companion_count=companion_count,
        is_private=is_private,
    )
    if not is_valid:
        return jsonify({'ok': False, 'error': error_message}), 400

    start_storage = _date_and_time_to_storage(date_text, start_text)
    end_storage = _date_and_time_to_storage(date_text, end_text)

    conn = _get_db_connection()
    try:
        conn.execute(
            '''
            INSERT INTO bookings (
                user_id,
                start,
                end,
                title,
                allow_companion,
                companion_count,
                is_private
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                user_id,
                start_storage,
                end_storage,
                title or None,
                1 if companion_count > 0 else 0,
                companion_count,
                1 if is_private else 0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({'ok': True})


@app.route('/calendar')
def calendar():
    opening_hours = _load_opening_hours()
    holidays = _load_holidays()
    special_dates = _load_special_dates()
    reservation_config = _load_reservation_config()
    bookings_by_date = _load_bookings_for_calendar()
    blocked_slot_rules = _load_blocked_slot_rules()
    calendar_js_path = Path(__file__).resolve().parent / 'static' / 'calendar.js'
    calendar_js_version = int(calendar_js_path.stat().st_mtime) if calendar_js_path.exists() else 1

    return render_template(
        'calendar.html',
        opening_hours_json=_opening_hours_for_calendar(opening_hours),
        holidays_json=holidays,
        special_dates_json=special_dates,
        reservation_config_json=reservation_config,
        bookings_json=bookings_by_date,
        blocked_slots_json=blocked_slot_rules,
        user_can_book=bool(session.get('user_id')) and not bool(session.get('must_change_password')),
        calendar_js_version=calendar_js_version,
    )


@app.route('/mes-reservations', methods=['GET', 'POST'])
def my_bookings():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    if session.get('must_change_password'):
        return redirect(url_for('force_password_change'))

    errors = []
    success_message = None
    reservation_config = _load_reservation_config()

    if request.method == 'POST':
        user_action = request.form.get('user_action', '').strip()
        booking_id_text = request.form.get('booking_id', '').strip()

        if not booking_id_text.isdigit():
            errors.append("Réservation invalide.")
        else:
            booking_id = int(booking_id_text)
            conn = _get_db_connection()
            try:
                booking_row = conn.execute(
                    '''
                    SELECT id, user_id, start, end, title, companion_count, is_private
                    FROM bookings
                    WHERE id = ? AND user_id = ?
                    LIMIT 1
                    ''',
                    (booking_id, user_id),
                ).fetchone()
            finally:
                conn.close()

            if not booking_row:
                errors.append("Réservation introuvable.")
            else:
                if user_action == 'delete_booking':
                    conn = _get_db_connection()
                    try:
                        conn.execute('DELETE FROM bookings WHERE id = ? AND user_id = ?', (booking_id, user_id))
                        conn.commit()
                        success_message = 'Réservation annulée.'
                    finally:
                        conn.close()

                if user_action == 'update_booking':
                    date_text = request.form.get('date', '').strip()
                    start_text = request.form.get('start_time', '').strip()
                    end_text = request.form.get('end_time', '').strip()
                    title = request.form.get('title', '').strip()
                    raw_companion_count = request.form.get('companion_count', '0').strip()
                    raw_is_private = request.form.get('is_private', '')

                    if raw_companion_count == '':
                        companion_count = 0
                    elif raw_companion_count.isdigit():
                        companion_count = int(raw_companion_count)
                    else:
                        companion_count = -1

                    is_private = raw_is_private == 'on'

                    is_valid, error_message, _ = _validate_booking_request(
                        user_id,
                        date_text,
                        start_text,
                        end_text,
                        companion_count=companion_count,
                        is_private=is_private,
                        exclude_booking_id=booking_id,
                    )
                    if not is_valid:
                        errors.append(error_message)
                    else:
                        start_storage = _date_and_time_to_storage(date_text, start_text)
                        end_storage = _date_and_time_to_storage(date_text, end_text)
                        conn = _get_db_connection()
                        try:
                            conn.execute(
                                '''
                                UPDATE bookings
                                SET start = ?, end = ?, title = ?, allow_companion = ?, companion_count = ?, is_private = ?
                                WHERE id = ? AND user_id = ?
                                ''',
                                (
                                    start_storage,
                                    end_storage,
                                    title or None,
                                    1 if companion_count > 0 else 0,
                                    companion_count,
                                    1 if is_private else 0,
                                    booking_id,
                                    user_id,
                                ),
                            )
                            conn.commit()
                            success_message = 'Réservation modifiée.'
                        finally:
                            conn.close()

    bookings = _load_bookings_for_user(user_id)
    return render_template(
        'my_bookings.html',
        bookings=bookings,
        reservation_config=reservation_config,
        errors=errors,
        success_message=success_message,
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not session.get('is_admin_authenticated'):
        return redirect(url_for('login'))

    errors = []
    success_message = None
    temporary_password_notice = None
    generated_invitation_code_notice = None
    invitation_mode_default = 'unique'
    active_tab = request.args.get('tab', 'bookings-panel')
    if active_tab not in {
        'opening-hours-panel',
        'bookings-panel',
        'blocked-slots-panel',
        'users-panel',
        'configuration-panel',
        'invitation-codes-panel',
    }:
        active_tab = 'bookings-panel'
    opening_hours = _load_opening_hours()
    holidays = _load_holidays()
    special_dates = _load_special_dates()
    reservation_config = _load_reservation_config()
    invitation_config = _load_invitation_config()
    blocked_slots = _load_blocked_slots_for_admin()
    blocked_slot_form = {
        'title': '',
        'repeat_type': 'once',
        'reference_date': '',
        'start_time': '09:00',
        'end_time': '10:00',
        'range_start': '',
        'range_end': '',
    }

    if request.method == 'POST':
        admin_action = request.form.get('admin_action', '').strip()

        if admin_action == 'save_opening_hours':
            active_tab = 'opening-hours-panel'
            updated_hours = {}

            for day_key, day_label, _ in DAY_CONFIG:
                closed = request.form.get(f'closed_{day_key}') == 'on'
                start_text = request.form.get(f'start_{day_key}', '').strip()
                end_text = request.form.get(f'end_{day_key}', '').strip()

                if closed:
                    updated_hours[day_key] = {
                        'closed': True,
                        'start': opening_hours.get(day_key, {}).get('start', '09:00'),
                        'end': opening_hours.get(day_key, {}).get('end', '17:00'),
                    }
                    continue

                start_minutes = _time_text_to_minutes(start_text)
                end_minutes = _time_text_to_minutes(end_text)

                if start_minutes is None or end_minutes is None:
                    errors.append(f"{day_label}: format d'heure invalide.")
                    continue

                if end_minutes <= start_minutes:
                    errors.append(f"{day_label}: l'heure de fin doit être après l'heure de début.")
                    continue

                updated_hours[day_key] = {
                    'closed': False,
                    'start': start_text,
                    'end': end_text,
                }

            if not errors:
                _save_opening_hours(updated_hours)
                opening_hours = _load_opening_hours()
                success_message = 'Heures d\'ouverture mises à jour.'
            else:
                opening_hours = _normalize_opening_hours(updated_hours)

        if admin_action == 'save_special_date':
            active_tab = 'opening-hours-panel'
            special_date = request.form.get('special_date', '').strip()
            special_closed = request.form.get('special_closed') == 'on'
            special_start = request.form.get('special_start', '').strip()
            special_end = request.form.get('special_end', '').strip()
            special_reason = request.form.get('special_reason', '').strip()

            if not _is_valid_iso_date_text(special_date):
                errors.append("Date spéciale invalide.")
            elif special_closed:
                updated_special_dates = [
                    item for item in special_dates
                    if item.get('date') != special_date
                ]
                updated_special_dates.append(
                    {
                        'date': special_date,
                        'closed': True,
                        'start': '00:00',
                        'end': '00:00',
                        'reason': special_reason,
                    }
                )
                _save_special_dates(updated_special_dates)
                special_dates = _load_special_dates()
                success_message = 'Horaire spécial enregistré.'
            else:
                start_minutes = _time_text_to_minutes(special_start)
                end_minutes = _time_text_to_minutes(special_end)
                if start_minutes is None or end_minutes is None:
                    errors.append("Date spéciale: format d'heure invalide.")
                elif end_minutes <= start_minutes:
                    errors.append("Date spéciale: l'heure de fin doit être après l'heure de début.")
                else:
                    updated_special_dates = [
                        item for item in special_dates
                        if item.get('date') != special_date
                    ]
                    updated_special_dates.append(
                        {
                            'date': special_date,
                            'closed': False,
                            'start': special_start,
                            'end': special_end,
                            'reason': special_reason,
                        }
                    )
                    _save_special_dates(updated_special_dates)
                    special_dates = _load_special_dates()
                    success_message = 'Horaire spécial enregistré.'

        if admin_action == 'delete_special_date':
            active_tab = 'opening-hours-panel'
            special_date = request.form.get('special_date', '').strip()
            if not _is_valid_iso_date_text(special_date):
                errors.append("Date spéciale invalide.")
            else:
                updated_special_dates = [
                    item for item in special_dates
                    if item.get('date') != special_date
                ]
                if len(updated_special_dates) == len(special_dates):
                    errors.append("Aucune date spéciale correspondante à supprimer.")
                else:
                    _save_special_dates(updated_special_dates)
                    special_dates = _load_special_dates()
                    success_message = 'Horaire spécial supprimé.'

        if admin_action == 'save_reservation_config':
            active_tab = 'configuration-panel'
            raw_max_sim = request.form.get('max_simultaneous_bookings', '').strip()
            raw_min_duration = request.form.get('min_duration_minutes', '').strip()
            raw_max_duration = request.form.get('max_duration_minutes', '').strip()
            raw_latest_start = request.form.get('latest_start_before_close_minutes', '').strip()
            raw_slot_interval = request.form.get('slot_interval_minutes', '').strip()
            raw_fixed_interval = request.form.get('fixed_time_interval_minutes', '').strip()
            raw_frequency_limit_value = request.form.get('frequency_limit_value', '').strip()
            raw_frequency_limit_period_value = request.form.get('frequency_limit_period_value', '').strip()
            raw_frequency_limit_metric = request.form.get('frequency_limit_metric', '').strip().lower()
            raw_frequency_limit_period_unit = request.form.get('frequency_limit_period_unit', '').strip().lower()

            slot_interval_enabled = request.form.get('slot_interval_enabled') == 'on'
            allow_back_to_back = request.form.get('allow_back_to_back') == 'on'
            fixed_time_only = request.form.get('fixed_time_only') == 'on'
            allow_companion_booking = request.form.get('allow_companion_booking') == 'on'
            allow_private_room_choice = request.form.get('allow_private_room_choice') == 'on'
            single_booking_per_day = request.form.get('single_booking_per_day') == 'on'
            frequency_limit_enabled = request.form.get('frequency_limit_enabled') == 'on'

            if not raw_max_sim.isdigit() or int(raw_max_sim) < 1:
                errors.append("Capacité maximale (personnes) doit être un entier >= 1.")
            if not raw_min_duration.isdigit() or int(raw_min_duration) < 1:
                errors.append("Temps minimal doit être un entier >= 1 minute.")
            if not raw_max_duration.isdigit() or int(raw_max_duration) < 1:
                errors.append("Temps maximal doit être un entier >= 1 minute.")
            if not raw_latest_start.isdigit() or int(raw_latest_start) < 0:
                errors.append("Délai maximal avant fermeture doit être un entier >= 0 minute.")

            min_duration = int(raw_min_duration) if raw_min_duration.isdigit() else 0
            max_duration = int(raw_max_duration) if raw_max_duration.isdigit() else 0
            if min_duration and max_duration and max_duration < min_duration:
                errors.append("Temps maximal doit être supérieur ou égal au temps minimal.")

            if not raw_slot_interval.isdigit() or int(raw_slot_interval) not in VALID_SLOT_INTERVALS:
                errors.append("Tranche de temps doit être 15, 30 ou 60 minutes.")
            if not raw_fixed_interval.isdigit() or int(raw_fixed_interval) not in VALID_SLOT_INTERVALS:
                errors.append("Heures fixes doit être 15, 30 ou 60 minutes.")

            if frequency_limit_enabled:
                if raw_frequency_limit_metric not in {'bookings', 'hours'}:
                    errors.append("Le type de limite de fréquentation est invalide.")
                if raw_frequency_limit_period_unit not in {'days', 'weeks', 'months'}:
                    errors.append("La période de limite de fréquentation est invalide.")
                if not raw_frequency_limit_value.isdigit() or int(raw_frequency_limit_value) < 1:
                    errors.append("La valeur de limite de fréquentation doit être un entier >= 1.")
                if not raw_frequency_limit_period_value.isdigit() or int(raw_frequency_limit_period_value) < 1:
                    errors.append("La durée de période doit être un entier >= 1.")

            candidate_config = {
                'max_simultaneous_bookings': int(raw_max_sim) if raw_max_sim.isdigit() else reservation_config['max_simultaneous_bookings'],
                'min_duration_minutes': min_duration if min_duration > 0 else reservation_config['min_duration_minutes'],
                'max_duration_minutes': max_duration if max_duration > 0 else reservation_config['max_duration_minutes'],
                'latest_start_before_close_minutes': int(raw_latest_start) if raw_latest_start.isdigit() else reservation_config['latest_start_before_close_minutes'],
                'slot_interval_enabled': slot_interval_enabled,
                'slot_interval_minutes': int(raw_slot_interval) if raw_slot_interval.isdigit() else reservation_config['slot_interval_minutes'],
                'allow_back_to_back': allow_back_to_back,
                'fixed_time_only': fixed_time_only,
                'fixed_time_interval_minutes': int(raw_fixed_interval) if raw_fixed_interval.isdigit() else reservation_config['fixed_time_interval_minutes'],
                'allow_companion_booking': allow_companion_booking,
                'allow_private_room_choice': allow_private_room_choice,
                'single_booking_per_day': single_booking_per_day,
                'frequency_limit_enabled': frequency_limit_enabled,
                'frequency_limit_metric': (
                    raw_frequency_limit_metric
                    if raw_frequency_limit_metric in {'bookings', 'hours'}
                    else reservation_config['frequency_limit_metric']
                ),
                'frequency_limit_value': (
                    int(raw_frequency_limit_value)
                    if raw_frequency_limit_value.isdigit()
                    else reservation_config['frequency_limit_value']
                ),
                'frequency_limit_period_value': (
                    int(raw_frequency_limit_period_value)
                    if raw_frequency_limit_period_value.isdigit()
                    else reservation_config['frequency_limit_period_value']
                ),
                'frequency_limit_period_unit': (
                    raw_frequency_limit_period_unit
                    if raw_frequency_limit_period_unit in {'days', 'weeks', 'months'}
                    else reservation_config['frequency_limit_period_unit']
                ),
            }

            if not errors:
                _save_reservation_config(candidate_config)
                reservation_config = _load_reservation_config()
                success_message = 'Configuration des réservations mise à jour.'
            else:
                reservation_config = _normalize_reservation_config(candidate_config)

        if admin_action == 'save_invitation_config':
            active_tab = 'invitation-codes-panel'
            invitation_mode_default = 'custom'
            custom_code_enabled = request.form.get('custom_code_enabled') == 'on'
            custom_code = request.form.get('custom_code', '').strip()
            raw_validity_days = request.form.get('one_time_validity_days', '').strip()

            if custom_code_enabled and not custom_code:
                errors.append("Le code personnalisé est requis quand l'option est activée.")
            if raw_validity_days:
                if not raw_validity_days.isdigit() or int(raw_validity_days) < 1:
                    errors.append("La durée de validité doit être un entier >= 1 jour.")

            validity_days = invitation_config['one_time_validity_days']
            if raw_validity_days and raw_validity_days.isdigit():
                validity_days = int(raw_validity_days)
            candidate_config = {
                'custom_code_enabled': custom_code_enabled,
                'custom_code': custom_code,
                'one_time_validity_days': validity_days,
            }

            if not errors:
                _save_invitation_config(candidate_config)
                invitation_config = _load_invitation_config()
                success_message = "Configuration des codes d'invitation mise à jour."
            else:
                invitation_config = _normalize_invitation_config(candidate_config)

        if admin_action == 'generate_invitation_code':
            active_tab = 'invitation-codes-panel'
            invitation_mode_default = 'unique'
            raw_validity_days = request.form.get('one_time_validity_days', '').strip()
            if not raw_validity_days.isdigit() or int(raw_validity_days) < 1:
                errors.append("Durée invalide. Utilisez un nombre de jours >= 1.")
            else:
                validity_days = int(raw_validity_days)
                conn = _get_db_connection()
                try:
                    code, expires_at = _generate_one_time_invitation_code(conn, validity_days)
                    conn.commit()
                    generated_invitation_code_notice = f"Code généré: {code} (valide jusqu'au {expires_at.replace('T', ' ')})"
                    success_message = "Code d'invitation à usage unique généré."
                except RuntimeError as exc:
                    conn.rollback()
                    errors.append(str(exc))
                finally:
                    conn.close()

        if admin_action == 'delete_invitation_code':
            active_tab = 'invitation-codes-panel'
            invitation_mode_default = 'unique'
            raw_code_id = request.form.get('invitation_code_id', '').strip()
            if not raw_code_id.isdigit():
                errors.append("Code d'invitation invalide.")
            else:
                code_id = int(raw_code_id)
                conn = _get_db_connection()
                try:
                    deleted = conn.execute(
                        'DELETE FROM invitation_codes WHERE id = ?',
                        (code_id,),
                    ).rowcount
                    if deleted:
                        conn.commit()
                        success_message = "Code d'invitation supprimé."
                    else:
                        conn.rollback()
                        errors.append("Code d'invitation introuvable.")
                except sqlite3.Error:
                    conn.rollback()
                    errors.append("Impossible de supprimer le code d'invitation.")
                finally:
                    conn.close()

        if admin_action in {'create_blocked_slot', 'delete_blocked_slot'}:
            active_tab = 'blocked-slots-panel'

            if admin_action == 'create_blocked_slot':
                blocked_slot_form = {
                    'title': request.form.get('blocked_title', '').strip(),
                    'repeat_type': request.form.get('repeat_type', 'once').strip(),
                    'reference_date': request.form.get('reference_date', '').strip(),
                    'start_time': request.form.get('blocked_start_time', '').strip(),
                    'end_time': request.form.get('blocked_end_time', '').strip(),
                    'range_start': request.form.get('range_start', '').strip(),
                    'range_end': request.form.get('range_end', '').strip(),
                }

                repeat_type = blocked_slot_form['repeat_type']
                if repeat_type not in {'once', 'weekly', 'yearly', 'holiday'}:
                    errors.append("Type de répétition invalide.")

                start_minutes = _time_text_to_minutes(blocked_slot_form['start_time'])
                end_minutes = _time_text_to_minutes(blocked_slot_form['end_time'])
                if start_minutes is None or end_minutes is None:
                    errors.append("Heure de début/fin invalide.")
                elif end_minutes <= start_minutes:
                    errors.append("L'heure de fin doit être après l'heure de début.")

                date_value = ''
                weekday = None
                month_day = ''
                reference_date = blocked_slot_form['reference_date']

                if repeat_type in {'once', 'weekly', 'yearly'} and not _is_valid_iso_date_text(reference_date):
                    errors.append("Date de référence invalide.")

                if repeat_type == 'once' and _is_valid_iso_date_text(reference_date):
                    date_value = reference_date

                if repeat_type == 'weekly' and _is_valid_iso_date_text(reference_date):
                    weekday = datetime.strptime(reference_date, '%Y-%m-%d').date().weekday()

                if repeat_type == 'yearly' and _is_valid_iso_date_text(reference_date):
                    month_day = reference_date[5:]

                if blocked_slot_form['range_start'] and not _is_valid_iso_date_text(blocked_slot_form['range_start']):
                    errors.append("Date de début de période invalide.")
                if blocked_slot_form['range_end'] and not _is_valid_iso_date_text(blocked_slot_form['range_end']):
                    errors.append("Date de fin de période invalide.")
                if (
                    blocked_slot_form['range_start']
                    and blocked_slot_form['range_end']
                    and blocked_slot_form['range_end'] < blocked_slot_form['range_start']
                ):
                    errors.append("La fin de période doit être après le début de période.")

                if not errors:
                    conn = _get_db_connection()
                    try:
                        conn.execute(
                            '''
                            INSERT INTO blocked_slots (
                                title,
                                repeat_type,
                                date_value,
                                weekday,
                                month_day,
                                start_time,
                                end_time,
                                range_start,
                                range_end
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''',
                            (
                                blocked_slot_form['title'] or None,
                                repeat_type,
                                date_value or None,
                                weekday,
                                month_day or None,
                                blocked_slot_form['start_time'],
                                blocked_slot_form['end_time'],
                                blocked_slot_form['range_start'] or None,
                                blocked_slot_form['range_end'] or None,
                            ),
                        )
                        conn.commit()
                        blocked_slot_form = {
                            'title': '',
                            'repeat_type': 'once',
                            'reference_date': '',
                            'start_time': '09:00',
                            'end_time': '10:00',
                            'range_start': '',
                            'range_end': '',
                        }
                        success_message = 'Créneau bloqué enregistré.'
                    finally:
                        conn.close()

            if admin_action == 'delete_blocked_slot':
                blocked_id_text = request.form.get('blocked_slot_id', '').strip()
                if not blocked_id_text.isdigit():
                    errors.append("Créneau bloqué invalide.")
                else:
                    conn = _get_db_connection()
                    try:
                        conn.execute('DELETE FROM blocked_slots WHERE id = ?', (int(blocked_id_text),))
                        conn.commit()
                        success_message = 'Créneau bloqué supprimé.'
                    finally:
                        conn.close()

        if admin_action in {'toggle_user_block', 'set_user_limit', 'delete_user', 'reset_user_password'}:
            active_tab = 'users-panel'
            user_id_text = request.form.get('user_id', '').strip()
            if not user_id_text.isdigit():
                errors.append("Utilisateur invalide.")
            else:
                user_id = int(user_id_text)
                conn = _get_db_connection()
                try:
                    user_row = conn.execute(
                        'SELECT id FROM users WHERE id = ?',
                        (user_id,),
                    ).fetchone()
                    if not user_row:
                        errors.append("Utilisateur introuvable.")
                    else:
                        if admin_action == 'toggle_user_block':
                            blocked_value = 1 if request.form.get('blocked_value') == '1' else 0
                            conn.execute(
                                'UPDATE users SET is_blocked = ? WHERE id = ?',
                                (blocked_value, user_id),
                            )
                            success_message = 'Statut de blocage utilisateur mis à jour.'

                        if admin_action == 'set_user_limit':
                            raw_limit = request.form.get('reservation_limit', '').strip()
                            if raw_limit == '':
                                limit_value = None
                            elif raw_limit.isdigit() and int(raw_limit) >= 0:
                                limit_value = int(raw_limit)
                            else:
                                errors.append("Limite invalide. Utilisez un nombre entier positif.")
                                limit_value = None

                            if not errors:
                                conn.execute(
                                    'UPDATE users SET reservation_limit = ? WHERE id = ?',
                                    (limit_value, user_id),
                                )
                                success_message = 'Limite de réservation mise à jour.'

                        if admin_action == 'delete_user':
                            conn.execute('DELETE FROM bookings WHERE user_id = ?', (user_id,))
                            conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
                            success_message = 'Compte utilisateur supprimé.'

                        if admin_action == 'reset_user_password':
                            temp_code = _generate_temporary_password_code()
                            temp_hash = _make_user_password_hash(temp_code)
                            conn.execute(
                                'UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?',
                                (temp_hash, user_id),
                            )
                            success_message = 'Mot de passe temporaire généré.'
                            temporary_password_notice = f"Code temporaire utilisateur #{user_id}: {temp_code}"

                    if not errors:
                        conn.commit()
                    else:
                        conn.rollback()
                finally:
                    conn.close()

        if admin_action == 'delete_booking':
            active_tab = 'bookings-panel'
            booking_id_text = request.form.get('booking_id', '').strip()
            if not booking_id_text.isdigit():
                errors.append("Réservation invalide.")
            else:
                booking_id = int(booking_id_text)
                conn = _get_db_connection()
                try:
                    row = conn.execute(
                        'SELECT id FROM bookings WHERE id = ?',
                        (booking_id,),
                    ).fetchone()
                    if not row:
                        errors.append("Réservation introuvable.")
                    else:
                        conn.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
                        conn.commit()
                        success_message = 'Réservation supprimée.'
                finally:
                    conn.close()

    admin_account = _load_admin_account()
    admin_identifier = admin_account['identifier'] if admin_account else 'Administrateur'
    bookings = _load_bookings_for_admin()
    bookings_grouped = _group_bookings_by_date(bookings)
    users = _load_users_for_admin()
    invitation_codes = _load_invitation_codes_for_admin()
    blocked_slots = _load_blocked_slots_for_admin()
    bookings_by_date = _load_bookings_for_calendar()
    blocked_slot_rules = _load_blocked_slot_rules()
    calendar_js_path = Path(__file__).resolve().parent / 'static' / 'calendar.js'
    calendar_js_version = int(calendar_js_path.stat().st_mtime) if calendar_js_path.exists() else 1

    return render_template(
        'admin_dashboard.html',
        admin_identifier=admin_identifier,
        opening_hours=opening_hours,
        opening_hours_json=_opening_hours_for_calendar(opening_hours),
        holidays_json=holidays,
        special_dates=special_dates,
        special_dates_json=special_dates,
        reservation_config=reservation_config,
        reservation_config_json=reservation_config,
        valid_slot_intervals=sorted(VALID_SLOT_INTERVALS),
        bookings=bookings,
        bookings_json=bookings_by_date,
        bookings_grouped=bookings_grouped,
        users=users,
        invitation_config=invitation_config,
        invitation_codes=invitation_codes,
        blocked_slots=blocked_slots,
        blocked_slots_json=blocked_slot_rules,
        blocked_slot_form=blocked_slot_form,
        blocked_slot_repeat_options=BLOCKED_SLOT_REPEAT_OPTIONS,
        generated_invitation_code_notice=generated_invitation_code_notice,
        invitation_mode_default=invitation_mode_default,
        temporary_password_notice=temporary_password_notice,
        user_can_book=False,
        calendar_js_version=calendar_js_version,
        active_tab=active_tab,
        current_day_key=datetime.now().strftime('%Y-%m-%d'),
        day_config=DAY_CONFIG,
        errors=errors,
        success_message=success_message,
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=39048, debug=True)
