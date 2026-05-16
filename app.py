import base64
import calendar as pycalendar
import hashlib
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

_fallback_key = secrets.token_hex(32)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', _fallback_key)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(days=30)

DATA_DIR = Path(__file__).resolve().parent / 'data'
STATIC_DIR = Path(__file__).resolve().parent / 'static'
LOG_DIR = Path(__file__).resolve().parent / 'logs'
ADMIN_STORE_PATH = DATA_DIR / 'admin_account.json'
ADMIN_KEY_PATH = DATA_DIR / 'admin_account.key'
SUPER_ADMIN_RECOVERY_PATH = DATA_DIR / 'super_admin_account.json'
OPENING_HOURS_PATH = DATA_DIR / 'opening_hours.json'
DATABASE_PATH = DATA_DIR / 'sunnyvibe.db'
RESERVATION_CONFIG_PATH = DATA_DIR / 'reservation_config.json'
INVITATION_CONFIG_PATH = DATA_DIR / 'invitation_config.json'
MENU_PATH = DATA_DIR / 'menu.json'
DEFAULT_MENU_DISCLAIMER_TEXTS = [
    "Il est à noter que nous ne pouvons garantir que nos produits, une fois reconstitués au Sunny Vibes Nutrition, seront exempts de quelconque allergène ou intolérance.",
    "Il est donc IMPORTANT de nous aviser si vous avez des ALLERGIES et/ou une INTOLÉRANCE dès votre arrivée.",
    "De plus, il est aussi IMPORTANT de nous aviser si vous êtes ENCEINTE, si vous ALLAITEZ ou si vous êtes atteint d'une MALADIE afin que nous puissions vous conseiller des produits adaptés à votre situation.",
]
SUPER_ADMIN_IDENTIFIER = 'butts136'
SUPER_ADMIN_DISPLAY_NAME = 'Butts136'
SUPER_ADMIN_IDENTIFIERS = {SUPER_ADMIN_IDENTIFIER}
SUPER_ADMIN_USER_EMAIL = 'butts136@sunnyvibe.local'
SUPER_ADMIN_USER_FULL_NAME = 'Butts136 SuperAdmin'
SUPER_ADMIN_BOOTSTRAP_SALT = 'r8Lt5Yr27augWpc8IR36pA=='
SUPER_ADMIN_BOOTSTRAP_HASH = 'FvvcQI9GBk1m1hRJ9q27Sbq4Jb4xOmHf1fZpWbaz2oE='
SUPER_ADMIN_RECOVERY_SIGNATURE_KEY = 'be5954dcc7dec12af5c99dc8f5ebf6f2ae90d0ef8480322d6b1719b58848a313'

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
DEFAULT_RESERVATION_TIMEZONE = 'America/Toronto'
AVAILABILITY_MODE_OPENING_HOURS = 'opening_hours'
AVAILABILITY_MODE_ACTIVE_SLOTS = 'active_slots'
AVAILABILITY_MODE_OPENING_HOURS_WITH_OVERRIDES = 'opening_hours_with_overrides'
VALID_AVAILABILITY_MODES = {
    AVAILABILITY_MODE_OPENING_HOURS,
    AVAILABILITY_MODE_ACTIVE_SLOTS,
    AVAILABILITY_MODE_OPENING_HOURS_WITH_OVERRIDES,
}
WEEK_START_SUNDAY = 'sunday'
WEEK_START_MONDAY = 'monday'
VALID_WEEK_START_DAYS = {
    WEEK_START_SUNDAY,
    WEEK_START_MONDAY,
}
SUNNYGYM_DISPLAY_MODE_CALENDAR = 'calendar'
SUNNYGYM_DISPLAY_MODE_CARDS = 'cards'
VALID_SUNNYGYM_DISPLAY_MODES = {
    SUNNYGYM_DISPLAY_MODE_CALENDAR,
    SUNNYGYM_DISPLAY_MODE_CARDS,
}


def _configure_logging():
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / 'sunnyvibe.log'
    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding='utf-8',
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
    )

    app.logger.setLevel(logging.INFO)
    if not any(
        isinstance(existing, RotatingFileHandler)
        and getattr(existing, 'baseFilename', '') == str(log_path)
        for existing in app.logger.handlers
    ):
        app.logger.addHandler(handler)


_configure_logging()


def _static_asset_version(filename):
    asset_path = STATIC_DIR / filename
    try:
        return int(asset_path.stat().st_mtime)
    except OSError:
        return 1


def _build_reservation_timezone_options():
    try:
        timezone_names = sorted(available_timezones())
    except Exception:
        timezone_names = [DEFAULT_RESERVATION_TIMEZONE, 'UTC']

    if DEFAULT_RESERVATION_TIMEZONE in timezone_names:
        timezone_names.remove(DEFAULT_RESERVATION_TIMEZONE)
    timezone_names.insert(0, DEFAULT_RESERVATION_TIMEZONE)

    if 'UTC' in timezone_names:
        timezone_names.remove('UTC')
    timezone_names.insert(1, 'UTC')

    options = []
    for timezone_name in timezone_names:
        if timezone_name == DEFAULT_RESERVATION_TIMEZONE:
            label = f"Québec ({timezone_name})"
        else:
            label = timezone_name
        options.append((timezone_name, label))
    return options


