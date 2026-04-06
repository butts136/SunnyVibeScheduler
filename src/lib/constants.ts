import path from 'node:path';

export const ROOT_DIR = process.cwd();
export const DATA_DIR = path.join(ROOT_DIR, 'data');
export const DATABASE_PATH = path.join(DATA_DIR, 'sunnyvibe.db');
export const OPENING_HOURS_PATH = path.join(DATA_DIR, 'opening_hours.json');
export const RESERVATION_CONFIG_PATH = path.join(DATA_DIR, 'reservation_config.json');
export const INVITATION_CONFIG_PATH = path.join(DATA_DIR, 'invitation_config.json');
export const LEGACY_ADMIN_STORE_PATH = path.join(DATA_DIR, 'admin_account.json');
export const LEGACY_ADMIN_KEY_PATH = path.join(DATA_DIR, 'admin_account.key');
export const SESSION_SECRET_PATH = path.join(DATA_DIR, '.session-secret');

export const SESSION_COOKIE_NAME = 'sunnyvibe_session';
export const GUEST_CSRF_COOKIE_NAME = 'sunnyvibe_guest_csrf';
export const SESSION_MAX_AGE_SECONDS = 60 * 60;

export const VALID_SLOT_INTERVALS = [15, 30, 60] as const;
export const DEFAULT_RESERVATION_TIMEZONE = 'America/Toronto';
export const DEFAULT_HOLIDAY_ALERT = "Congé férié du Québec. Horaire spécial possible pour cette journée.";

export const DAY_CONFIG = [
  ['monday', 'Lundi', 1],
  ['tuesday', 'Mardi', 2],
  ['wednesday', 'Mercredi', 3],
  ['thursday', 'Jeudi', 4],
  ['friday', 'Vendredi', 5],
  ['saturday', 'Samedi', 6],
  ['sunday', 'Dimanche', 0],
] as const;

export const BLOCKED_SLOT_REPEAT_OPTIONS = [
  ['once', 'Une seule fois'],
  ['weekly', 'Chaque semaine'],
  ['yearly', 'Chaque année (même date)'],
  ['holiday', 'À chaque journée fériée'],
] as const;

export const QUEBEC_FIXED_HOLIDAYS = [
  ['Jour de l’an', '01-01'],
  ['Fête nationale du Québec', '06-24'],
  ['Fête du Canada', '07-01'],
  ['Noël', '12-25'],
] as const;

export const FRENCH_MONTHS: Record<number, string> = {
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
};
