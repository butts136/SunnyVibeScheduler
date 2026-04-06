import fs from 'node:fs';

import {
  BLOCKED_SLOT_REPEAT_OPTIONS,
  DAY_CONFIG,
  DEFAULT_HOLIDAY_ALERT,
  DEFAULT_RESERVATION_TIMEZONE,
  FRENCH_MONTHS,
  INVITATION_CONFIG_PATH,
  OPENING_HOURS_PATH,
  QUEBEC_FIXED_HOLIDAYS,
  RESERVATION_CONFIG_PATH,
  VALID_SLOT_INTERVALS,
} from '@/lib/constants';
import type {
  HolidayConfig,
  InvitationConfig,
  OpeningHours,
  ReservationConfig,
  SpecialDateConfig,
} from '@/lib/types';
import { isValidIsoDate, isValidMonthDay, timeTextToMinutes } from '@/lib/utils';

export function defaultOpeningHours(): OpeningHours {
  return {
    monday: { closed: false, start: '09:00', end: '17:00' },
    tuesday: { closed: false, start: '08:00', end: '14:00' },
    wednesday: { closed: false, start: '10:00', end: '18:00' },
    thursday: { closed: false, start: '09:00', end: '15:00' },
    friday: { closed: false, start: '09:00', end: '16:00' },
    saturday: { closed: false, start: '10:00', end: '13:00' },
    sunday: { closed: true, start: '09:00', end: '09:00' },
  };
}

export function normalizeOpeningHours(rawValue: unknown): OpeningHours {
  const normalized = defaultOpeningHours();
  if (!rawValue || typeof rawValue !== 'object') {
    return normalized;
  }

  for (const [dayKey] of DAY_CONFIG) {
    const dayValue = (rawValue as Record<string, unknown>)[dayKey];
    if (!dayValue || typeof dayValue !== 'object') {
      continue;
    }

    const closed = Boolean((dayValue as Record<string, unknown>).closed);
    const start = String((dayValue as Record<string, unknown>).start ?? normalized[dayKey].start);
    const end = String((dayValue as Record<string, unknown>).end ?? normalized[dayKey].end);

    normalized[dayKey] = {
      closed,
      start: timeTextToMinutes(start) === null ? normalized[dayKey].start : start,
      end: timeTextToMinutes(end) === null ? normalized[dayKey].end : end,
    };
  }

  return normalized;
}

export function normalizeHolidays(rawValue: unknown): HolidayConfig[] {
  if (!Array.isArray(rawValue)) {
    return [];
  }

  const rows: HolidayConfig[] = [];
  for (const item of rawValue) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const row = item as Record<string, unknown>;
    const name = String(row.name ?? '').trim();
    const date = String(row.date ?? '').trim();
    const monthDay = String(row.month_day ?? '').trim();
    const alert = String(row.alert ?? '').trim();
    if (!name) {
      continue;
    }
    if (!isValidIsoDate(date) && !isValidMonthDay(monthDay)) {
      continue;
    }
    rows.push({
      name,
      date: isValidIsoDate(date) ? date : '',
      monthDay: isValidMonthDay(monthDay) ? monthDay : '',
      alert: alert || DEFAULT_HOLIDAY_ALERT,
    });
  }
  return rows;
}

export function normalizeSpecialDates(rawValue: unknown): SpecialDateConfig[] {
  if (!Array.isArray(rawValue)) {
    return [];
  }

  const map = new Map<string, SpecialDateConfig>();
  for (const item of rawValue) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const row = item as Record<string, unknown>;
    const date = String(row.date ?? '').trim();
    if (!isValidIsoDate(date)) {
      continue;
    }
    const closed = Boolean(row.closed);
    const start = String(row.start ?? '09:00').trim();
    const end = String(row.end ?? '17:00').trim();
    const reason = String(row.reason ?? '').trim();

    if (!closed) {
      const startMinutes = timeTextToMinutes(start);
      const endMinutes = timeTextToMinutes(end);
      if (startMinutes === null || endMinutes === null || endMinutes <= startMinutes) {
        continue;
      }
    }

    map.set(date, {
      date,
      closed,
      start: closed ? '00:00' : start,
      end: closed ? '00:00' : end,
      reason,
    });
  }

  return Array.from(map.values()).sort((left, right) => left.date.localeCompare(right.date));
}