RESERVATION_TIMEZONE_OPTIONS = _build_reservation_timezone_options()
VALID_RESERVATION_TIMEZONES = {item[0] for item in RESERVATION_TIMEZONE_OPTIONS}
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
MENU_CATEGORY_OPTIONS = [
    ('all', 'Tout'),
    ('tea_bombs', 'Bombe à thé'),
    ('shakes', 'Shake'),
    ('protein_juices', 'Jus protéiné'),
    ('protein_coffees', 'Café protéiné'),
    ('kids_juices', 'Jus enfant'),
    ('extras', 'Extras'),
    ('hangover', 'HANGOVER'),
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
                username TEXT,
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

            CREATE TABLE IF NOT EXISTS active_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                date_value TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_active_slots_date_value ON active_slots(date_value);
            '''
        )
        user_columns = {
            row['name'] for row in conn.execute('PRAGMA table_info(users)').fetchall()
        }
        if 'is_blocked' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0')
        if 'username' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN username TEXT')
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
        if 'booking_status' not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN booking_status TEXT NOT NULL DEFAULT 'upcoming'")
        conn.execute(
            '''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower
                ON users(lower(username))
                WHERE username IS NOT NULL AND username != ''
            '''
        )
        conn.commit()
    finally:
        conn.close()
    _ensure_super_admin_user()


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
    now_year = _now_in_reservation_timezone().year
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


def _format_opening_hours_text(day_data):
    if not isinstance(day_data, dict) or day_data.get('closed', True):
        return 'Fermé'
    return f"{day_data.get('start', '09:00')} à {day_data.get('end', '17:00')}"


def _format_french_date(date_obj):
    return f"{date_obj.day} {FRENCH_MONTHS.get(date_obj.month, str(date_obj.month))} {date_obj.year}"


def _format_day_group_label(day_labels):
    if not day_labels:
        return ''
    if len(day_labels) == 1:
        return day_labels[0]
    if len(day_labels) == 2:
        return f"{day_labels[0]} et {day_labels[1]}"
    return f"{day_labels[0]} à {day_labels[-1]}"


def _append_unique(values, value):
    text = str(value or '').strip()
    if text and text not in values:
        values.append(text)


def _is_date_active_or_future(date_obj, reference_dt=None):
    current_dt = reference_dt or _now_in_reservation_timezone()
    end_of_target_day = datetime.combine(
        date_obj,
        datetime.max.time(),
        tzinfo=current_dt.tzinfo,
    )
    return end_of_target_day >= current_dt


def _build_grouped_weekly_hours(opening_hours):
    ordered_days = [
        ('sunday', 'Dimanche'),
        ('monday', 'Lundi'),
        ('tuesday', 'Mardi'),
        ('wednesday', 'Mercredi'),
        ('thursday', 'Jeudi'),
        ('friday', 'Vendredi'),
        ('saturday', 'Samedi'),
    ]

    groups = []
    for day_key, day_label in ordered_days:
        hours_text = _format_opening_hours_text(opening_hours.get(day_key, {}))
        if groups and groups[-1]['hours_text'] == hours_text:
            groups[-1]['day_labels'].append(day_label)
            continue

        groups.append(
            {
                'day_labels': [day_label],
                'hours_text': hours_text,
                'is_closed': hours_text == 'Fermé',
            }
        )

    normalized_groups = []
    for group in groups:
        day_labels = group['day_labels']
        normalized_groups.append(
            {
                'days_label': _format_day_group_label(day_labels),
                'day_count': len(day_labels),
                'hours_text': group['hours_text'],
                'is_closed': group['is_closed'],
            }
        )

    return normalized_groups


def _build_weekly_hours(opening_hours):
    ordered_days = _ordered_weekly_days()
    weekly_rows = []
    for day_key, day_label in ordered_days:
        hours_text = _format_opening_hours_text(opening_hours.get(day_key, {}))
        weekly_rows.append(
            {
                'day_key': day_key,
                'day_label': day_label,
                'hours_text': hours_text,
                'is_closed': hours_text == 'Fermé',
            }
        )
    return weekly_rows


def _ordered_weekly_days(week_start_day=WEEK_START_SUNDAY):
    ordered_days = [
        ('sunday', 'Dimanche'),
        ('monday', 'Lundi'),
        ('tuesday', 'Mardi'),
        ('wednesday', 'Mercredi'),
        ('thursday', 'Jeudi'),
        ('friday', 'Vendredi'),
        ('saturday', 'Samedi'),
    ]
    if week_start_day == WEEK_START_MONDAY:
        return ordered_days[1:] + ordered_days[:1]
    return ordered_days


def _build_merged_weekly_hours(opening_hours, week_start_day=WEEK_START_SUNDAY):
    ordered_days = _ordered_weekly_days(week_start_day)
    merged_rows = []
    current_group = None

    for index, (day_key, day_label) in enumerate(ordered_days, start=1):
        hours_text = _format_opening_hours_text(opening_hours.get(day_key, {}))
        if current_group and current_group['hours_text'] == hours_text:
            current_group['day_labels'].append(day_label)
            current_group['span'] += 1
            continue

        current_group = {
            'day_key': day_key,
            'day_labels': [day_label],
            'hours_text': hours_text,
            'is_closed': hours_text == 'Fermé',
            'span': 1,
            'column_start': index,
        }
        merged_rows.append(current_group)

    normalized_rows = []
    for row in merged_rows:
        labels = row['day_labels']
        if len(labels) == 1:
            day_label = labels[0]
        elif len(labels) == 2:
            day_label = f"{labels[0]} et {labels[1]}"
        else:
            day_label = f"{labels[0]} à {labels[-1]}"

        normalized_rows.append(
            {
                'day_key': row['day_key'],
                'day_label': day_label,
                'hours_text': row['hours_text'],
                'is_closed': row['is_closed'],
                'span': row['span'],
                'column_start': row['column_start'],
            }
        )

    return normalized_rows


def _build_upcoming_special_dates(opening_hours, holidays, special_dates, reference_date=None, limit=10):
    today = reference_date or _now_in_reservation_timezone().date()
    day_keys_by_python_weekday = [
        'monday',
        'tuesday',
        'wednesday',
        'thursday',
        'friday',
        'saturday',
        'sunday',
    ]
    weekday_labels = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    events_by_date = {}

    def _event_for_date(date_obj):
        date_key = date_obj.strftime('%Y-%m-%d')
        if date_key not in events_by_date:
            day_key = day_keys_by_python_weekday[date_obj.weekday()]
            regular_hours = _format_opening_hours_text(opening_hours.get(day_key, {}))
            events_by_date[date_key] = {
                'date': date_key,
                'date_label': _format_french_date(date_obj),
                'weekday_label': weekday_labels[date_obj.weekday()],
                'title_parts': [],
                'notes': [],
                'badges': [],
                'hours_text': regular_hours,
                'hours_context': 'Horaire régulier',
                'is_closed': regular_hours == 'Fermé',
                'is_holiday': False,
                'has_special_hours': False,
            }
        return events_by_date[date_key]

    for holiday in holidays:
        explicit_date = str(holiday.get('date', '')).strip()
        recurring_month_day = str(holiday.get('month_day', '')).strip()
        occurrences = []

        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', explicit_date):
            holiday_date = datetime.strptime(explicit_date, '%Y-%m-%d').date()
            if holiday_date >= today:
                occurrences.append(holiday_date)
        elif re.fullmatch(r'\d{2}-\d{2}', recurring_month_day):
            month_text, day_text = recurring_month_day.split('-', 1)
            month = int(month_text)
            day = int(day_text)
            for year in range(today.year, today.year + 4):
                try:
                    holiday_date = datetime(year, month, day).date()
                except ValueError:
                    continue
                if holiday_date >= today:
                    occurrences.append(holiday_date)

        for holiday_date in occurrences:
            event = _event_for_date(holiday_date)
            event['is_holiday'] = True
            _append_unique(event['badges'], 'Férié')
            _append_unique(event['title_parts'], holiday.get('name', 'Férié'))
            _append_unique(event['notes'], holiday.get('alert', ''))

    for special_day in special_dates:
        date_text = str(special_day.get('date', '')).strip()
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date_text):
            continue

        special_date = datetime.strptime(date_text, '%Y-%m-%d').date()
        if special_date < today:
            continue

        event = _event_for_date(special_date)
        event['has_special_hours'] = True
        _append_unique(event['badges'], 'Horaire spécial')

        reason = str(special_day.get('reason', '')).strip()
        if reason:
            _append_unique(event['notes'], reason)

        if special_day.get('closed', False):
            event['hours_text'] = 'Fermé'
            event['hours_context'] = 'Fermé exceptionnellement'
            event['is_closed'] = True
        else:
            event['hours_text'] = f"{special_day.get('start', '09:00')} à {special_day.get('end', '17:00')}"
            event['hours_context'] = 'Horaire spécial'
            event['is_closed'] = False

    upcoming_events = []
    for date_key in sorted(events_by_date.keys())[:limit]:
        event = events_by_date[date_key]
        title = ' · '.join(event['title_parts']).strip()
        if not title:
            title = 'Horaire modifié'
        if not event['notes'] and event['has_special_hours'] and not event['is_holiday']:
            event['notes'] = ["Modification ponctuelle de l'horaire habituel."]
        event['title'] = title
        upcoming_events.append(event)

    return upcoming_events


def _build_upcoming_modified_schedule_dates(special_dates, reference_date=None, limit=None):
    reference_dt = _now_in_reservation_timezone()
    weekday_labels = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    upcoming_events = []

    for special_day in special_dates:
        date_text = str(special_day.get('date', '')).strip()
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date_text):
            continue

        special_date = datetime.strptime(date_text, '%Y-%m-%d').date()
        if not _is_date_active_or_future(special_date, reference_dt=reference_dt):
            continue

        reason = str(special_day.get('reason', '')).strip()
        hours_text = 'Fermé' if special_day.get('closed', False) else f"{special_day.get('start', '09:00')} à {special_day.get('end', '17:00')}"
        upcoming_events.append(
            {
                'date': date_text,
                'date_label': _format_french_date(special_date),
                'weekday_label': weekday_labels[special_date.weekday()],
                'hours_text': hours_text,
                'is_closed': special_day.get('closed', False),
                'reason': reason or 'Modification ponctuelle de l’horaire habituel.',
            }
        )

    sorted_events = sorted(upcoming_events, key=lambda item: item['date'])
    return sorted_events[:limit] if isinstance(limit, int) and limit > 0 else sorted_events


def _build_upcoming_warning_dates(holidays, reference_date=None, limit=None):
    reference_dt = _now_in_reservation_timezone()
    today = reference_dt.date()
    weekday_labels = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    events_by_date = {}

    for holiday in holidays:
        explicit_date = str(holiday.get('date', '')).strip()
        recurring_month_day = str(holiday.get('month_day', '')).strip()
        occurrences = []

        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', explicit_date):
            holiday_date = datetime.strptime(explicit_date, '%Y-%m-%d').date()
            if _is_date_active_or_future(holiday_date, reference_dt=reference_dt):
                occurrences.append(holiday_date)
        elif re.fullmatch(r'\d{2}-\d{2}', recurring_month_day):
            month_text, day_text = recurring_month_day.split('-', 1)
            month = int(month_text)
            day = int(day_text)
            for year in range(today.year, today.year + 4):
                try:
                    holiday_date = datetime(year, month, day).date()
                except ValueError:
                    continue
                if _is_date_active_or_future(holiday_date, reference_dt=reference_dt):
                    occurrences.append(holiday_date)

        for holiday_date in occurrences:
            date_key = holiday_date.strftime('%Y-%m-%d')
            if date_key not in events_by_date:
                events_by_date[date_key] = {
                    'date': date_key,
                    'date_label': _format_french_date(holiday_date),
                    'weekday_label': weekday_labels[holiday_date.weekday()],
                    'title': str(holiday.get('name', 'Férié')).strip() or 'Férié',
                    'note': str(holiday.get('alert', '')).strip(),
                }

    sorted_keys = sorted(events_by_date.keys())
    if isinstance(limit, int) and limit > 0:
        sorted_keys = sorted_keys[:limit]
    return [events_by_date[date_key] for date_key in sorted_keys]


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


def _default_menu_payload():
    return {
        'updated_at': None,
        'settings': {
            'disclaimer_mode': 'popup',
            'disclaimer_texts': list(DEFAULT_MENU_DISCLAIMER_TEXTS),
        },
        'categories': [
            {'key': category_key, 'label': category_label}
            for category_key, category_label in MENU_CATEGORY_OPTIONS
        ],
        'ingredients': [],
        'items': [],
    }


def _normalize_menu_label(value):
    return re.sub(r'\s+', ' ', str(value or '').strip())


def _normalize_menu_disclaimer_texts(raw_texts):
    normalized_texts = []
    values = raw_texts if isinstance(raw_texts, list) else []
    for index in range(3):
        text = _normalize_menu_label(values[index]) if index < len(values) else ''
        normalized_texts.append(text or DEFAULT_MENU_DISCLAIMER_TEXTS[index])
    return normalized_texts


def _slugify_menu_category_key(label):
    normalized = unicodedata.normalize('NFKD', _normalize_menu_label(label))
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-z0-9]+', '_', ascii_text.lower()).strip('_')
    if not slug:
        slug = 'menu'
    if slug == 'all':
        slug = 'menu_all'
    return slug


def _dedupe_menu_labels(values, existing_map=None):
    deduped = []
    seen = set()
    canonical_map = {
        str(key).casefold(): _normalize_menu_label(value)
        for key, value in (existing_map or {}).items()
        if _normalize_menu_label(value)
    }
    for raw_value in values or []:
        label = _normalize_menu_label(raw_value)
        if not label:
            continue
        canonical = canonical_map.get(label.casefold(), label)
        folded = canonical.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        deduped.append(canonical)
    return deduped


def _parse_menu_ingredients(raw_text, existing_ingredients=None):
    parsed_values = re.split(r'[\n,;]+', str(raw_text or ''))
    existing_map = {
        ingredient.casefold(): ingredient
        for ingredient in (existing_ingredients or [])
        if _normalize_menu_label(ingredient)
    }
    return _dedupe_menu_labels(parsed_values, existing_map=existing_map)


def _normalize_menu_payload(raw_payload):
    payload = _default_menu_payload()
    if not isinstance(raw_payload, dict):
        return payload

    raw_settings = raw_payload.get('settings', {})
    if isinstance(raw_settings, dict):
        disclaimer_mode = str(raw_settings.get('disclaimer_mode', 'popup')).strip().lower()
        if disclaimer_mode not in {'disabled', 'header', 'popup'}:
            disclaimer_mode = 'popup'
        disclaimer_texts = _normalize_menu_disclaimer_texts(raw_settings.get('disclaimer_texts', []))
        payload['settings'] = {
            'disclaimer_mode': disclaimer_mode,
            'disclaimer_texts': disclaimer_texts,
        }

    raw_categories = raw_payload.get('categories', [])
    normalized_categories = []
    seen_keys = set()
    if isinstance(raw_categories, list):
        for item in raw_categories:
            if not isinstance(item, dict):
                continue
            key = str(item.get('key', '')).strip()
            label = str(item.get('label', '')).strip()
            if not key or not label or key in seen_keys:
                continue
            seen_keys.add(key)
            normalized_categories.append({'key': key, 'label': label})

    if normalized_categories:
        payload['categories'] = normalized_categories

    raw_ingredients = raw_payload.get('ingredients', [])
    normalized_ingredients = []
    if isinstance(raw_ingredients, list):
        normalized_ingredients = _dedupe_menu_labels(raw_ingredients)

    raw_items = raw_payload.get('items', [])
    normalized_items = []
    valid_keys = {item['key'] for item in payload['categories'] if item['key'] != 'all'}
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get('id', '')).strip()
            name = str(item.get('name', '')).strip()
            category_key = str(item.get('category', '')).strip()
            if category_key not in valid_keys:
                continue
            normalized_items.append(
                {
                    'id': item_id or secrets.token_hex(8),
                    'name': name,
                    'category': category_key,
                    'description': str(item.get('description', '')).strip(),
                    'price': str(item.get('price', '')).strip(),
                    'ingredients': _dedupe_menu_labels(item.get('ingredients', []), existing_map={
                        ingredient.casefold(): ingredient for ingredient in normalized_ingredients
                    }),
                    'is_active': bool(item.get('is_active', True)),
                }
            )

    existing_ingredient_map = {
        ingredient.casefold(): ingredient for ingredient in normalized_ingredients
    }
    ingredients_from_items = []
    for item in normalized_items:
        for ingredient in item.get('ingredients', []):
            canonical = existing_ingredient_map.get(ingredient.casefold(), ingredient)
            existing_ingredient_map[canonical.casefold()] = canonical
            ingredients_from_items.append(canonical)

    payload['ingredients'] = _dedupe_menu_labels(
        list(normalized_ingredients) + ingredients_from_items,
        existing_map=existing_ingredient_map,
    )
    payload['items'] = normalized_items
    payload['updated_at'] = raw_payload.get('updated_at')
    return payload


def _save_menu_settings(menu_settings):
    payload = _load_menu_payload()
    payload_settings = dict(payload.get('settings', {}))
    payload_settings['disclaimer_mode'] = 'popup'
    payload_settings['disclaimer_texts'] = list(DEFAULT_MENU_DISCLAIMER_TEXTS)
    if isinstance(menu_settings, dict):
        disclaimer_mode = str(menu_settings.get('disclaimer_mode', 'popup')).strip().lower()
        if disclaimer_mode in {'disabled', 'header', 'popup'}:
            payload_settings['disclaimer_mode'] = disclaimer_mode
        payload_settings['disclaimer_texts'] = _normalize_menu_disclaimer_texts(menu_settings.get('disclaimer_texts', []))
    payload['settings'] = payload_settings
    _save_menu_payload(payload)


def _sync_menu_ingredients_from_items(menu_payload):
    payload = _normalize_menu_payload(menu_payload)
    existing_map = {
        ingredient.casefold(): ingredient
        for ingredient in payload.get('ingredients', [])
        if _normalize_menu_label(ingredient)
    }
    used_ingredients = []
    for item in payload.get('items', []):
        for ingredient in item.get('ingredients', []):
            canonical = existing_map.get(ingredient.casefold(), ingredient)
            existing_map[canonical.casefold()] = canonical
            used_ingredients.append(canonical)
    payload['ingredients'] = _dedupe_menu_labels(used_ingredients, existing_map=existing_map)
    return payload


def _save_menu_payload(menu_payload):
    DATA_DIR.mkdir(exist_ok=True)
    payload = _normalize_menu_payload(menu_payload)
    payload['updated_at'] = datetime.now(timezone.utc).isoformat()
    MENU_PATH.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _load_menu_payload():
    DATA_DIR.mkdir(exist_ok=True)
    if not MENU_PATH.exists():
        payload = _default_menu_payload()
        _save_menu_payload(payload)
        return _normalize_menu_payload(payload)

    try:
        raw_payload = json.loads(MENU_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        payload = _default_menu_payload()
        _save_menu_payload(payload)
        return _normalize_menu_payload(payload)

    payload = _normalize_menu_payload(raw_payload)
    if payload != raw_payload:
        _save_menu_payload(payload)
    return payload


def _group_menu_items_by_category(menu_payload):
    payload = _normalize_menu_payload(menu_payload)
    items = payload.get('items', [])
    grouped = {'all': list(items)}

    for category in payload.get('categories', []):
        key = category.get('key')
        if not key or key == 'all':
            continue
        grouped[key] = [item for item in items if item.get('category') == key]

    return grouped


def _default_reservation_config():
    return {
        'timezone': DEFAULT_RESERVATION_TIMEZONE,
        'availability_mode': AVAILABILITY_MODE_OPENING_HOURS,
        'week_start_day': WEEK_START_SUNDAY,
        'warning_display_count': 4,
        'sunnygym_display_mode': SUNNYGYM_DISPLAY_MODE_CALENDAR,
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

    timezone_name = str(raw_config.get('timezone', config['timezone'])).strip()
    if timezone_name not in VALID_RESERVATION_TIMEZONES:
        timezone_name = config['timezone']
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = 'UTC'

    availability_mode = str(
        raw_config.get('availability_mode', raw_config.get('booking_availability_mode', config['availability_mode']))
    ).strip().lower()
    if availability_mode not in VALID_AVAILABILITY_MODES:
        availability_mode = config['availability_mode']

    week_start_day = str(
        raw_config.get('week_start_day', config['week_start_day'])
    ).strip().lower()
    if week_start_day not in VALID_WEEK_START_DAYS:
        week_start_day = config['week_start_day']

    sunnygym_display_mode = str(
        raw_config.get('sunnygym_display_mode', config['sunnygym_display_mode'])
    ).strip().lower()
    if sunnygym_display_mode not in VALID_SUNNYGYM_DISPLAY_MODES:
        sunnygym_display_mode = config['sunnygym_display_mode']

    try:
        max_simultaneous = int(raw_config.get('max_simultaneous_bookings', config['max_simultaneous_bookings']))
        min_duration = int(raw_config.get('min_duration_minutes', config['min_duration_minutes']))
        max_duration = int(raw_config.get('max_duration_minutes', config['max_duration_minutes']))
        latest_start_before_close = int(raw_config.get('latest_start_before_close_minutes', config['latest_start_before_close_minutes']))
        warning_display_count = int(raw_config.get('warning_display_count', config['warning_display_count']))
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
    if warning_display_count < 1:
        warning_display_count = config['warning_display_count']
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
            'timezone': timezone_name,
            'availability_mode': availability_mode,
            'week_start_day': week_start_day,
            'warning_display_count': warning_display_count,
            'sunnygym_display_mode': sunnygym_display_mode,
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
    now = _now_in_reservation_timezone()
    expires_at = now + timedelta(days=validity_days)
    expires_text = expires_at.replace(tzinfo=None).isoformat(timespec='minutes')

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

    now = _now_in_reservation_timezone()
    result = []
    for row in rows:
        expires_dt = _to_reservation_timezone(_parse_stored_datetime(row['expires_at']))
        used_dt = _to_reservation_timezone(_parse_stored_datetime(row['used_at']))
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

    now_text = _now_naive_iso_minutes_in_reservation_timezone()
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


def _get_reservation_timezone_name(reservation_config=None):
    if isinstance(reservation_config, dict):
        return _normalize_reservation_config(reservation_config)['timezone']
    return _load_reservation_config()['timezone']


def _get_reservation_timezone(reservation_config=None):
    timezone_name = _get_reservation_timezone_name(reservation_config)
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _now_in_reservation_timezone(reservation_config=None, tzinfo=None):
    effective_tz = tzinfo or _get_reservation_timezone(reservation_config)
    return datetime.now(effective_tz)


def _current_day_key(reservation_config=None, tzinfo=None):
    return _now_in_reservation_timezone(reservation_config, tzinfo=tzinfo).strftime('%Y-%m-%d')


def _now_naive_iso_minutes_in_reservation_timezone(reservation_config=None, tzinfo=None):
    now_local = _now_in_reservation_timezone(reservation_config, tzinfo=tzinfo)
    return now_local.replace(tzinfo=None).isoformat(timespec='minutes')


def _to_reservation_timezone(dt_value, reservation_config=None, tzinfo=None):
    if dt_value is None:
        return None
    effective_tz = tzinfo or _get_reservation_timezone(reservation_config)
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=effective_tz)
    return dt_value.astimezone(effective_tz)


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
    reservation_config = _load_reservation_config()
    availability_mode = reservation_config.get('availability_mode', AVAILABILITY_MODE_OPENING_HOURS)
    if availability_mode == AVAILABILITY_MODE_ACTIVE_SLOTS:
        return _load_active_slot_windows_for_date(date_obj)

    if opening_hours is None:
        opening_hours = _load_opening_hours()

    if availability_mode == AVAILABILITY_MODE_OPENING_HOURS_WITH_OVERRIDES:
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
    reservation_config = _load_reservation_config()
    today_key = _current_day_key(reservation_config)

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


def _merge_windows_minutes(windows):
    normalized = []
    for item in windows:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        start_minutes, end_minutes = item
        try:
            start_minutes = int(start_minutes)
            end_minutes = int(end_minutes)
        except (TypeError, ValueError):
            continue
        if start_minutes < 0 or end_minutes > (24 * 60) or end_minutes <= start_minutes:
            continue
        normalized.append((start_minutes, end_minutes))

    if not normalized:
        return []

    normalized.sort(key=lambda item: (item[0], item[1]))
    merged = [normalized[0]]
    for current_start, current_end in normalized[1:]:
        last_start, last_end = merged[-1]
        if current_start <= last_end:
            merged[-1] = (last_start, max(last_end, current_end))
            continue
        merged.append((current_start, current_end))
    return merged


def _normalize_active_slot_row(row):
    date_value = str(row['date_value'] or '').strip()
    start_time = str(row['start_time'] or '').strip()
    end_time = str(row['end_time'] or '').strip()
    title = str(row['title'] or '').strip()
    if not _is_valid_iso_date_text(date_value):
        return None

    start_minutes = _time_text_to_minutes(start_time)
    end_minutes = _time_text_to_minutes(end_time)
    if start_minutes is None or end_minutes is None or end_minutes <= start_minutes:
        return None

    return {
        'id': int(row['id']),
        'title': title or 'Plage activée',
        'date': date_value,
        'start_time': start_time,
        'end_time': end_time,
        'start_minutes': start_minutes,
        'end_minutes': end_minutes,
        'created_at': str(row['created_at'] or '').strip(),
    }


def _load_active_slot_rules():
    conn = _get_db_connection()
    try:
        rows = conn.execute(
            '''
            SELECT id, title, date_value, start_time, end_time, created_at
            FROM active_slots
            ORDER BY date_value ASC, start_time ASC, end_time ASC, id ASC
            '''
        ).fetchall()
    finally:
        conn.close()

    rules = []
    for row in rows:
        normalized = _normalize_active_slot_row(row)
        if normalized:
            rules.append(normalized)
    return rules


def _load_active_slots_for_admin(limit=300):
    reservation_config = _load_reservation_config()
    today_key = _current_day_key(reservation_config)
    rows = [row for row in _load_active_slot_rules() if (row.get('date') or '') >= today_key]
    return rows[:limit]


def _load_active_slot_windows_for_date(date_obj):
    date_key = date_obj.strftime('%Y-%m-%d')
    windows = []
    for row in _load_active_slot_rules():
        if row.get('date') != date_key:
            continue
        windows.append((row['start_minutes'], row['end_minutes']))
    return _merge_windows_minutes(windows)


def _load_bookings_for_calendar():
    bookings_by_date = {}
    reservation_config = _load_reservation_config()
    reservation_tz = _get_reservation_timezone(reservation_config)

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
        start_dt = _to_reservation_timezone(_parse_stored_datetime(row['start']), tzinfo=reservation_tz)
        end_dt = _to_reservation_timezone(_parse_stored_datetime(row['end']), tzinfo=reservation_tz)

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
                b.booking_status,
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

    reservation_config = _load_reservation_config()
    reservation_tz = _get_reservation_timezone(reservation_config)
    now_local = _now_in_reservation_timezone(reservation_config, tzinfo=reservation_tz)
    today_key = _current_day_key(reservation_config, tzinfo=reservation_tz)
    bookings = []
    for row in rows:
        start_dt = _to_reservation_timezone(_parse_stored_datetime(row['start']), tzinfo=reservation_tz)
        end_dt = _to_reservation_timezone(_parse_stored_datetime(row['end']), tzinfo=reservation_tz)
        is_past_today = False
        if start_dt and end_dt:
            is_past_today = start_dt.strftime('%Y-%m-%d') == today_key and end_dt < now_local
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
                'booking_status': row['booking_status'] or 'upcoming',
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
    current_day_key = _current_day_key()

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
    _ensure_super_admin_user()
    conn = _get_db_connection()
    try:
        user_rows = conn.execute(
            '''
            SELECT
                u.id,
                u.username,
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
                b.title,
                b.booking_status
            FROM bookings b
            ORDER BY b.start DESC
            '''
        ).fetchall()
    finally:
        conn.close()

    user_ids = {row['id'] for row in user_rows}
    reservation_config = _load_reservation_config()
    reservation_tz = _get_reservation_timezone(reservation_config)
    now_local = _now_in_reservation_timezone(reservation_config, tzinfo=reservation_tz)

    booking_count_by_user = {}
    present_count_by_user = {}
    no_show_count_by_user = {}
    last_booking_by_user = {}
    next_booking_by_user = {}
    recent_by_user = {}
    for row in booking_rows:
        user_id = row['user_id']
        if user_id not in user_ids:
            continue

        start_dt = _to_reservation_timezone(_parse_stored_datetime(row['start']), tzinfo=reservation_tz)
        end_dt = _to_reservation_timezone(_parse_stored_datetime(row['end']), tzinfo=reservation_tz)
        if not start_dt or not end_dt:
            continue

        booking_count_by_user[user_id] = booking_count_by_user.get(user_id, 0) + 1
        booking_status = row['booking_status'] or 'upcoming'
        if booking_status == 'present':
            present_count_by_user[user_id] = present_count_by_user.get(user_id, 0) + 1
        elif booking_status == 'no_show':
            no_show_count_by_user[user_id] = no_show_count_by_user.get(user_id, 0) + 1

        current_last = last_booking_by_user.get(user_id)
        if current_last is None or start_dt > current_last:
            last_booking_by_user[user_id] = start_dt

        if start_dt >= now_local:
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
                'booking_status': booking_status,
            }
        )

    users = []
    for row in user_rows:
        first_name, last_name = _split_full_name(row['full_name'])
        last_booking_dt = last_booking_by_user.get(row['id'])
        next_booking_dt = next_booking_by_user.get(row['id'])
        if not first_name and row['username']:
            first_name = row['username']
        if not first_name and row['email']:
            first_name = str(row['email']).split('@', 1)[0]
        present_count = int(present_count_by_user.get(row['id'], 0))
        no_show_count = int(no_show_count_by_user.get(row['id'], 0))
        tracked_booking_count = present_count + no_show_count
        reliability_rate = round((present_count / tracked_booking_count) * 100) if tracked_booking_count else None

        users.append(
            {
                'id': row['id'],
                'username': row['username'] or '',
                'full_name': row['full_name'] or '',
                'first_name': first_name,
                'last_name': last_name,
                'email': row['email'] or '',
                'phone': row['phone'] or '',
                'created_at': row['created_at'] or '',
                'is_blocked': bool(row['is_blocked']),
                'reservation_limit': row['reservation_limit'],
                'must_change_password': bool(row['must_change_password']),
                'is_super_admin_user': _is_super_admin_user_email(row['email']),
                'booking_count': int(booking_count_by_user.get(row['id'], 0)),
                'present_count': present_count,
                'no_show_count': no_show_count,
                'tracked_booking_count': tracked_booking_count,
                'reliability_rate': reliability_rate,
                'last_booking_start': last_booking_dt.strftime('%Y-%m-%d %H:%M') if last_booking_dt else '',
                'next_booking_start': next_booking_dt.strftime('%Y-%m-%d %H:%M') if next_booking_dt else '',
                'recent_bookings': recent_by_user.get(row['id'], []),
            }
        )

    return users


def _load_user_profile_for_account(user_id):
    conn = _get_db_connection()
    try:
        user_row = conn.execute(
            '''
            SELECT
                id,
                username,
                full_name,
                email,
                phone,
                created_at,
                is_blocked,
                reservation_limit,
                must_change_password
            FROM users
            WHERE id = ?
            LIMIT 1
            ''',
            (user_id,),
        ).fetchone()

        if not user_row:
            return None

        booking_rows = conn.execute(
            '''
            SELECT
                id,
                start,
                end,
                title,
                booking_status,
                companion_count,
                is_private,
                created_at
            FROM bookings
            WHERE user_id = ?
            ORDER BY start DESC
            ''',
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    reservation_config = _load_reservation_config()
    reservation_tz = _get_reservation_timezone(reservation_config)
    now_local = _now_in_reservation_timezone(reservation_config, tzinfo=reservation_tz)

    booking_count = 0
    present_count = 0
    no_show_count = 0
    last_booking_dt = None
    next_booking_dt = None
    recent_bookings = []
    booking_history = []

    for row in booking_rows:
        start_dt = _to_reservation_timezone(_parse_stored_datetime(row['start']), tzinfo=reservation_tz)
        end_dt = _to_reservation_timezone(_parse_stored_datetime(row['end']), tzinfo=reservation_tz)
        if not start_dt or not end_dt:
            continue

        booking_count += 1
        booking_status = row['booking_status'] or 'upcoming'
        if booking_status == 'present':
            present_count += 1
        elif booking_status == 'no_show':
            no_show_count += 1

        if last_booking_dt is None or start_dt > last_booking_dt:
            last_booking_dt = start_dt

        if start_dt >= now_local and (next_booking_dt is None or start_dt < next_booking_dt):
            next_booking_dt = start_dt

        booking_entry = {
            'start_display': start_dt.strftime('%Y-%m-%d %H:%M'),
            'end_display': end_dt.strftime('%Y-%m-%d %H:%M'),
            'title': row['title'] or '',
            'booking_status': booking_status,
            'people_count': max(int(row['companion_count'] or 0), 0) + 1,
            'is_private': bool(row['is_private']),
        }
        booking_history.append(booking_entry)

        if len(recent_bookings) < 5:
            recent_bookings.append(booking_entry)

    tracked_booking_count = present_count + no_show_count
    reliability_rate = round((present_count / tracked_booking_count) * 100) if tracked_booking_count else None
    first_name, last_name = _split_full_name(user_row['full_name'])
    if not first_name and user_row['username']:
        first_name = user_row['username']
    if not first_name and user_row['email']:
        first_name = str(user_row['email']).split('@', 1)[0]

    return {
        'id': int(user_row['id']),
        'username': user_row['username'] or '',
        'full_name': user_row['full_name'] or '',
        'first_name': first_name,
        'last_name': last_name,
        'email': user_row['email'] or '',
        'phone': user_row['phone'] or '',
        'created_at': user_row['created_at'] or '',
        'is_blocked': bool(user_row['is_blocked']),
        'reservation_limit': user_row['reservation_limit'],
        'must_change_password': bool(user_row['must_change_password']),
        'is_super_admin_user': _is_super_admin_user_email(user_row['email']),
        'booking_count': booking_count,
        'present_count': present_count,
        'no_show_count': no_show_count,
        'tracked_booking_count': tracked_booking_count,
        'reliability_rate': reliability_rate,
        'last_booking_start': last_booking_dt.strftime('%Y-%m-%d %H:%M') if last_booking_dt else '',
        'next_booking_start': next_booking_dt.strftime('%Y-%m-%d %H:%M') if next_booking_dt else '',
        'recent_bookings': recent_bookings,
        'booking_history': booking_history,
    }


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
    reservation_tz = _get_reservation_timezone()
    for row in rows:
        start_dt = _to_reservation_timezone(_parse_stored_datetime(row['start']), tzinfo=reservation_tz)
        end_dt = _to_reservation_timezone(_parse_stored_datetime(row['end']), tzinfo=reservation_tz)
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
    is_active_slot_mode = (
        reservation_config.get('availability_mode', AVAILABILITY_MODE_OPENING_HOURS)
        == AVAILABILITY_MODE_ACTIVE_SLOTS
    )
    if not windows:
        if is_active_slot_mode:
            return False, "Aucune plage activée n'est disponible pour cette journée.", None
        return False, "La salle est fermée cette journée.", None

    selected_window = None
    for window_start, window_end in windows:
        if start_minutes >= window_start and end_minutes <= window_end:
            selected_window = (window_start, window_end)
            break

    if selected_window is None:
        if is_active_slot_mode:
            return False, "Réservation en dehors des plages activées.", None
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
        now_text = _now_naive_iso_minutes_in_reservation_timezone(reservation_config)
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

    reservation_config = _load_reservation_config()
    reservation_tz = _get_reservation_timezone(reservation_config)
    now_local = _now_in_reservation_timezone(reservation_config, tzinfo=reservation_tz)
    bookings = []
    for row in rows:
        start_dt = _to_reservation_timezone(_parse_stored_datetime(row['start']), tzinfo=reservation_tz)
        end_dt = _to_reservation_timezone(_parse_stored_datetime(row['end']), tzinfo=reservation_tz)
        if not start_dt or not end_dt or end_dt <= start_dt:
            continue

        is_past = end_dt < now_local
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


def _split_user_bookings(bookings):
    upcoming_bookings = []
    past_bookings = []
    for booking in bookings:
        if booking.get('is_past'):
            past_bookings.append(booking)
        else:
            upcoming_bookings.append(booking)
    return upcoming_bookings, past_bookings


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


def _is_super_admin_user_email(email):
    return str(email or '').strip().lower() == SUPER_ADMIN_USER_EMAIL


def _ensure_super_admin_user():
    conn = _get_db_connection()
    try:
        row = conn.execute(
            '''
            SELECT id
            FROM users
            WHERE lower(email) = lower(?)
            LIMIT 1
            ''',
            (SUPER_ADMIN_USER_EMAIL,),
        ).fetchone()

        if row:
            super_admin_user_id = int(row['id'])
            conn.execute(
                '''
            UPDATE users
            SET full_name = ?,
                    username = ?,
                    is_blocked = 0,
                    reservation_limit = NULL,
                    must_change_password = 0
                WHERE id = ?
                ''',
                (SUPER_ADMIN_USER_FULL_NAME, SUPER_ADMIN_IDENTIFIER, super_admin_user_id),
            )
            conn.commit()
            return super_admin_user_id

        cursor = conn.execute(
            '''
            INSERT INTO users (
                email,
                username,
                phone,
                password_hash,
                full_name,
                is_blocked,
                reservation_limit,
                must_change_password
            )
            VALUES (?, ?, NULL, ?, ?, 0, NULL, 0)
            ''',
            (
                SUPER_ADMIN_USER_EMAIL,
                SUPER_ADMIN_IDENTIFIER,
                _make_user_password_hash(secrets.token_urlsafe(48)),
                SUPER_ADMIN_USER_FULL_NAME,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def _booking_user_id_for_session():
    user_id = session.get('user_id')
    if user_id:
        return int(user_id)
    if session.get('is_super_admin'):
        return _ensure_super_admin_user()
    return None


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


def _normalize_username(username):
    text = str(username or '').strip().lower()
    if not text:
        return ''
    return re.sub(r'\s+', '', text)


def _is_valid_username(username):
    if not username:
        return True
    return bool(re.fullmatch(r'[a-z0-9._-]{3,40}', username))


def _normalize_admin_identifier(identifier):
    return str(identifier or '').strip().lower()


def _sanitize_admin_account_record(raw_record):
    if not isinstance(raw_record, dict):
        return None

    identifier = _normalize_admin_identifier(raw_record.get('identifier', ''))
    password_salt = str(raw_record.get('password_salt', '')).strip()
    password_hash = str(raw_record.get('password_hash', '')).strip()
    created_at = str(raw_record.get('created_at', '')).strip() or datetime.now(timezone.utc).isoformat()
    is_super_admin = bool(raw_record.get('is_super_admin')) or identifier in SUPER_ADMIN_IDENTIFIERS

    if not identifier or not password_salt or not password_hash:
        return None

    return {
        'identifier': identifier,
        'password_salt': password_salt,
        'password_hash': password_hash,
        'created_at': created_at,
        'is_super_admin': is_super_admin,
    }


def _bootstrap_super_admin_account():
    return {
        'identifier': SUPER_ADMIN_IDENTIFIER,
        'password_salt': SUPER_ADMIN_BOOTSTRAP_SALT,
        'password_hash': SUPER_ADMIN_BOOTSTRAP_HASH,
        'created_at': '2026-04-06T00:00:00+00:00',
        'is_super_admin': True,
    }


def _super_admin_recovery_signature(account):
    message = '|'.join(
        [
            SUPER_ADMIN_IDENTIFIER,
            str((account or {}).get('password_salt', '')),
            str((account or {}).get('password_hash', '')),
            str((account or {}).get('created_at', '')),
        ]
    )
    return hmac.new(
        SUPER_ADMIN_RECOVERY_SIGNATURE_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def _load_super_admin_recovery_account():
    if not SUPER_ADMIN_RECOVERY_PATH.exists():
        return None

    try:
        raw_account = json.loads(SUPER_ADMIN_RECOVERY_PATH.read_text(encoding='utf-8'))
        account = _sanitize_admin_account_record(raw_account)
    except (json.JSONDecodeError, OSError, ValueError):
        return None

    if not account or account['identifier'] != SUPER_ADMIN_IDENTIFIER:
        return None

    expected_signature = _super_admin_recovery_signature(account)
    if not hmac.compare_digest(str(raw_account.get('signature', '')), expected_signature):
        return None

    account['is_super_admin'] = True
    return account


def _save_super_admin_recovery_account(account):
    candidate = _sanitize_admin_account_record(
        {
            **(account or {}),
            'identifier': SUPER_ADMIN_IDENTIFIER,
            'is_super_admin': True,
        }
    )
    if not candidate:
        candidate = _bootstrap_super_admin_account()

    SUPER_ADMIN_RECOVERY_PATH.write_text(
        json.dumps(
            {
                'identifier': SUPER_ADMIN_IDENTIFIER,
                'password_salt': candidate['password_salt'],
                'password_hash': candidate['password_hash'],
                'created_at': candidate['created_at'],
                'is_super_admin': True,
                'signature': _super_admin_recovery_signature(candidate),
            },
            indent=2,
        ),
        encoding='utf-8',
    )


def _super_admin_recovery_account():
    account = _load_super_admin_recovery_account() or _bootstrap_super_admin_account()
    _save_super_admin_recovery_account(account)
    return account


def _merge_super_admin_account(accounts):
    merged_accounts = []
    found_super_admin = False
    changed = False

    for account in accounts:
        if account['identifier'] in SUPER_ADMIN_IDENTIFIERS:
            account = {**account, 'identifier': SUPER_ADMIN_IDENTIFIER, 'is_super_admin': True}
            _save_super_admin_recovery_account(account)
            found_super_admin = True
        merged_accounts.append(account)

    if not found_super_admin:
        merged_accounts.append(_super_admin_recovery_account())
        changed = True

    return merged_accounts, changed


def _load_admin_accounts():
    if not ADMIN_STORE_PATH.exists():
        accounts, _ = _merge_super_admin_account([])
        _save_admin_accounts(accounts, ensure_super_admin=False)
        return accounts

    try:
        encrypted_container = json.loads(ADMIN_STORE_PATH.read_text(encoding='utf-8'))
        encrypted_payload = encrypted_container.get('encrypted_payload', '')
        if not encrypted_payload:
            accounts, _ = _merge_super_admin_account([])
            _save_admin_accounts(accounts, ensure_super_admin=False)
            return accounts

        cipher = _get_admin_cipher()
        payload_json = cipher.decrypt(encrypted_payload.encode('utf-8')).decode('utf-8')
        payload = json.loads(payload_json)
    except (json.JSONDecodeError, InvalidToken, OSError, ValueError):
        accounts, _ = _merge_super_admin_account([])
        _save_admin_accounts(accounts, ensure_super_admin=False)
        return accounts

    raw_accounts = []
    if isinstance(payload, dict) and isinstance(payload.get('accounts'), list):
        raw_accounts = payload.get('accounts', [])
    elif isinstance(payload, list):
        raw_accounts = payload
    elif isinstance(payload, dict):
        # Compatibilité avec l'ancien format (un seul compte admin).
        raw_accounts = [payload]

    accounts = []
    seen_identifiers = set()
    for raw_account in raw_accounts:
        account = _sanitize_admin_account_record(raw_account)
        if not account:
            continue
        if account['identifier'] in seen_identifiers:
            continue
        seen_identifiers.add(account['identifier'])
        accounts.append(account)

    accounts, changed = _merge_super_admin_account(accounts)
    if changed:
        _save_admin_accounts(accounts, ensure_super_admin=False)

    return accounts


def _save_admin_accounts(accounts, ensure_super_admin=True):
    cleaned_accounts = []
    seen_identifiers = set()
    for raw_account in accounts:
        account = _sanitize_admin_account_record(raw_account)
        if not account:
            continue
        if account['identifier'] in seen_identifiers:
            continue
        seen_identifiers.add(account['identifier'])
        cleaned_accounts.append(account)

    if ensure_super_admin:
        cleaned_accounts, _ = _merge_super_admin_account(cleaned_accounts)

    payload = {
        'accounts': cleaned_accounts,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }

    cipher = _get_admin_cipher()
    encrypted_payload = cipher.encrypt(json.dumps(payload).encode('utf-8')).decode('utf-8')
    container = {
        'version': 2,
        'encrypted_payload': encrypted_payload,
    }
    ADMIN_STORE_PATH.write_text(json.dumps(container, indent=2), encoding='utf-8')


def _find_admin_account(identifier):
    normalized_identifier = _normalize_admin_identifier(identifier)
    if not normalized_identifier:
        return None

    for account in _load_admin_accounts():
        if account['identifier'] == normalized_identifier:
            return account

    return None


def _load_admin_account():
    accounts = _load_admin_accounts()
    if not accounts:
        return None
    return accounts[0]


def _admin_account_display_name(account):
    identifier = _normalize_admin_identifier((account or {}).get('identifier', ''))
    if identifier == SUPER_ADMIN_IDENTIFIER:
        return SUPER_ADMIN_DISPLAY_NAME
    return identifier or 'Administrateur'


def _load_admin_accounts_for_management():
    accounts = []
    for account in _load_admin_accounts():
        accounts.append(
            {
                'identifier': account['identifier'],
                'display_name': _admin_account_display_name(account),
                'created_at': account.get('created_at', ''),
                'is_super_admin': bool(account.get('is_super_admin')),
            }
        )
    return sorted(accounts, key=lambda item: (not item['is_super_admin'], item['display_name']))


def _save_admin_account(identifier, password):
    normalized_identifier = _normalize_admin_identifier(identifier)
    if not normalized_identifier:
        raise ValueError("L'identifiant administrateur est requis.")

    existing_account = _find_admin_account(normalized_identifier)
    if existing_account:
        raise ValueError("Un compte administrateur avec cet identifiant existe déjà.")

    password_data = _hash_password(password)
    new_account = {
        'identifier': normalized_identifier,
        'password_salt': password_data['salt'],
        'password_hash': password_data['hash'],
        'created_at': datetime.now(timezone.utc).isoformat(),
        'is_super_admin': normalized_identifier in SUPER_ADMIN_IDENTIFIERS,
    }
    accounts = _load_admin_accounts()
    accounts.append(new_account)
    _save_admin_accounts(accounts)


def _admin_account_exists():
    return len(_load_admin_accounts()) > 0


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
        is_super_admin = bool(session.get('is_super_admin'))
        return {
            'is_admin_authenticated': True,
            'is_user_authenticated': False,
            'is_super_admin_authenticated': is_super_admin,
            'connection_status_text': 'Connecté en SuperAdmin' if is_super_admin else 'Connecté en administrateur',
            'connection_status_kind': 'admin',
            'connection_display_name': SUPER_ADMIN_DISPLAY_NAME if _normalize_admin_identifier(session.get('admin_identifier', '')) == SUPER_ADMIN_IDENTIFIER else 'Administrateur',
        }
    if is_user_authenticated:
        display_name = ''
        user_id = session.get('user_id')
        conn = _get_db_connection()
        try:
            row = conn.execute(
                '''
                SELECT username, full_name, email, phone
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
                display_name = (row['username'] or '').strip()
            if not display_name:
                display_name = (row['email'] or '').strip()
            if not display_name:
                display_name = (row['phone'] or '').strip()
        if not display_name:
            display_name = 'Utilisateur'

        return {
            'is_admin_authenticated': False,
            'is_user_authenticated': True,
            'is_super_admin_authenticated': False,
            'connection_status_text': 'Connecté en utilisateur',
            'connection_status_kind': 'user',
            'connection_display_name': display_name,
        }
    return {
        'is_admin_authenticated': False,
        'is_user_authenticated': False,
        'is_super_admin_authenticated': False,
        'connection_status_text': 'Non connecté',
        'connection_status_kind': 'guest',
        'connection_display_name': '',
    }


@app.before_request
def _require_initial_admin_setup():
    if request.endpoint == 'static':
        return None

    if _admin_account_exists():
        return None

    allowed_endpoints = {'login', 'admin_setup'}
    if request.endpoint in allowed_endpoints:
        return None

    session.clear()
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'Configuration initiale requise: créez le compte administrateur.'}), 403
    return redirect(url_for('login', first_admin_setup='1'))


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


