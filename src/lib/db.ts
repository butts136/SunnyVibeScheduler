import fs from 'node:fs';
import { DatabaseSync } from 'node:sqlite';

import {
  DATA_DIR,
  DATABASE_PATH,
  LEGACY_ADMIN_KEY_PATH,
  LEGACY_ADMIN_STORE_PATH,
} from '@/lib/constants';
import { decryptLegacyFernet } from '@/lib/security/legacy-fernet';

type LegacyAdminRecord = {
  identifier?: string;
  password_salt?: string;
  password_hash?: string;
  created_at?: string;
};

const globalDatabase = globalThis as typeof globalThis & {
  __sunnyvibeDb?: DatabaseSync;
  __sunnyvibeDbInitialized?: boolean;
};

function getDatabase() {
  if (!globalDatabase.__sunnyvibeDb) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    globalDatabase.__sunnyvibeDb = new DatabaseSync(DATABASE_PATH);
    globalDatabase.__sunnyvibeDb.exec('PRAGMA foreign_keys = ON');
  }

  if (!globalDatabase.__sunnyvibeDbInitialized) {
    initializeDatabase(globalDatabase.__sunnyvibeDb);
    globalDatabase.__sunnyvibeDbInitialized = true;
  }

  return globalDatabase.__sunnyvibeDb;
}

function tableColumns(db: DatabaseSync, tableName: string) {
  const rows = db.prepare(`PRAGMA table_info(${tableName})`).all() as Array<{ name: string }>;
  return new Set(rows.map((row) => row.name));
}

function addColumnIfMissing(db: DatabaseSync, tableName: string, columnName: string, ddl: string) {
  const columns = tableColumns(db, tableName);
  if (!columns.has(columnName)) {
    db.exec(`ALTER TABLE ${tableName} ADD COLUMN ${ddl}`);
  }
}

function migrateLegacyAdmins(db: DatabaseSync) {
  const adminsCount = db.prepare('SELECT COUNT(*) AS total FROM admins').get() as { total: number };
  if (Number(adminsCount.total) > 0) {
    return;
  }

  if (!fs.existsSync(LEGACY_ADMIN_STORE_PATH) || !fs.existsSync(LEGACY_ADMIN_KEY_PATH)) {
    return;
  }

  try {
    const container = JSON.parse(fs.readFileSync(LEGACY_ADMIN_STORE_PATH, 'utf8')) as {
      encrypted_payload?: string;
    };
    if (!container.encrypted_payload) {
      return;
    }

    const secret = fs.readFileSync(LEGACY_ADMIN_KEY_PATH, 'utf8').trim();
    const decrypted = decryptLegacyFernet(secret, container.encrypted_payload);
    const payload = JSON.parse(decrypted) as unknown;

    let records: LegacyAdminRecord[] = [];
    if (Array.isArray(payload)) {
      records = payload as LegacyAdminRecord[];
    } else if (
      payload
      && typeof payload === 'object'
      && 'accounts' in payload
      && Array.isArray((payload as { accounts?: unknown }).accounts)
    ) {
      records = (payload as { accounts: LegacyAdminRecord[] }).accounts;
    } else if (payload && typeof payload === 'object') {
      records = [payload as LegacyAdminRecord];
    }

    const insert = db.prepare(`
      INSERT OR IGNORE INTO admins (email, password_hash, created_at)
      VALUES (?, ?, ?)
    `);

    for (const record of records) {
      const email = String(record.identifier ?? '').trim().toLowerCase();
      const salt = String(record.password_salt ?? '').trim();
      const hash = String(record.password_hash ?? '').trim();
      const createdAt = String(record.created_at ?? '').trim() || new Date().toISOString();
      if (!email || !salt || !hash) {
        continue;
      }
      insert.run(email, `pbkdf2$${salt}$${hash}`, createdAt);
    }
  } catch {
    // Legacy migration failure should not stop the application startup.
  }
}

function initializeDatabase(db: DatabaseSync) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS admins (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE,
      phone TEXT UNIQUE,
      password_hash TEXT NOT NULL,
      full_name TEXT,
      birth_date TEXT,
      is_blocked INTEGER NOT NULL DEFAULT 0,
      reservation_limit INTEGER,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      CHECK (email IS NOT NULL OR phone IS NOT NULL)
    );

    CREATE TABLE IF NOT EXISTS bookings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      start TEXT NOT NULL,
      end TEXT NOT NULL,
      title TEXT,
      allow_companion INTEGER NOT NULL DEFAULT 0,
      companion_count INTEGER NOT NULL DEFAULT 0,
      is_private INTEGER NOT NULL DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_bookings_start ON bookings(start);
    CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings(user_id);

    CREATE TABLE IF NOT EXISTS invitation_codes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT NOT NULL UNIQUE,
      expires_at TEXT NOT NULL,
      used_at TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_blocked_slots_repeat ON blocked_slots(repeat_type);

    CREATE TABLE IF NOT EXISTS active_slots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT,
      date_value TEXT NOT NULL,
      start_time TEXT NOT NULL,
      end_time TEXT NOT NULL,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_active_slots_date_value ON active_slots(date_value);

    CREATE TABLE IF NOT EXISTS password_reset_tokens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      token_hash TEXT NOT NULL UNIQUE,
      expires_at TEXT NOT NULL,
      used_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
  `);

  addColumnIfMissing(db, 'users', 'birth_date', 'birth_date TEXT');
  addColumnIfMissing(db, 'users', 'is_blocked', 'is_blocked INTEGER NOT NULL DEFAULT 0');
  addColumnIfMissing(db, 'users', 'reservation_limit', 'reservation_limit INTEGER');

  addColumnIfMissing(db, 'bookings', 'allow_companion', 'allow_companion INTEGER NOT NULL DEFAULT 0');
  addColumnIfMissing(db, 'bookings', 'companion_count', 'companion_count INTEGER NOT NULL DEFAULT 0');
  addColumnIfMissing(db, 'bookings', 'is_private', 'is_private INTEGER NOT NULL DEFAULT 0');

  migrateLegacyAdmins(db);
}

export function db() {
  return getDatabase();
}

export function transaction<T>(callback: () => T) {
  const database = db();
  database.exec('BEGIN IMMEDIATE');
  try {
    const value = callback();
    database.exec('COMMIT');
    return value;
  } catch (error) {
    database.exec('ROLLBACK');
    throw error;
  }
}