export function defaultReservationConfig(): ReservationConfig {
  return {
    timezone: DEFAULT_RESERVATION_TIMEZONE,
    availabilityMode: 'opening_hours',
    weekStartDay: 'sunday',
    warningDisplayCount: 4,
    sunnygymDisplayMode: 'calendar',
    maxSimultaneousBookings: 3,
    minDurationMinutes: 30,
    maxDurationMinutes: 120,
    latestStartBeforeCloseMinutes: 30,
    slotIntervalEnabled: true,
    slotIntervalMinutes: 30,
    allowBackToBack: true,
    fixedTimeOnly: true,
    fixedTimeIntervalMinutes: 15,
    allowCompanionBooking: true,
    allowPrivateRoomChoice: false,
    singleBookingPerDay: false,
    frequencyLimitEnabled: false,
    frequencyLimitMetric: 'bookings',
    frequencyLimitValue: 3,
    frequencyLimitPeriodValue: 1,
    frequencyLimitPeriodUnit: 'weeks',
  };
}

export function normalizeReservationConfig(rawValue: unknown): ReservationConfig {
  const defaults = defaultReservationConfig();
  if (!rawValue || typeof rawValue !== 'object') {
    return defaults;
  }

  const row = rawValue as Record<string, unknown>;

  const parseNumber = (value: unknown, fallback: number) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const slotInterval = VALID_SLOT_INTERVALS.includes(parseNumber(row.slot_interval_minutes, defaults.slotIntervalMinutes) as 15 | 30 | 60)
    ? (parseNumber(row.slot_interval_minutes, defaults.slotIntervalMinutes) as 15 | 30 | 60)
    : defaults.slotIntervalMinutes;
  const fixedInterval = VALID_SLOT_INTERVALS.includes(parseNumber(row.fixed_time_interval_minutes, defaults.fixedTimeIntervalMinutes) as 15 | 30 | 60)
    ? (parseNumber(row.fixed_time_interval_minutes, defaults.fixedTimeIntervalMinutes) as 15 | 30 | 60)
    : defaults.fixedTimeIntervalMinutes;
  const timezone = String(row.timezone ?? defaults.timezone).trim() || defaults.timezone;
  const availabilityMode = String(row.availability_mode ?? defaults.availabilityMode).trim().toLowerCase() === 'active_slots'
    ? 'active_slots'
    : 'opening_hours';
  const weekStartDay = String(row.week_start_day ?? defaults.weekStartDay).trim().toLowerCase() === 'monday'
    ? 'monday'
    : 'sunday';
  const warningDisplayCount = Math.max(1, parseNumber(row.warning_display_count, defaults.warningDisplayCount));
  const sunnygymDisplayMode = String(row.sunnygym_display_mode ?? defaults.sunnygymDisplayMode).trim().toLowerCase() === 'cards'
    ? 'cards'
    : 'calendar';

  return {
    timezone,
    availabilityMode,
    weekStartDay,
    warningDisplayCount,
    sunnygymDisplayMode,
    maxSimultaneousBookings: Math.max(1, parseNumber(row.max_simultaneous_bookings, defaults.maxSimultaneousBookings)),
    minDurationMinutes: Math.max(1, parseNumber(row.min_duration_minutes, defaults.minDurationMinutes)),
    maxDurationMinutes: Math.max(
      Math.max(1, parseNumber(row.min_duration_minutes, defaults.minDurationMinutes)),
      parseNumber(row.max_duration_minutes, defaults.maxDurationMinutes),
    ),
    latestStartBeforeCloseMinutes: Math.max(0, parseNumber(row.latest_start_before_close_minutes, defaults.latestStartBeforeCloseMinutes)),
    slotIntervalEnabled: Boolean(row.slot_interval_enabled ?? defaults.slotIntervalEnabled),
    slotIntervalMinutes: slotInterval,
    allowBackToBack: Boolean(row.allow_back_to_back ?? defaults.allowBackToBack),
    fixedTimeOnly: Boolean(row.fixed_time_only ?? defaults.fixedTimeOnly),
    fixedTimeIntervalMinutes: fixedInterval,
    allowCompanionBooking: Boolean(row.allow_companion_booking ?? defaults.allowCompanionBooking),
    allowPrivateRoomChoice: Boolean(row.allow_private_room_choice ?? defaults.allowPrivateRoomChoice),
    singleBookingPerDay: Boolean(row.single_booking_per_day ?? defaults.singleBookingPerDay),
    frequencyLimitEnabled: Boolean(row.frequency_limit_enabled ?? defaults.frequencyLimitEnabled),
    frequencyLimitMetric: String(row.frequency_limit_metric ?? defaults.frequencyLimitMetric).trim().toLowerCase() === 'hours' ? 'hours' : 'bookings',
    frequencyLimitValue: Math.max(1, parseNumber(row.frequency_limit_value, defaults.frequencyLimitValue)),
    frequencyLimitPeriodValue: Math.max(1, parseNumber(row.frequency_limit_period_value, defaults.frequencyLimitPeriodValue)),
    frequencyLimitPeriodUnit: ['days', 'weeks', 'months'].includes(String(row.frequency_limit_period_unit ?? defaults.frequencyLimitPeriodUnit))
      ? (String(row.frequency_limit_period_unit ?? defaults.frequencyLimitPeriodUnit) as 'days' | 'weeks' | 'months')
      : defaults.frequencyLimitPeriodUnit,
  };
}