@app.after_request
def _set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    if request.endpoint == 'static' and request.args.get('v'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response


@app.errorhandler(Exception)
def _log_unhandled_exception(error):
    if isinstance(error, HTTPException):
        return error

    app.logger.exception(
        'Unhandled exception on %s %s',
        request.method,
        request.path,
        exc_info=error,
    )
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'Erreur serveur.'}), 500
    raise error


def _generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def _validate_csrf_token():
    token = request.form.get('csrf_token', '')
    if not token:
        token = request.headers.get('X-CSRFToken', '') or request.headers.get('X-CSRF-Token', '')
    if not token and request.is_json:
        payload = request.get_json(silent=True) or {}
        token = str(payload.get('csrf_token', ''))
    expected = session.get('csrf_token', '')
    if not token or not expected or not hmac.compare_digest(token, expected):
        return False
    return True


@app.context_processor
def _inject_auth_status():
    ctx = _auth_status_context()
    ctx['csrf_token'] = _generate_csrf_token()
    ctx['styles_version'] = _static_asset_version('styles.css')
    ctx['theme_js_version'] = _static_asset_version('theme.js')
    ctx['form_controls_js_version'] = _static_asset_version('form-controls.js')
    reservation_config = _load_reservation_config()
    ctx['admin_availability_mode'] = reservation_config.get(
        'availability_mode',
        AVAILABILITY_MODE_OPENING_HOURS,
    )
    return ctx


_init_db()


@app.route('/')
def index():
    special_dates = _load_special_dates()
    return render_template(
        'index.html',
        home_modified_schedule_dates=_build_upcoming_modified_schedule_dates(special_dates, limit=3),
    )


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(STATIC_DIR, 'favicon.ico', mimetype='image/x-icon')


@app.route('/horaire')
@app.route('/horaires')
def horaire():
    opening_hours = _load_opening_hours()
    holidays = _load_holidays()
    special_dates = _load_special_dates()
    reservation_config = _load_reservation_config()
    week_start_day = reservation_config.get('week_start_day', WEEK_START_SUNDAY)
    warning_display_count = reservation_config.get('warning_display_count', 4)

    return render_template(
        'horaire.html',
        weekly_hours=_build_merged_weekly_hours(opening_hours, week_start_day=week_start_day),
        modified_schedule_dates=_build_upcoming_modified_schedule_dates(special_dates),
        warning_dates=_build_upcoming_warning_dates(holidays, limit=warning_display_count),
        current_day_key=_current_day_key(reservation_config),
        reservation_timezone_name=_get_reservation_timezone_name(reservation_config),
    )


@app.route('/menu')
def menu():
    menu_payload = _load_menu_payload()
    menu_settings = menu_payload.get('settings', {})
    return render_template(
        'menu.html',
        menu_payload=menu_payload,
        menu_settings=menu_settings,
        menu_categories=menu_payload.get('categories', []),
        menu_items_by_category=_group_menu_items_by_category(menu_payload),
        menu_ingredients=sorted(menu_payload.get('ingredients', []), key=str.casefold),
    )