export function defaultInvitationConfig(): InvitationConfig {
  return {
    customCodeEnabled: false,
    customCode: '',
    oneTimeValidityDays: 15,
  };
}

export function normalizeInvitationConfig(rawValue: unknown): InvitationConfig {
  const defaults = defaultInvitationConfig();
  if (!rawValue || typeof rawValue !== 'object') {
    return defaults;
  }
  const row = rawValue as Record<string, unknown>;
  const validity = Number(row.one_time_validity_days);
  return {
    customCodeEnabled: Boolean(row.custom_code_enabled),
    customCode: String(row.custom_code ?? '').trim().slice(0, 32),
    oneTimeValidityDays: Number.isFinite(validity) ? Math.max(1, Math.min(365, validity)) : defaults.oneTimeValidityDays,
  };
}

function readJson(path: string) {
  if (!fs.existsSync(path)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(path, 'utf8'));
  } catch {
    return null;
  }
}

function writeJson(path: string, payload: unknown) {
  fs.writeFileSync(path, JSON.stringify(payload, null, 2), 'utf8');
}

export function loadOpeningHoursPayload() {
  const raw = readJson(OPENING_HOURS_PATH);
  const record = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const openingHours = normalizeOpeningHours(record.opening_hours ?? record);
  const holidays = normalizeHolidays(record.holidays);
  const specialDates = normalizeSpecialDates(record.special_dates);
  return {
    updatedAt: String(record.updated_at ?? new Date().toISOString()),
    openingHours,
    holidays,
    specialDates,
  };
}

export function saveOpeningHoursPayload(payload: {
  openingHours?: OpeningHours;
  holidays?: HolidayConfig[];
  specialDates?: SpecialDateConfig[];
}) {
  const current = loadOpeningHoursPayload();
  writeJson(OPENING_HOURS_PATH, {
    updated_at: new Date().toISOString(),
    opening_hours: normalizeOpeningHours(payload.openingHours ?? current.openingHours),
    holidays: normalizeHolidays(payload.holidays ?? current.holidays),
    special_dates: normalizeSpecialDates(payload.specialDates ?? current.specialDates).map((item) => ({
      date: item.date,
      closed: item.closed,
      start: item.start,
      end: item.end,
      reason: item.reason,
    })),
  });
}

export function loadReservationConfig() {
  const raw = readJson(RESERVATION_CONFIG_PATH);
  const record = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return normalizeReservationConfig(record.reservation_config ?? record);
}

export function saveReservationConfig(config: ReservationConfig) {
  writeJson(RESERVATION_CONFIG_PATH, {
    updated_at: new Date().toISOString(),
    reservation_config: {
      timezone: config.timezone,
      availability_mode: config.availabilityMode,
      week_start_day: config.weekStartDay,
      warning_display_count: config.warningDisplayCount,
      sunnygym_display_mode: config.sunnygymDisplayMode,
      max_simultaneous_bookings: config.maxSimultaneousBookings,
      min_duration_minutes: config.minDurationMinutes,
      max_duration_minutes: config.maxDurationMinutes,
      latest_start_before_close_minutes: config.latestStartBeforeCloseMinutes,
      slot_interval_enabled: config.slotIntervalEnabled,
      slot_interval_minutes: config.slotIntervalMinutes,
      allow_back_to_back: config.allowBackToBack,
      fixed_time_only: config.fixedTimeOnly,
      fixed_time_interval_minutes: config.fixedTimeIntervalMinutes,
      allow_companion_booking: config.allowCompanionBooking,
      allow_private_room_choice: config.allowPrivateRoomChoice,
      single_booking_per_day: config.singleBookingPerDay,
      frequency_limit_enabled: config.frequencyLimitEnabled,
      frequency_limit_metric: config.frequencyLimitMetric,
      frequency_limit_value: config.frequencyLimitValue,
      frequency_limit_period_value: config.frequencyLimitPeriodValue,
      frequency_limit_period_unit: config.frequencyLimitPeriodUnit,
    },
  });
}