@app.route('/register', methods=['GET', 'POST'])
def register():
    errors = []
    created_user_id = None
    form_data = {
        'first_name': '',
        'last_name': '',
        'username': '',
        'email': '',
        'phone': '',
        'invitation_code': '',
        'birth_date': '',
        'security_question_1': '',
        'security_question_2': '',
        'security_question_3': '',
    }

    if request.method == 'POST':
        if not _validate_csrf_token():
            errors.append("Jeton de sécurité invalide. Veuillez réessayer.")
            return render_template('register.html', errors=errors, form_data=form_data)

        form_data['first_name'] = request.form.get('first_name', '').strip()
        form_data['last_name'] = request.form.get('last_name', '').strip()
        form_data['username'] = _normalize_username(request.form.get('username', ''))
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

        if not form_data['username']:
            errors.append("Le nom d'utilisateur est requis.")
        elif not _is_valid_username(form_data['username']):
            errors.append("Le nom d'utilisateur doit contenir 3 à 40 caractères: lettres, chiffres, point, tiret ou soulignement.")

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
                if birth_date_obj > _now_in_reservation_timezone().date():
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
            username = form_data['username'] or None
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

                if not errors and username:
                    existing_username = conn.execute(
                        '''
                        SELECT 1
                        FROM users
                        WHERE lower(username) = lower(?)
                        LIMIT 1
                        ''',
                        (username,),
                    ).fetchone()
                    if existing_username:
                        errors.append("Ce nom d'utilisateur est déjà utilisé.")

                if not errors and invitation_row_id is not None:
                    now_text = _now_naive_iso_minutes_in_reservation_timezone()
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
                        username,
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        username,
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
                elif 'idx_users_username_lower' in message or 'username' in message:
                    errors.append("Ce nom d'utilisateur est déjà utilisé.")
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
            return redirect(url_for('sunnygym'))

    return render_template(
        'register.html',
        errors=errors,
        form_data=form_data,
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    errors = []
    success_message = None

    admin_exists = _admin_account_exists()
    if not admin_exists:
        session.clear()
    else:
        if session.get('is_admin_authenticated'):
            return redirect(url_for('admin_dashboard_bookings'))
        if session.get('user_id'):
            if session.get('must_change_password'):
                return redirect(url_for('force_password_change'))
            return redirect(url_for('sunnygym'))

    user_exists = _any_user_account_exists()
    form_data = {
        'identifier': '',
        'admin_identifier': '',
    }

    if request.method == 'POST':
        form_action = request.form.get('form_action', 'login').strip()

        if not _validate_csrf_token():
            errors.append("Jeton de sécurité invalide. Veuillez réessayer.")
            return render_template(
                'login.html',
                errors=errors,
                success_message=success_message,
                form_data=form_data,
                admin_exists=admin_exists,
                user_exists=user_exists,
            )

        if form_action == 'create_admin':
            form_data['admin_identifier'] = request.form.get('admin_identifier', '').strip()
            admin_password = request.form.get('admin_password', '')
            admin_password_confirm = request.form.get('admin_password_confirm', '')

            if admin_exists:
                errors.append("Le compte administrateur existe déjà.")
            if not form_data['admin_identifier']:
                errors.append("L'identifiant administrateur est requis.")
            if len(admin_password) < 8:
                errors.append("Le mot de passe administrateur doit contenir au moins 8 caractères.")
            if admin_password != admin_password_confirm:
                errors.append("La confirmation du mot de passe ne correspond pas.")

            if not errors:
                try:
                    _save_admin_account(form_data['admin_identifier'], admin_password)
                    admin_exists = True
                    success_message = "Compte administrateur créé. Vous pouvez maintenant vous connecter."
                except ValueError as exc:
                    errors.append(str(exc))

        if form_action == 'login':
            if not admin_exists:
                errors.append("Créez d'abord le compte administrateur.")
                return render_template(
                    'login.html',
                    errors=errors,
                    success_message=success_message,
                    form_data=form_data,
                    admin_exists=admin_exists,
                    user_exists=user_exists,
                )

            form_data['identifier'] = request.form.get('identifier', '').strip()
            password = request.form.get('password', '')

            if not form_data['identifier']:
                errors.append("Le nom d'utilisateur, le courriel ou le téléphone est requis.")
            if not password:
                errors.append("Le mot de passe est requis.")

            if not errors:
                admin_account = _find_admin_account(form_data['identifier'])
                if admin_account:
                    password_ok = _verify_password(
                        password,
                        admin_account['password_salt'],
                        admin_account['password_hash'],
                    )
                    if password_ok:
                        session['is_admin_authenticated'] = True
                        session['admin_identifier'] = admin_account['identifier']
                        session['is_super_admin'] = bool(admin_account.get('is_super_admin'))
                        session.pop('password_reset_user_id', None)
                        session.pop('password_reset_verified_at', None)
                        session.permanent = True
                        session['last_activity_ts'] = int(datetime.now(timezone.utc).timestamp())
                        return redirect(url_for('admin_dashboard_bookings'))

            if not errors:
                identifier = form_data['identifier']
                identifier_lower = identifier.lower()

                conn = _get_db_connection()
                try:
                    user_row = conn.execute(
                        '''
                        SELECT id, username, email, phone, password_hash, is_blocked, must_change_password
                        FROM users
                        WHERE lower(username) = lower(?) OR lower(email) = lower(?) OR phone = ?
                        LIMIT 1
                        ''',
                        (identifier_lower, identifier_lower, identifier),
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
                    session.pop('admin_identifier', None)
                    session.pop('is_super_admin', None)
                    session.pop('password_reset_user_id', None)
                    session.pop('password_reset_verified_at', None)
                    session['must_change_password'] = bool(user_row['must_change_password'])
                    session.permanent = True
                    session['last_activity_ts'] = int(datetime.now(timezone.utc).timestamp())
                    if session.get('must_change_password'):
                        return redirect(url_for('force_password_change'))
                    return redirect(url_for('sunnygym'))

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
        return redirect(url_for('admin_dashboard_bookings'))
    if session.get('user_id') and not session.get('must_change_password'):
        return redirect(url_for('sunnygym'))

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
        if not _validate_csrf_token():
            errors.append("Jeton de sécurité invalide. Veuillez réessayer.")
            return render_template(
                'password_reset.html',
                errors=errors,
                success_message=success_message,
                reset_lookup_data=reset_lookup_data,
                reset_password_data=reset_password_data,
                reset_questions=reset_questions,
            )

        form_action = request.form.get('form_action', 'reset_lookup').strip()

        if form_action == 'reset_lookup':
            reset_lookup_data['identifier'] = request.form.get('reset_identifier', '').strip()
            reset_lookup_data['birth_date'] = request.form.get('reset_birth_date', '').strip()

            if not reset_lookup_data['identifier']:
                errors.append("Le nom d'utilisateur, le courriel ou le téléphone est requis pour la récupération.")
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
                        WHERE (lower(username) = lower(?) OR lower(email) = lower(?) OR phone = ?)
                          AND birth_date = ?
                        LIMIT 1
                        ''',
                        (identifier_lower, identifier_lower, identifier, reset_lookup_data['birth_date']),
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
        return redirect(url_for('sunnygym'))

    errors = []

    if request.method == 'POST':
        if not _validate_csrf_token():
            errors.append("Jeton de sécurité invalide. Veuillez réessayer.")
            return render_template('force_password_change.html', errors=errors)

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
            return redirect(url_for('sunnygym'))

    return render_template('force_password_change.html', errors=errors)


@app.route('/api/bookings', methods=['POST'])
def create_booking():
    user_id = _booking_user_id_for_session()
    if not user_id:
        return jsonify({'ok': False, 'error': 'Connexion requise.'}), 401

    if session.get('user_id') and session.get('must_change_password'):
        return jsonify({'ok': False, 'error': 'Vous devez d’abord changer votre mot de passe.'}), 403

    if not _validate_csrf_token():
        return jsonify({'ok': False, 'error': 'Jeton de sécurité invalide. Veuillez réessayer.'}), 400

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


@app.route('/sunnygym')
def sunnygym():
    opening_hours = _load_opening_hours()
    holidays = _load_holidays()
    special_dates = _load_special_dates()
    reservation_config = _load_reservation_config()
    bookings_by_date = _load_bookings_for_calendar()
    blocked_slot_rules = _load_blocked_slot_rules()
    active_slot_rules = _load_active_slot_rules()
    calendar_js_path = Path(__file__).resolve().parent / 'static' / 'calendar.js'
    calendar_js_version = int(calendar_js_path.stat().st_mtime) if calendar_js_path.exists() else 1
    current_now_local = _now_in_reservation_timezone(reservation_config)

    return render_template(
        'calendar.html',
        opening_hours_json=_opening_hours_for_calendar(opening_hours),
        holidays_json=holidays,
        special_dates_json=special_dates,
        reservation_config_json=reservation_config,
        bookings_json=bookings_by_date,
        blocked_slots_json=blocked_slot_rules,
        active_slots_json=active_slot_rules,
        user_can_book=(
            (bool(session.get('user_id')) and not bool(session.get('must_change_password')))
            or bool(session.get('is_super_admin'))
        ),
        calendar_js_version=calendar_js_version,
        current_day_key=_current_day_key(reservation_config),
        reservation_timezone_name=_get_reservation_timezone_name(reservation_config),
    )


@app.route('/calendar')
def calendar_legacy_redirect():
    return redirect(url_for('sunnygym'))


@app.route('/mes-reservations', methods=['GET', 'POST'])
def my_bookings():
    user_id = _booking_user_id_for_session()
    if not user_id:
        return redirect(url_for('login'))
    if session.get('user_id') and session.get('must_change_password'):
        return redirect(url_for('force_password_change'))

    errors = []
    success_message = None
    reservation_config = _load_reservation_config()

    if request.method == 'POST':
        if not _validate_csrf_token():
            errors.append("Jeton de sécurité invalide. Veuillez réessayer.")
        else:
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
    upcoming_bookings, past_bookings = _split_user_bookings(bookings)
    return render_template(
        'my_bookings.html',
        bookings=bookings,
        upcoming_bookings=upcoming_bookings,
        past_bookings=past_bookings,
        reservation_config=reservation_config,
        errors=errors,
        success_message=success_message,
    )


@app.route('/mon-compte', methods=['GET', 'POST'])
@app.route('/account', methods=['GET', 'POST'])
def my_account():
    profile_user_id = _booking_user_id_for_session()
    if not profile_user_id:
        if session.get('is_admin_authenticated'):
            return redirect(url_for('admin_dashboard_bookings'))
        return redirect(url_for('login'))

    if session.get('user_id') and session.get('must_change_password'):
        return redirect(url_for('force_password_change'))

    profile = _load_user_profile_for_account(profile_user_id)
    if not profile:
        session.clear()
        return redirect(url_for('login'))

    errors = []
    success_message = None
    can_change_password = bool(session.get('user_id')) and not bool(session.get('must_change_password'))
    show_password_form = can_change_password
    profile_can_edit_password = bool(session.get('user_id'))

    if request.method == 'POST' and show_password_form:
        if not _validate_csrf_token():
            errors.append("Jeton de sécurité invalide. Veuillez réessayer.")
        else:
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            new_password_confirm = request.form.get('new_password_confirm', '')

            if not current_password:
                errors.append("Le mot de passe actuel est requis.")
            if len(new_password) < 8:
                errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")
            if new_password != new_password_confirm:
                errors.append("La confirmation du nouveau mot de passe ne correspond pas.")

            conn = _get_db_connection()
            try:
                row = conn.execute(
                    'SELECT password_hash FROM users WHERE id = ? LIMIT 1',
                    (profile_user_id,),
                ).fetchone()
            finally:
                conn.close()

            if not row:
                errors.append("Compte introuvable.")
            elif not _verify_user_password(current_password, row['password_hash']):
                errors.append("Le mot de passe actuel est invalide.")

            if not errors:
                new_password_hash = _make_user_password_hash(new_password)
                conn = _get_db_connection()
                try:
                    conn.execute(
                        'UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?',
                        (new_password_hash, profile_user_id),
                    )
                    conn.commit()
                finally:
                    conn.close()

                session['must_change_password'] = False
                success_message = 'Mot de passe mis à jour.'
                profile = _load_user_profile_for_account(profile_user_id) or profile

    reservation_config = _load_reservation_config()
    reservation_tz = _get_reservation_timezone(reservation_config)
    current_day_key = _current_day_key(reservation_config, tzinfo=reservation_tz)
    current_time_minutes = _now_in_reservation_timezone(reservation_config, tzinfo=reservation_tz).hour * 60 + _now_in_reservation_timezone(reservation_config, tzinfo=reservation_tz).minute

    return render_template(
        'my_account.html',
        profile=profile,
        errors=errors,
        success_message=success_message,
        can_change_password=profile_can_edit_password,
        show_password_form=show_password_form,
        users=[],
        bookings=[],
        invitation_mode_default='manual',
        current_day_key=current_day_key,
        current_time_minutes=current_time_minutes,
        opening_hours_json={},
        holidays_json={},
        special_dates_json={},
        reservation_config_json=reservation_config,
        bookings_json=[],
        blocked_slots_json=[],
        active_slots_json=[],
        user_can_book=bool(session.get('user_id')),
        reservation_config=reservation_config,
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not session.get('is_admin_authenticated'):
        return redirect(url_for('login'))

    if request.method == 'GET' and request.endpoint == 'admin_dashboard' and not request.args.get('tab'):
        return redirect(url_for('admin_dashboard_bookings'))

    errors = []
    success_message = None
    temporary_password_notice = None
    generated_invitation_code_notice = None
    invitation_mode_default = 'unique'
    admin_account_creation_form = {
        'identifier': '',
    }
    endpoint_to_tab = {
        'admin_dashboard_bookings': 'bookings-panel',
        'admin_dashboard_active_slots': 'active-slots-panel',
        'admin_dashboard_blocked_slots': 'active-slots-panel',
        'admin_dashboard_menu': 'menu-panel',
        'admin_dashboard_settings': 'settings-panel',
        'admin_dashboard_opening_hours': 'opening-hours-panel',
        'admin_dashboard_invitations': 'invitation-codes-panel',
        'admin_dashboard_users': 'users-panel',
        'admin_dashboard_configuration': 'configuration-panel',
    }
    active_tab = endpoint_to_tab.get(request.endpoint, request.args.get('tab', 'bookings-panel'))
    if active_tab not in {
        'opening-hours-panel',
        'bookings-panel',
        'active-slots-panel',
        'menu-panel',
        'users-panel',
        'configuration-panel',
        'settings-panel',
        'invitation-codes-panel',
    }:
        active_tab = 'bookings-panel'
    opening_hours = _load_opening_hours()
    holidays = _load_holidays()
    special_dates = _load_special_dates()
    reservation_config = _load_reservation_config()
    invitation_config = _load_invitation_config()
    menu_payload = _load_menu_payload()
    menu_categories = menu_payload.get('categories', [])
    menu_settings = menu_payload.get('settings', {})
    valid_menu_category_keys = {item.get('key') for item in menu_categories if item.get('key')}
    ordered_menu_category_keys = [item.get('key') for item in menu_categories if item.get('key')]
    ordered_menu_product_category_keys = [item.get('key') for item in menu_categories if item.get('key') and item.get('key') != 'all']
    valid_menu_product_category_keys = {item.get('key') for item in menu_categories if item.get('key') and item.get('key') != 'all'}
    menu_active_category = request.args.get('menu_tab', '').strip() or 'all'
    if menu_active_category not in valid_menu_category_keys:
        menu_active_category = 'all' if 'all' in valid_menu_category_keys else (ordered_menu_category_keys[0] if ordered_menu_category_keys else 'all')
    menu_product_form = {
        'category': menu_active_category if menu_active_category in valid_menu_product_category_keys else (ordered_menu_product_category_keys[0] if ordered_menu_product_category_keys else ''),
        'name': '',
        'ingredients_text': '',
    }
    blocked_slots = _load_blocked_slots_for_admin()
    active_slots = _load_active_slots_for_admin()
    blocked_slot_form = {
        'title': '',
        'repeat_type': 'once',
        'reference_date': '',
        'start_time': '09:00',
        'end_time': '10:00',
        'range_start': '',
        'range_end': '',
    }
    active_slot_form = {
        'title': '',
        'date': '',
        'start_time': '09:00',
        'end_time': '10:00',
    }

    if request.method == 'POST':
        if not _validate_csrf_token():
            errors.append("Jeton de sécurité invalide. Veuillez réessayer.")

        admin_action = request.form.get('admin_action', '').strip() if not errors else ''
        requested_menu_active_category = request.form.get('menu_active_category', '').strip()
        if requested_menu_active_category in valid_menu_category_keys:
            menu_active_category = requested_menu_active_category

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
            raw_timezone = request.form.get('reservation_timezone', '').strip()
            raw_availability_mode = request.form.get('availability_mode', '').strip().lower()
            raw_week_start_day = request.form.get('week_start_day', '').strip().lower()
            raw_warning_display_count = request.form.get('warning_display_count', '').strip()
            raw_sunnygym_display_mode = request.form.get('sunnygym_display_mode', '').strip().lower()
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

            if raw_timezone and raw_timezone not in VALID_RESERVATION_TIMEZONES:
                errors.append("Fuseau horaire invalide.")
            if raw_availability_mode not in VALID_AVAILABILITY_MODES:
                errors.append("Mode de disponibilités invalide.")
            if raw_week_start_day and raw_week_start_day not in VALID_WEEK_START_DAYS:
                errors.append("Jour de début de semaine invalide.")
            if raw_sunnygym_display_mode and raw_sunnygym_display_mode not in VALID_SUNNYGYM_DISPLAY_MODES:
                errors.append("Mode d'affichage SunnyGym invalide.")

            if not raw_max_sim.isdigit() or int(raw_max_sim) < 1:
                errors.append("Capacité maximale (personnes) doit être un entier >= 1.")
            if not raw_min_duration.isdigit() or int(raw_min_duration) < 1:
                errors.append("Temps minimal doit être un entier >= 1 minute.")
            if not raw_max_duration.isdigit() or int(raw_max_duration) < 1:
                errors.append("Temps maximal doit être un entier >= 1 minute.")
            if not raw_latest_start.isdigit() or int(raw_latest_start) < 0:
                errors.append("Délai maximal avant fermeture doit être un entier >= 0 minute.")
            if not raw_warning_display_count.isdigit() or int(raw_warning_display_count) < 1:
                errors.append("Le nombre d'avertissements affichés doit être un entier >= 1.")

            min_duration = int(raw_min_duration) if raw_min_duration.isdigit() else 0
            max_duration = int(raw_max_duration) if raw_max_duration.isdigit() else 0
            warning_display_count = int(raw_warning_display_count) if raw_warning_display_count.isdigit() else 0
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
                'timezone': (
                    raw_timezone
                    if raw_timezone in VALID_RESERVATION_TIMEZONES
                    else reservation_config.get('timezone', DEFAULT_RESERVATION_TIMEZONE)
                ),
                'availability_mode': (
                    raw_availability_mode
                    if raw_availability_mode in VALID_AVAILABILITY_MODES
                    else reservation_config.get('availability_mode', AVAILABILITY_MODE_OPENING_HOURS)
                ),
                'week_start_day': (
                    raw_week_start_day
                    if raw_week_start_day in VALID_WEEK_START_DAYS
                    else reservation_config.get('week_start_day', WEEK_START_SUNDAY)
                ),
                'warning_display_count': (
                    warning_display_count
                    if warning_display_count > 0
                    else reservation_config.get('warning_display_count', 4)
                ),
                'sunnygym_display_mode': (
                    raw_sunnygym_display_mode
                    if raw_sunnygym_display_mode in VALID_SUNNYGYM_DISPLAY_MODES
                    else reservation_config.get('sunnygym_display_mode', SUNNYGYM_DISPLAY_MODE_CALENDAR)
                ),
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

        if admin_action == 'create_admin_account':
            active_tab = 'users-panel'
            admin_identifier_text = request.form.get('new_admin_identifier', '').strip()
            admin_password = request.form.get('new_admin_password', '')
            admin_password_confirm = request.form.get('new_admin_password_confirm', '')
            admin_account_creation_form['identifier'] = admin_identifier_text

            if not admin_identifier_text:
                errors.append("L'identifiant administrateur est requis.")
            if len(admin_password) < 8:
                errors.append("Le mot de passe administrateur doit contenir au moins 8 caractères.")
            if admin_password != admin_password_confirm:
                errors.append("La confirmation du mot de passe administrateur ne correspond pas.")

            if not errors:
                try:
                    _save_admin_account(admin_identifier_text, admin_password)
                    success_message = "Nouveau compte administrateur créé."
                    admin_account_creation_form = {'identifier': ''}
                except ValueError as exc:
                    errors.append(str(exc))

        if admin_action == 'delete_admin_account':
            active_tab = 'users-panel'
            target_identifier = _normalize_admin_identifier(request.form.get('admin_identifier', ''))
            current_admin_identifier = _normalize_admin_identifier(session.get('admin_identifier', ''))

            if not target_identifier:
                errors.append("Compte administrateur invalide.")
            elif target_identifier == current_admin_identifier:
                errors.append("Vous ne pouvez pas supprimer le compte administrateur actuellement connecté.")
            elif target_identifier == SUPER_ADMIN_IDENTIFIER:
                errors.append("Le compte SuperAdmin est protégé.")
            else:
                admin_accounts_to_keep = []
                removed_admin_account = False
                for account in _load_admin_accounts():
                    if account.get('identifier') == target_identifier:
                        removed_admin_account = True
                        continue
                    admin_accounts_to_keep.append(account)

                if not removed_admin_account:
                    errors.append("Compte administrateur introuvable.")
                else:
                    _save_admin_accounts(admin_accounts_to_keep)
                    success_message = "Compte administrateur supprimé."

        if admin_action == 'update_super_admin_password':
            active_tab = 'users-panel'
            current_password = request.form.get('super_admin_current_password', '')
            new_password = request.form.get('super_admin_new_password', '')
            new_password_confirm = request.form.get('super_admin_new_password_confirm', '')
            current_admin_identifier = _normalize_admin_identifier(session.get('admin_identifier', ''))

            if not session.get('is_super_admin') or current_admin_identifier != SUPER_ADMIN_IDENTIFIER:
                errors.append("Seul le SuperAdmin peut modifier ce mot de passe.")
            if not current_password:
                errors.append("Le mot de passe actuel est requis.")
            if len(new_password) < 8:
                errors.append("Le nouveau mot de passe SuperAdmin doit contenir au moins 8 caractères.")
            if new_password != new_password_confirm:
                errors.append("La confirmation du mot de passe SuperAdmin ne correspond pas.")

            super_admin_account = _find_admin_account(SUPER_ADMIN_IDENTIFIER)
            if not errors and (
                not super_admin_account
                or not _verify_password(
                    current_password,
                    super_admin_account['password_salt'],
                    super_admin_account['password_hash'],
                )
            ):
                errors.append("Le mot de passe actuel est invalide.")

            if not errors:
                password_data = _hash_password(new_password)
                accounts = _load_admin_accounts()
                updated = False
                for account in accounts:
                    if account['identifier'] == SUPER_ADMIN_IDENTIFIER:
                        account['password_salt'] = password_data['salt']
                        account['password_hash'] = password_data['hash']
                        account['is_super_admin'] = True
                        updated = True
                        break
                if not updated:
                    accounts.append(
                        {
                            'identifier': SUPER_ADMIN_IDENTIFIER,
                            'password_salt': password_data['salt'],
                            'password_hash': password_data['hash'],
                            'created_at': datetime.now(timezone.utc).isoformat(),
                            'is_super_admin': True,
                        }
                    )
                _save_admin_accounts(accounts)
                success_message = "Mot de passe SuperAdmin mis à jour."

        if admin_action in {'create_blocked_slot', 'delete_blocked_slot', 'create_active_slot', 'delete_active_slot'}:
            active_tab = 'active-slots-panel'

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

            if admin_action == 'create_active_slot':
                active_slot_form = {
                    'title': request.form.get('active_slot_title', '').strip(),
                    'date': request.form.get('active_slot_date', '').strip(),
                    'start_time': request.form.get('active_slot_start_time', '').strip(),
                    'end_time': request.form.get('active_slot_end_time', '').strip(),
                }

                if not _is_valid_iso_date_text(active_slot_form['date']):
                    errors.append("Date de plage activée invalide.")

                start_minutes = _time_text_to_minutes(active_slot_form['start_time'])
                end_minutes = _time_text_to_minutes(active_slot_form['end_time'])
                if start_minutes is None or end_minutes is None:
                    errors.append("Heure de début/fin de la plage activée invalide.")
                elif end_minutes <= start_minutes:
                    errors.append("La plage activée doit se terminer après son début.")

                if not errors:
                    conn = _get_db_connection()
                    try:
                        conn.execute(
                            '''
                            INSERT INTO active_slots (title, date_value, start_time, end_time)
                            VALUES (?, ?, ?, ?)
                            ''',
                            (
                                active_slot_form['title'] or None,
                                active_slot_form['date'],
                                active_slot_form['start_time'],
                                active_slot_form['end_time'],
                            ),
                        )
                        conn.commit()
                        active_slot_form = {
                            'title': '',
                            'date': '',
                            'start_time': '09:00',
                            'end_time': '10:00',
                        }
                        success_message = 'Plage activée enregistrée.'
                    finally:
                        conn.close()

            if admin_action == 'delete_active_slot':
                active_slot_id_text = request.form.get('active_slot_id', '').strip()
                if not active_slot_id_text.isdigit():
                    errors.append("Plage activée invalide.")
                else:
                    conn = _get_db_connection()
                    try:
                        conn.execute('DELETE FROM active_slots WHERE id = ?', (int(active_slot_id_text),))
                        conn.commit()
                        success_message = 'Plage activée supprimée.'
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
                        'SELECT id, email FROM users WHERE id = ?',
                        (user_id,),
                    ).fetchone()
                    if not user_row:
                        errors.append("Utilisateur introuvable.")
                    elif _is_super_admin_user_email(user_row['email']):
                        errors.append("Le compte utilisateur SuperAdmin est protégé.")
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

        if admin_action in {'mark_booking_present', 'mark_booking_no_show', 'delete_booking'}:
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
                        if admin_action == 'delete_booking':
                            conn.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
                            success_message = 'Réservation supprimée.'
                        else:
                            booking_status = 'present' if admin_action == 'mark_booking_present' else 'no_show'
                            conn.execute(
                                'UPDATE bookings SET booking_status = ? WHERE id = ?',
                                (booking_status, booking_id),
                            )
                            success_message = 'Statut de la réservation mis à jour.'
                        conn.commit()
                finally:
                    conn.close()

        if admin_action in {
            'add_menu_category',
            'rename_menu_category',
            'delete_menu_category',
            'add_menu_product',
            'rename_menu_product',
            'update_menu_product_flavors',
            'delete_menu_product',
            'save_menu_settings',
            'save_menu_disclaimer',
        }:
            active_tab = 'menu-panel'
            candidate_menu_payload = _normalize_menu_payload(menu_payload)

            if admin_action == 'add_menu_category':
                new_category_label = _normalize_menu_label(request.form.get('menu_category_label', ''))
                if not new_category_label:
                    errors.append("Le nom du nouvel onglet est requis.")
                else:
                    existing_labels = {
                        item.get('label', '').casefold() for item in candidate_menu_payload.get('categories', [])
                    }
                    if new_category_label.casefold() in existing_labels:
                        errors.append("Un onglet avec ce nom existe déjà.")
                    else:
                        existing_keys = {
                            item.get('key', '') for item in candidate_menu_payload.get('categories', [])
                        }
                        category_key = _slugify_menu_category_key(new_category_label)
                        suffix = 2
                        while category_key in existing_keys:
                            category_key = f"{_slugify_menu_category_key(new_category_label)}_{suffix}"
                            suffix += 1
                        candidate_menu_payload['categories'].append(
                            {'key': category_key, 'label': new_category_label}
                        )
                        _save_menu_payload(candidate_menu_payload)
                        menu_payload = _load_menu_payload()
                        menu_categories = menu_payload.get('categories', [])
                        valid_menu_category_keys = {item.get('key') for item in menu_categories if item.get('key')}
                        ordered_menu_category_keys = [item.get('key') for item in menu_categories if item.get('key')]
                        ordered_menu_product_category_keys = [item.get('key') for item in menu_categories if item.get('key') and item.get('key') != 'all']
                        valid_menu_product_category_keys = {
                            item.get('key') for item in menu_categories if item.get('key') and item.get('key') != 'all'
                        }
                        menu_active_category = category_key
                        menu_product_form['category'] = category_key
                        success_message = 'Nouvel onglet du menu ajouté.'

            if admin_action == 'rename_menu_category':
                category_key = request.form.get('menu_category_key', '').strip()
                rename_label = _normalize_menu_label(request.form.get('menu_category_rename_label', ''))
                menu_active_category = category_key or menu_active_category
                if category_key not in valid_menu_product_category_keys:
                    errors.append("Onglet du menu invalide.")
                elif not rename_label:
                    errors.append("Le nouveau nom de l'onglet est requis.")
                else:
                    existing_labels = {
                        item.get('label', '').casefold()
                        for item in candidate_menu_payload.get('categories', [])
                        if item.get('key') != category_key
                    }
                    if rename_label.casefold() in existing_labels:
                        errors.append("Un autre onglet utilise déjà ce nom.")
                    else:
                        for category in candidate_menu_payload.get('categories', []):
                            if category.get('key') == category_key:
                                category['label'] = rename_label
                                break
                        _save_menu_payload(candidate_menu_payload)
                        menu_payload = _load_menu_payload()
                        success_message = 'Nom de l’onglet mis à jour.'

            if admin_action == 'delete_menu_category':
                category_key = request.form.get('menu_category_key', '').strip()
                menu_active_category = category_key or menu_active_category
                if category_key not in valid_menu_product_category_keys:
                    errors.append("Onglet du menu invalide.")
                else:
                    category_items = [
                        item for item in candidate_menu_payload.get('items', [])
                        if item.get('category') == category_key
                    ]
                    if category_items:
                        errors.append("Supprimez d’abord les produits de cet onglet avant de le retirer.")
                    else:
                        candidate_menu_payload['categories'] = [
                            item for item in candidate_menu_payload.get('categories', [])
                            if item.get('key') != category_key
                        ]
                        _save_menu_payload(candidate_menu_payload)
                        menu_payload = _load_menu_payload()
                        menu_categories = menu_payload.get('categories', [])
                        valid_menu_category_keys = {item.get('key') for item in menu_categories if item.get('key')}
                        ordered_menu_category_keys = [item.get('key') for item in menu_categories if item.get('key')]
                        ordered_menu_product_category_keys = [item.get('key') for item in menu_categories if item.get('key') and item.get('key') != 'all']
                        valid_menu_product_category_keys = {
                            item.get('key') for item in menu_categories if item.get('key') and item.get('key') != 'all'
                        }
                        menu_active_category = 'all'
                        menu_product_form['category'] = ordered_menu_product_category_keys[0] if ordered_menu_product_category_keys else ''
                    success_message = 'Onglet du menu supprimé.'

            if admin_action == 'save_menu_settings':
                requested_mode = request.form.get('menu_disclaimer_mode', 'popup').strip().lower()
                if requested_mode not in {'disabled', 'header', 'popup'}:
                    errors.append("Mode de disclaimer invalide.")
                else:
                    candidate_settings = dict(candidate_menu_payload.get('settings', {}))
                    candidate_settings['disclaimer_mode'] = requested_mode
                    candidate_menu_payload['settings'] = candidate_settings
                    _save_menu_payload(candidate_menu_payload)
                    menu_payload = _load_menu_payload()
                    menu_settings = menu_payload.get('settings', {})
                    success_message = 'Paramètres du menu enregistrés.'

            if admin_action == 'save_menu_disclaimer':
                disclaimer_texts = [
                    request.form.get('menu_disclaimer_text_1', ''),
                    request.form.get('menu_disclaimer_text_2', ''),
                    request.form.get('menu_disclaimer_text_3', ''),
                ]
                candidate_settings = dict(candidate_menu_payload.get('settings', {}))
                candidate_settings['disclaimer_texts'] = _normalize_menu_disclaimer_texts(disclaimer_texts)
                candidate_menu_payload['settings'] = candidate_settings
                _save_menu_payload(candidate_menu_payload)
                menu_payload = _load_menu_payload()
                menu_settings = menu_payload.get('settings', {})
                success_message = 'Disclaimer mis à jour.'

            if admin_action == 'add_menu_product':
                product_category = request.form.get('menu_product_category', '').strip()
                product_name = _normalize_menu_label(request.form.get('menu_product_name', ''))
                product_ingredients_text = request.form.get('menu_product_ingredients', '').strip()
                menu_product_form = {
                    'category': product_category,
                    'name': product_name,
                    'ingredients_text': product_ingredients_text,
                }
                if product_category in valid_menu_product_category_keys:
                    menu_active_category = product_category
                if product_category not in valid_menu_product_category_keys:
                    errors.append("Catégorie de produit invalide.")
                if not product_name:
                    errors.append("Le nom du produit est requis.")

                existing_ingredients = candidate_menu_payload.get('ingredients', [])
                product_ingredients = _parse_menu_ingredients(product_ingredients_text, existing_ingredients)
                if not product_ingredients:
                    errors.append("Ajoutez au moins une saveur.")

                if not errors:
                    candidate_menu_payload['items'].append(
                        {
                            'id': secrets.token_hex(8),
                            'name': product_name,
                            'category': product_category,
                            'description': '',
                            'price': '',
                            'ingredients': product_ingredients,
                            'is_active': True,
                        }
                    )
                    candidate_menu_payload['ingredients'] = _dedupe_menu_labels(
                        list(candidate_menu_payload.get('ingredients', [])) + product_ingredients
                    )
                    _save_menu_payload(candidate_menu_payload)
                    menu_payload = _load_menu_payload()
                    menu_product_form = {
                        'category': product_category,
                        'name': '',
                        'ingredients_text': '',
                    }
                    success_message = 'Produit ajouté au menu.'

            if admin_action == 'delete_menu_product':
                product_id = request.form.get('menu_product_id', '').strip()
                target_category = request.form.get('menu_product_category', '').strip()
                original_count = len(candidate_menu_payload.get('items', []))
                candidate_menu_payload['items'] = [
                    item for item in candidate_menu_payload.get('items', [])
                    if item.get('id') != product_id
                ]
                if len(candidate_menu_payload['items']) == original_count:
                    errors.append("Produit introuvable.")
                else:
                    candidate_menu_payload = _sync_menu_ingredients_from_items(candidate_menu_payload)
                    _save_menu_payload(candidate_menu_payload)
                    menu_payload = _load_menu_payload()
                    success_message = 'Produit supprimé du menu.'

            if admin_action == 'rename_menu_product':
                product_id = request.form.get('menu_product_id', '').strip()
                target_category = request.form.get('menu_product_category', '').strip()
                product_name = _normalize_menu_label(request.form.get('menu_product_name', ''))
                if not product_name:
                    errors.append("Le nom du produit est requis.")
                else:
                    product_item = next(
                        (item for item in candidate_menu_payload.get('items', []) if item.get('id') == product_id),
                        None,
                    )
                    if not product_item:
                        errors.append("Produit introuvable.")
                    else:
                        product_item['name'] = product_name
                        _save_menu_payload(candidate_menu_payload)
                        menu_payload = _load_menu_payload()
                        success_message = 'Produit renommé.'

            if admin_action == 'update_menu_product_flavors':
                product_id = request.form.get('menu_product_id', '').strip()
                target_category = request.form.get('menu_product_category', '').strip()
                product_ingredients_text = request.form.get('menu_product_ingredients', '').strip()

                existing_ingredients = candidate_menu_payload.get('ingredients', [])
                product_ingredients = _parse_menu_ingredients(product_ingredients_text, existing_ingredients)
                if not product_ingredients:
                    errors.append("Ajoutez au moins une saveur.")
                else:
                    product_item = next(
                        (item for item in candidate_menu_payload.get('items', []) if item.get('id') == product_id),
                        None,
                    )
                    if not product_item:
                        errors.append("Produit introuvable.")
                    else:
                        product_item['ingredients'] = product_ingredients
                        candidate_menu_payload['ingredients'] = _dedupe_menu_labels(
                            list(candidate_menu_payload.get('ingredients', [])) + product_ingredients
                        )
                        candidate_menu_payload = _sync_menu_ingredients_from_items(candidate_menu_payload)
                        _save_menu_payload(candidate_menu_payload)
                        menu_payload = _load_menu_payload()
                        success_message = 'Saveurs du produit mises à jour.'

    admin_account = _find_admin_account(session.get('admin_identifier', '')) or _load_admin_account()
    admin_identifier = _admin_account_display_name(admin_account) if admin_account else 'Administrateur'
    admin_accounts = _load_admin_accounts_for_management()
    bookings = _load_bookings_for_admin()
    bookings_grouped = _group_bookings_by_date(bookings)
    users = _load_users_for_admin()
    current_admin_identifier = _normalize_admin_identifier(session.get('admin_identifier', ''))
    admin_account_by_identifier = {
        account.get('identifier'): account
        for account in admin_accounts
        if account.get('identifier')
    }
    linked_user_admin_identifiers = set()
    for user in users:
        user_admin_identifiers = [
            _normalize_admin_identifier(user.get('email', '')),
            _normalize_admin_identifier(user.get('username', '')),
        ]
        user_admin_identifiers = [identifier for identifier in user_admin_identifiers if identifier]
        matched_admin_identifiers = [
            identifier
            for identifier in user_admin_identifiers
            if identifier in admin_account_by_identifier
        ]
        linked_user_admin_identifiers.update(matched_admin_identifiers)
        matched_admin_identifier = (
            current_admin_identifier
            if current_admin_identifier in matched_admin_identifiers
            else (matched_admin_identifiers[0] if matched_admin_identifiers else '')
        )
        matched_admin_account = (
            admin_account_by_identifier.get(matched_admin_identifier)
            if matched_admin_identifier
            else None
        )

        user['admin_account_identifier'] = matched_admin_account['identifier'] if matched_admin_account else ''
        user['is_admin_account_user'] = bool(matched_admin_account and not user.get('is_super_admin_user'))
        user['can_delete_admin_account'] = bool(
            matched_admin_account
            and matched_admin_account.get('identifier') != current_admin_identifier
            and not matched_admin_account.get('is_super_admin')
        )
    admin_account_cards = [
        {
            **account,
            'can_delete': (
                account.get('identifier') != current_admin_identifier
                and not account.get('is_super_admin')
            ),
        }
        for account in admin_accounts
        if not account.get('is_super_admin')
        and account.get('identifier') not in linked_user_admin_identifiers
    ]
    invitation_codes = _load_invitation_codes_for_admin()
    blocked_slots = _load_blocked_slots_for_admin()
    active_slots = _load_active_slots_for_admin()
    bookings_by_date = _load_bookings_for_calendar()
    blocked_slot_rules = _load_blocked_slot_rules()
    active_slot_rules = _load_active_slot_rules()
    calendar_js_path = Path(__file__).resolve().parent / 'static' / 'calendar.js'
    calendar_js_version = int(calendar_js_path.stat().st_mtime) if calendar_js_path.exists() else 1
    current_now_local = _now_in_reservation_timezone(reservation_config)
    blocked_slots_page_title = (
        'Ajouter une plage horaire'
        if reservation_config.get('availability_mode') == AVAILABILITY_MODE_ACTIVE_SLOTS
        else 'Blocages horaires'
    )
    page_title_by_tab = {
        'opening-hours-panel': "Heures d'ouverture",
        'bookings-panel': 'Réservations',
        'active-slots-panel': blocked_slots_page_title,
        'menu-panel': 'Menu',
        'configuration-panel': 'Configuration des réservations',
        'settings-panel': 'Paramètres',
        'invitation-codes-panel': 'Invitations',
        'users-panel': 'Gestion des comptes',
    }

    template_by_tab = {
        'opening-hours-panel': 'admin_dashboard_opening_hours.html',
        'bookings-panel': 'admin_dashboard_bookings.html',
        'active-slots-panel': 'admin_dashboard_active_slots.html',
        'menu-panel': 'admin_dashboard_menu.html',
        'configuration-panel': 'admin_dashboard_configuration.html',
        'settings-panel': 'admin_dashboard_settings.html',
        'invitation-codes-panel': 'admin_dashboard_invitations.html',
        'users-panel': 'admin_dashboard_users.html',
    }

    menu_categories = menu_payload.get('categories', [])
    valid_menu_category_keys = {item.get('key') for item in menu_categories if item.get('key')}
    ordered_menu_category_keys = [item.get('key') for item in menu_categories if item.get('key')]
    ordered_menu_product_category_keys = [item.get('key') for item in menu_categories if item.get('key') and item.get('key') != 'all']
    valid_menu_product_category_keys = {item.get('key') for item in menu_categories if item.get('key') and item.get('key') != 'all'}
    if menu_active_category not in valid_menu_category_keys:
        menu_active_category = 'all' if 'all' in valid_menu_category_keys else (ordered_menu_category_keys[0] if ordered_menu_category_keys else 'all')
    if menu_product_form.get('category') not in valid_menu_product_category_keys:
        menu_product_form['category'] = (
            menu_active_category if menu_active_category in valid_menu_product_category_keys
            else (ordered_menu_product_category_keys[0] if ordered_menu_product_category_keys else '')
        )

    return render_template(
        template_by_tab.get(active_tab, 'admin_dashboard_bookings.html'),
        admin_identifier=admin_identifier,
        current_admin_is_super_admin=bool(session.get('is_super_admin')),
        opening_hours=opening_hours,
        opening_hours_json=_opening_hours_for_calendar(opening_hours),
        holidays_json=holidays,
        special_dates=special_dates,
        special_dates_json=special_dates,
        reservation_config=reservation_config,
        reservation_config_json=reservation_config,
        reservation_timezone_options=RESERVATION_TIMEZONE_OPTIONS,
        valid_slot_intervals=sorted(VALID_SLOT_INTERVALS),
        bookings=bookings,
        bookings_json=bookings_by_date,
        bookings_grouped=bookings_grouped,
        users=users,
        admin_accounts=admin_accounts,
        admin_account_cards=admin_account_cards,
        invitation_config=invitation_config,
        invitation_codes=invitation_codes,
        menu_payload=menu_payload,
        menu_settings=menu_settings,
        menu_categories=menu_categories,
        menu_items_by_category=_group_menu_items_by_category(menu_payload),
        menu_active_category=menu_active_category,
        menu_product_form=menu_product_form,
        menu_ingredients=menu_payload.get('ingredients', []),
        blocked_slots=blocked_slots,
        blocked_slots_json=blocked_slot_rules,
        active_slots=active_slots,
        active_slots_json=active_slot_rules,
        active_slot_form=active_slot_form,
        blocked_slot_form=blocked_slot_form,
        blocked_slot_repeat_options=BLOCKED_SLOT_REPEAT_OPTIONS,
        admin_account_creation_form=admin_account_creation_form,
        generated_invitation_code_notice=generated_invitation_code_notice,
        invitation_mode_default=invitation_mode_default,
        temporary_password_notice=temporary_password_notice,
        user_can_book=False,
        calendar_js_version=calendar_js_version,
        active_tab=active_tab,
        page_title=page_title_by_tab.get(active_tab, 'Tableau de bord'),
        current_day_key=_current_day_key(reservation_config),
        current_time_minutes=(current_now_local.hour * 60) + current_now_local.minute,
        day_config=DAY_CONFIG,
        errors=errors,
        success_message=success_message,
    )


app.add_url_rule('/admin/dashboard/bookings', endpoint='admin_dashboard_bookings', view_func=admin_dashboard, methods=['GET', 'POST'])
app.add_url_rule('/admin/dashboard/active-slots', endpoint='admin_dashboard_active_slots', view_func=admin_dashboard, methods=['GET', 'POST'])
app.add_url_rule('/admin/dashboard/blocked-slots', endpoint='admin_dashboard_blocked_slots', view_func=admin_dashboard, methods=['GET', 'POST'])
app.add_url_rule('/admin/dashboard/menu', endpoint='admin_dashboard_menu', view_func=admin_dashboard, methods=['GET', 'POST'])
app.add_url_rule('/admin/dashboard/settings', endpoint='admin_dashboard_settings', view_func=admin_dashboard, methods=['GET', 'POST'])
app.add_url_rule('/admin/dashboard/opening-hours', endpoint='admin_dashboard_opening_hours', view_func=admin_dashboard, methods=['GET', 'POST'])
app.add_url_rule('/admin/dashboard/invitations', endpoint='admin_dashboard_invitations', view_func=admin_dashboard, methods=['GET', 'POST'])
app.add_url_rule('/admin/dashboard/users', endpoint='admin_dashboard_users', view_func=admin_dashboard, methods=['GET', 'POST'])
app.add_url_rule('/admin/dashboard/configuration', endpoint='admin_dashboard_configuration', view_func=admin_dashboard, methods=['GET', 'POST'])


if __name__ == '__main__':
    flask_debug_enabled = os.environ.get('FLASK_DEBUG', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    production_mode = os.environ.get('FLASK_ENV') == 'production'
    port_env_var = 'PORT' if os.environ.get('FLASK_ENV') == 'production' else 'FLASK_RUN_PORT'
    try:
        flask_port = int(os.environ.get(port_env_var, '39048'))
    except ValueError:
        flask_port = 39048
    flask_host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    server_name = os.environ.get(
        'SUNNYVIBE_SERVER',
        'waitress' if production_mode else 'flask',
    ).strip().lower()

    app.logger.info(
        'Starting SunnyVibeScheduler on %s:%s server=%s debug=%s pid=%s',
        flask_host,
        flask_port,
        server_name,
        flask_debug_enabled,
        os.getpid(),
    )

    if server_name == 'waitress':
        from waitress import serve

        serve(
            app,
            host=flask_host,
            port=flask_port,
            threads=int(os.environ.get('SUNNYVIBE_WAITRESS_THREADS', '8')),
            connection_limit=int(os.environ.get('SUNNYVIBE_WAITRESS_CONNECTION_LIMIT', '80')),
            channel_timeout=int(os.environ.get('SUNNYVIBE_WAITRESS_CHANNEL_TIMEOUT', '30')),
        )
        raise SystemExit(0)

    app.run(
        host=flask_host,
        port=flask_port,
        debug=flask_debug_enabled,
        threaded=False,
        use_reloader=flask_debug_enabled,
    )