export function loadInvitationConfig() {
  const raw = readJson(INVITATION_CONFIG_PATH);
  const record = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return normalizeInvitationConfig(record.invitation_config ?? record);
}

export function saveInvitationConfig(config: InvitationConfig) {
  writeJson(INVITATION_CONFIG_PATH, {
    updated_at: new Date().toISOString(),
    invitation_config: {
      custom_code_enabled: config.customCodeEnabled,
      custom_code: config.customCode,
      one_time_validity_days: config.oneTimeValidityDays,
    },
  });
}

function calculateEasterSunday(year: number) {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = ((19 * a) + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + (2 * e) + (2 * i) - h - k) % 7;
  const m = Math.floor((a + (11 * h) + (22 * l)) / 451);
  const month = Math.floor((h + l - (7 * m) + 114) / 31);
  const day = ((h + l - (7 * m) + 114) % 31) + 1;
  return new Date(Date.UTC(year, month - 1, day));
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function dateKey(date: Date) {
  return date.toISOString().slice(0, 10);
}

function firstWeekdayInMonth(year: number, monthIndex: number, weekday: number) {
  const date = new Date(Date.UTC(year, monthIndex, 1));
  while (date.getUTCDay() !== weekday) {
    date.setUTCDate(date.getUTCDate() + 1);
  }
  return date;
}

function nthWeekdayInMonth(year: number, monthIndex: number, weekday: number, nth: number) {
  const first = firstWeekdayInMonth(year, monthIndex, weekday);
  const next = new Date(first);
  next.setUTCDate(next.getUTCDate() + (Math.max(nth - 1, 0) * 7));
  return next;
}

export function mergeWithQuebecHolidays(holidays: HolidayConfig[]) {
  const nowYear = new Date().getUTCFullYear();
  const generated: HolidayConfig[] = [];

  for (const [name, monthDay] of QUEBEC_FIXED_HOLIDAYS) {
    generated.push({ name, date: '', monthDay, alert: DEFAULT_HOLIDAY_ALERT });
  }

  for (let year = nowYear - 1; year <= nowYear + 10; year += 1) {
    const easter = calculateEasterSunday(year);
    const patriots = new Date(Date.UTC(year, 4, 24));
    while (patriots.getUTCDay() !== 1) {
      patriots.setUTCDate(patriots.getUTCDate() - 1);
    }

    const dynamicRows: Array<[string, string]> = [
      ['Vendredi saint', dateKey(addDays(easter, -2))],
      ['Lundi de Pâques', dateKey(addDays(easter, 1))],
      ['Journée nationale des Patriotes', dateKey(patriots)],
      ['Fête du Travail', dateKey(firstWeekdayInMonth(year, 8, 1))],
      ['Action de grâce', dateKey(nthWeekdayInMonth(year, 9, 1, 2))],
    ];

    for (const [name, date] of dynamicRows) {
      generated.push({ name, date, monthDay: '', alert: DEFAULT_HOLIDAY_ALERT });
    }
  }

  const byKey = new Map<string, HolidayConfig>();
  for (const item of generated) {
    byKey.set(item.date ? `date:${item.date}` : `month:${item.monthDay}`, item);
  }
  for (const item of holidays) {
    byKey.set(item.date ? `date:${item.date}` : `month:${item.monthDay}`, item);
  }

  return Array.from(byKey.values()).sort((left, right) => {
    const leftKey = left.date || `99-${left.monthDay}`;
    const rightKey = right.date || `99-${right.monthDay}`;
    return leftKey.localeCompare(rightKey);
  });
}

export function getReservationTimeZone(config = loadReservationConfig()) {
  return config.timezone || DEFAULT_RESERVATION_TIMEZONE;
}

export function formatDateTimeInTimeZone(date: Date, config = loadReservationConfig()) {
  return new Intl.DateTimeFormat('fr-CA', {
    timeZone: getReservationTimeZone(config),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(date);
}

export function dateKeyInTimeZone(date: Date, config = loadReservationConfig()) {
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: getReservationTimeZone(config),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

export function timeKeyInTimeZone(date: Date, config = loadReservationConfig()) {
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: getReservationTimeZone(config),
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(date);
}

export function formatMonthDay(dateKeyText: string) {
  const date = new Date(`${dateKeyText}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return dateKeyText;
  }
  return `${date.getUTCDate()} ${FRENCH_MONTHS[date.getUTCMonth() + 1] ?? ''}`.trim();
}

export const blockedSlotRepeatLabelMap = Object.fromEntries(BLOCKED_SLOT_REPEAT_OPTIONS);
