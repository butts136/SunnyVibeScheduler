import { db, transaction } from '@/lib/db';
import {
  blockedSlotRepeatLabelMap,
  dateKeyInTimeZone,
  formatMonthDay,
  getReservationTimeZone,
  loadOpeningHoursPayload,
  loadReservationConfig,
  mergeWithQuebecHolidays,
  timeKeyInTimeZone,
} from '@/lib/configuration';
import { DAY_CONFIG, DEFAULT_RESERVATION_TIMEZONE, FRENCH_MONTHS } from '@/lib/constants';
import type {
  ActiveSlotRule,
  BlockedSlotRule,
  BookingRecord,
  ReservationConfig,
} from '@/lib/types';
import { isValidIsoDate, isValidMonthDay, timeTextToMinutes } from '@/lib/utils';

function formatterForTimeZone(timeZone: string) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
}

function zonedParts(date: Date, timeZone: string) {
  const parts = formatterForTimeZone(timeZone).formatToParts(date);
  const getValue = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? '0');
  return {
    year: getValue('year'),
    month: getValue('month'),
    day: getValue('day'),
    hour: getValue('hour'),
    minute: getValue('minute'),
  };
}

export function zonedDateTimeToUtc(dateKey: string, timeText: string, timeZone = DEFAULT_RESERVATION_TIMEZONE) {
  const [year, month, day] = dateKey.split('-').map(Number);
  const [hour, minute] = timeText.split(':').map(Number);
  let guess = new Date(Date.UTC(year, month - 1, day, hour, minute));

  for (let index = 0; index < 4; index += 1) {
    const parts = zonedParts(guess, timeZone);
    const desiredUtc = Date.UTC(year, month - 1, day, hour, minute);
    const actualUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute);
    const diff = desiredUtc - actualUtc;
    if (diff === 0) {
      return guess;
    }
    guess = new Date(guess.getTime() + diff);
  }

  return guess;
}

function parseStoredInstant(value: string | null | undefined, config = loadReservationConfig()) {
  if (!value) {
    return null;
  }

  const normalized = value.replace(' ', 'T');
  if (/[zZ]$|[+-]\d{2}:\d{2}$/.test(normalized)) {
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const match = normalized.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  if (!match) {
    return null;
  }

  return zonedDateTimeToUtc(match[1], match[2], getReservationTimeZone(config));
}

function localDateTimeFromStored(value: string | null | undefined, config = loadReservationConfig()) {
  const date = parseStoredInstant(value, config);
  if (!date) {
    return null;
  }
  return {
    date,
    dateKey: dateKeyInTimeZone(date, config),
    timeKey: timeKeyInTimeZone(date, config),
  };
}

function nowInReservationTimeZone(config = loadReservationConfig()) {
  return new Date();
}

function sortByStart(left: BookingRecord, right: BookingRecord) {
  return parseStoredInstant(left.startAt)!.getTime() - parseStoredInstant(right.startAt)!.getTime();
}

function allBookings() {
  const rows = db().prepare(`
    SELECT id, user_id, start, end, title, companion_count, is_private, created_at
    FROM bookings
    ORDER BY start ASC
  `).all() as Array<Record<string, unknown>>;

  return rows.map((row) => ({
    id: Number(row.id),
    userId: Number(row.user_id),
    startAt: String(row.start),
    endAt: String(row.end),
    title: row.title ? String(row.title) : null,
    companionCount: Number(row.companion_count ?? 0),
    isPrivate: Boolean(row.is_private),
    createdAt: row.created_at ? String(row.created_at) : null,
  } satisfies BookingRecord));
}

function normalizeBlockedSlotRow(row: Record<string, unknown>): BlockedSlotRule | null {
  const startTime = String(row.start_time ?? '').trim();
  const endTime = String(row.end_time ?? '').trim();
  const startMinutes = timeTextToMinutes(startTime);
  const endMinutes = timeTextToMinutes(endTime);
  if (startMinutes === null || endMinutes === null || endMinutes <= startMinutes) {
    return null;
  }

  const repeatTypeRaw = String(row.repeat_type ?? 'once').trim();
  const repeatType = ['once', 'weekly', 'yearly', 'holiday'].includes(repeatTypeRaw)
    ? (repeatTypeRaw as BlockedSlotRule['repeatType'])
    : 'once';
  const dateValue = String(row.date_value ?? '').trim();
  const monthDay = String(row.month_day ?? '').trim();
  const weekdayValue = row.weekday === null || row.weekday === undefined ? null : Number(row.weekday);
  const title = String(row.title ?? '').trim() || 'Blocage administrateur';
  const rangeStart = isValidIsoDate(String(row.range_start ?? '').trim()) ? String(row.range_start) : '';
  const rangeEnd = isValidIsoDate(String(row.range_end ?? '').trim()) ? String(row.range_end) : '';

  let description: string = blockedSlotRepeatLabelMap[repeatType] ?? repeatType;
  if (repeatType === 'once') {
    if (!isValidIsoDate(dateValue)) {
      return null;
    }
    description = `Une seule fois (${dateValue})`;
  }
  if (repeatType === 'weekly') {
    if (weekdayValue === null || weekdayValue < 0 || weekdayValue > 6) {
      return null;
    }
    const weekdayLabels = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
    description = `Chaque semaine (${weekdayLabels[weekdayValue] ?? 'Jour inconnu'})`;
  }
  if (repeatType === 'yearly') {
    if (!isValidMonthDay(monthDay)) {
      return null;
    }
    description = `Chaque année (${monthDay})`;
  }

  return {
    id: Number(row.id),
    title,
    repeatType,
    dateValue: isValidIsoDate(dateValue) ? dateValue : '',
    weekday: weekdayValue,
    monthDay: isValidMonthDay(monthDay) ? monthDay : '',
    startTime,
    endTime,
    rangeStart,
    rangeEnd,
    startMinutes,
    endMinutes,
    repeatLabel: blockedSlotRepeatLabelMap[repeatType] ?? repeatType,
    repeatDescription: description,
    createdAt: String(row.created_at ?? ''),
  };
}

export function loadBlockedSlotRules() {
  const rows = db().prepare(`
    SELECT id, title, repeat_type, date_value, weekday, month_day, start_time, end_time, range_start, range_end, created_at
    FROM blocked_slots
    ORDER BY created_at DESC, id DESC
  `).all() as Array<Record<string, unknown>>;

  return rows
    .map(normalizeBlockedSlotRow)
    .filter((row): row is BlockedSlotRule => row !== null);
}

function normalizeActiveSlotRow(row: Record<string, unknown>): ActiveSlotRule | null {
  const date = String(row.date_value ?? '').trim();
  const startTime = String(row.start_time ?? '').trim();
  const endTime = String(row.end_time ?? '').trim();
  const startMinutes = timeTextToMinutes(startTime);
  const endMinutes = timeTextToMinutes(endTime);
  if (!isValidIsoDate(date) || startMinutes === null || endMinutes === null || endMinutes <= startMinutes) {
    return null;
  }
  return {
    id: Number(row.id),
    title: String(row.title ?? '').trim() || 'Plage activée',
    date,
    startTime,
    endTime,
    startMinutes,
    endMinutes,
    createdAt: String(row.created_at ?? ''),
  };
}

export function loadActiveSlotRules() {
  const rows = db().prepare(`
    SELECT id, title, date_value, start_time, end_time, created_at
    FROM active_slots
    ORDER BY date_value ASC, start_time ASC, end_time ASC, id ASC
  `).all() as Array<Record<string, unknown>>;

  return rows
    .map(normalizeActiveSlotRow)
    .filter((row): row is ActiveSlotRule => row !== null);
}

export function loadActiveSlotWindowsForDate(dateKey: string) {
  return loadActiveSlotRules()
    .filter((row) => row.date === dateKey)
    .map((row) => ({ startMinutes: row.startMinutes, endMinutes: row.endMinutes }));
}

function specialDateForDate(dateKey: string) {
  return loadOpeningHoursPayload().specialDates.find((item) => item.date === dateKey) ?? null;
}

function holidayForDate(dateKey: string) {
  const monthDay = dateKey.slice(5);
  return mergeWithQuebecHolidays(loadOpeningHoursPayload().holidays)
    .find((item) => item.date === dateKey || item.monthDay === monthDay) ?? null;
}

function windowsForDate(dateKey: string, config = loadReservationConfig()) {
  if (config.availabilityMode === 'active_slots') {
    return loadActiveSlotWindowsForDate(dateKey);
  }

  const specialDate = specialDateForDate(dateKey);
  if (specialDate) {
    if (specialDate.closed) {
      return [];
    }
    return [{
      startMinutes: timeTextToMinutes(specialDate.start)!,
      endMinutes: timeTextToMinutes(specialDate.end)!,
    }];
  }

  const weekdayIndex = new Date(`${dateKey}T00:00:00Z`).getUTCDay();
  const dayKey = DAY_CONFIG.find(([, , jsDayIndex]) => jsDayIndex === weekdayIndex)?.[0] ?? 'monday';
  const openingHours = loadOpeningHoursPayload().openingHours[dayKey];
  if (!openingHours || openingHours.closed) {
    return [];
  }

  const startMinutes = timeTextToMinutes(openingHours.start);
  const endMinutes = timeTextToMinutes(openingHours.end);
  if (startMinutes === null || endMinutes === null || endMinutes <= startMinutes) {
    return [];
  }

  return [{ startMinutes, endMinutes }];
}

function blockedSlotAppliesToDate(rule: BlockedSlotRule, dateKey: string) {
  if (rule.rangeStart && dateKey < rule.rangeStart) {
    return false;
  }
  if (rule.rangeEnd && dateKey > rule.rangeEnd) {
    return false;
  }

  if (rule.repeatType === 'once') {
    return dateKey === rule.dateValue;
  }
  if (rule.repeatType === 'weekly') {
    const weekday = new Date(`${dateKey}T00:00:00Z`).getUTCDay();
    const mondayIndex = weekday === 0 ? 6 : weekday - 1;
    return rule.weekday === mondayIndex;
  }
  if (rule.repeatType === 'yearly') {
    return dateKey.slice(5) === rule.monthDay;
  }
  if (rule.repeatType === 'holiday') {
    return Boolean(holidayForDate(dateKey));
  }
  return false;
}

function blockedIntervalsForDate(dateKey: string) {
  return loadBlockedSlotRules()
    .filter((rule) => blockedSlotAppliesToDate(rule, dateKey))
    .map((rule) => ({
      id: rule.id,
      title: rule.title,
      startMinutes: rule.startMinutes,
      endMinutes: rule.endMinutes,
    }));
}

function bookingsForLocalDate(dateKey: string, config = loadReservationConfig()) {
  return allBookings()
    .filter((booking) => {
      const local = localDateTimeFromStored(booking.startAt, config);
      return local?.dateKey === dateKey;
    })
    .map((booking) => {
      const startLocal = localDateTimeFromStored(booking.startAt, config);
      const endLocal = localDateTimeFromStored(booking.endAt, config);
      if (!startLocal || !endLocal) {
        return null;
      }
      return {
        id: booking.id,
        userId: booking.userId,
        startMinutes: timeTextToMinutes(startLocal.timeKey) ?? 0,
        endMinutes: timeTextToMinutes(endLocal.timeKey) ?? 0,
        companionCount: booking.companionCount,
        peopleCount: booking.companionCount + 1,
        isPrivate: booking.isPrivate,
      };
    })
    .filter((row): row is NonNullable<typeof row> => row !== null);
}

function addMonths(date: Date, months: number) {
  const next = new Date(date);
  next.setUTCMonth(next.getUTCMonth() + months);
  return next;
}

function frequencyWindowStart(referenceDate: Date, unit: ReservationConfig['frequencyLimitPeriodUnit'], amount: number) {
  if (unit === 'days') {
    return new Date(referenceDate.getTime() - (amount * 24 * 60 * 60 * 1000));
  }
  if (unit === 'weeks') {
    return new Date(referenceDate.getTime() - (amount * 7 * 24 * 60 * 60 * 1000));
  }
  return addMonths(referenceDate, -amount);
}

export function validateBookingRequest(input: {
  userId: number;
  date: string;
  startTime: string;
  endTime: string;
  companionCount: number;
  isPrivate: boolean;
  excludeBookingId?: number;
}) {
  const config = loadReservationConfig();
  const dateKey = input.date;
  const startMinutes = timeTextToMinutes(input.startTime);
  const endMinutes = timeTextToMinutes(input.endTime);
  if (!isValidIsoDate(dateKey)) {
    throw new Error('Date invalide.');
  }
  if (startMinutes === null || endMinutes === null) {
    throw new Error("Heure de début ou de fin invalide.");
  }
  if (endMinutes <= startMinutes) {
    throw new Error("L'heure de fin doit être après l'heure de début.");
  }

  const windows = windowsForDate(dateKey, config);
  if (!windows.length) {
    throw new Error(config.availabilityMode === 'active_slots'
      ? "Aucune plage activée n'est disponible pour cette journée."
      : 'La salle est fermée cette journée.');
  }

  const selectedWindow = windows.find((window) => startMinutes >= window.startMinutes && endMinutes <= window.endMinutes);
  if (!selectedWindow) {
    throw new Error(config.availabilityMode === 'active_slots'
      ? 'Réservation en dehors des plages activées.'
      : "Réservation en dehors des heures d'ouverture.");
  }

  const duration = endMinutes - startMinutes;
  if (duration < config.minDurationMinutes) {
    throw new Error('Durée inférieure au minimum autorisé.');
  }
  if (duration > config.maxDurationMinutes) {
    throw new Error('Durée supérieure au maximum autorisé.');
  }
  if (input.companionCount < 0) {
    throw new Error("Le nombre d'accompagnateurs ne peut pas être négatif.");
  }
  if (input.companionCount > 0 && !config.allowCompanionBooking) {
    throw new Error("Les accompagnateurs sont désactivés. Chaque place doit être réservée par un compte utilisateur.");
  }
  if (input.isPrivate && !config.allowPrivateRoomChoice) {
    throw new Error("L'option de réservation privée n'est pas activée.");
  }
  if (config.slotIntervalEnabled && (duration % config.slotIntervalMinutes) !== 0) {
    throw new Error(`La durée doit respecter un multiple de ${config.slotIntervalMinutes} minutes.`);
  }
  if (config.fixedTimeOnly && ((startMinutes % config.fixedTimeIntervalMinutes) !== 0 || (endMinutes % config.fixedTimeIntervalMinutes) !== 0)) {
    throw new Error(`Heures fixes requises par tranches de ${config.fixedTimeIntervalMinutes} minutes.`);
  }
  if (startMinutes > (selectedWindow.endMinutes - config.latestStartBeforeCloseMinutes)) {
    throw new Error("Cette heure de début est trop proche de la fermeture.");
  }

  const userRow = db().prepare(`
    SELECT id, is_blocked, reservation_limit
    FROM users
    WHERE id = ?
    LIMIT 1
  `).get(input.userId) as Record<string, unknown> | undefined;
  if (!userRow) {
    throw new Error('Utilisateur introuvable.');
  }
  if (Boolean(userRow.is_blocked)) {
    throw new Error('Votre compte est bloqué.');
  }

  const peopleCount = input.companionCount + 1;
  if (peopleCount > config.maxSimultaneousBookings) {
    throw new Error('Le nombre total de personnes dépasse la capacité maximale.');
  }

  const now = nowInReservationTimeZone(config);
  const futureBookingsCount = allBookings()
    .filter((booking) => booking.userId === input.userId)
    .filter((booking) => {
      if (input.excludeBookingId && booking.id === input.excludeBookingId) {
        return false;
      }
      const end = parseStoredInstant(booking.endAt, config);
      return end ? end >= now : false;
    })
    .length;
  if (userRow.reservation_limit !== null && userRow.reservation_limit !== undefined && futureBookingsCount >= Number(userRow.reservation_limit)) {
    throw new Error('Vous avez atteint votre limite de réservations autorisées.');
  }

  const requestedStartUtc = zonedDateTimeToUtc(dateKey, input.startTime, getReservationTimeZone(config));
  const requestedEndUtc = zonedDateTimeToUtc(dateKey, input.endTime, getReservationTimeZone(config));

  if (config.singleBookingPerDay) {
    const existingSameDay = allBookings()
      .filter((booking) => booking.userId === input.userId)
      .filter((booking) => {
        if (input.excludeBookingId && booking.id === input.excludeBookingId) {
          return false;
        }
        const local = localDateTimeFromStored(booking.startAt, config);
        return local?.dateKey === dateKey;
      });
    if (existingSameDay.length > 0) {
      throw new Error('Limite atteinte: une seule réservation par jour est autorisée.');
    }
  }

  if (config.frequencyLimitEnabled) {
    const windowStart = frequencyWindowStart(requestedStartUtc, config.frequencyLimitPeriodUnit, config.frequencyLimitPeriodValue);
    let existingCount = 0;
    let existingHours = 0;
    for (const booking of allBookings()) {
      if (booking.userId !== input.userId) {
        continue;
      }
      if (input.excludeBookingId && booking.id === input.excludeBookingId) {
        continue;
      }
      const start = parseStoredInstant(booking.startAt, config);
      const end = parseStoredInstant(booking.endAt, config);
      if (!start || !end) {
        continue;
      }
      if (start >= windowStart && start < requestedStartUtc) {
        existingCount += 1;
        existingHours += (end.getTime() - start.getTime()) / 3_600_000;
      }
    }
    const requestedHours = (requestedEndUtc.getTime() - requestedStartUtc.getTime()) / 3_600_000;
    const periodLabel = `${config.frequencyLimitPeriodValue} ${config.frequencyLimitPeriodUnit}`;
    if (config.frequencyLimitMetric === 'bookings' && (existingCount + 1) > config.frequencyLimitValue) {
      throw new Error(`Limite atteinte: maximum ${config.frequencyLimitValue} réservation(s) par ${periodLabel}.`);
    }
    if (config.frequencyLimitMetric === 'hours' && (existingHours + requestedHours) > config.frequencyLimitValue) {
      throw new Error(`Limite atteinte: maximum ${config.frequencyLimitValue} heure(s) par ${periodLabel}.`);
    }
  }

  for (const blocked of blockedIntervalsForDate(dateKey)) {
    const overlapStart = Math.max(startMinutes, blocked.startMinutes);
    const overlapEnd = Math.min(endMinutes, blocked.endMinutes);
    if (overlapEnd > overlapStart) {
      throw new Error(`Cette plage est bloquée par l'administrateur (${blocked.title}).`);
    }
  }

  const existingForDate = bookingsForLocalDate(dateKey, config);
  if (!config.allowBackToBack) {
    for (const booking of existingForDate) {
      if (input.excludeBookingId && booking.id === input.excludeBookingId) {
        continue;
      }
      if (booking.endMinutes === startMinutes || booking.startMinutes === endMinutes) {
        throw new Error('Les réservations subséquentes ne sont pas permises.');
      }
    }
  }

  const overlapping = [];
  for (const booking of existingForDate) {
    if (input.excludeBookingId && booking.id === input.excludeBookingId) {
      continue;
    }
    const overlapStart = Math.max(startMinutes, booking.startMinutes);
    const overlapEnd = Math.min(endMinutes, booking.endMinutes);
    if (overlapEnd <= overlapStart) {
      continue;
    }
    if (booking.userId === input.userId) {
      throw new Error('Vous avez déjà une réservation qui chevauche cette plage horaire.');
    }
    overlapping.push({
      overlapStart,
      overlapEnd,
      peopleCount: booking.peopleCount,
      isPrivate: booking.isPrivate,
    });
  }

  if (input.isPrivate && overlapping.length > 0) {
    throw new Error('Réservation privée impossible: une autre réservation existe déjà sur cette plage.');
  }
  if (!input.isPrivate && overlapping.some((booking) => booking.isPrivate)) {
    throw new Error('Cette plage contient une réservation privée qui interdit le partage.');
  }

  const events: Array<[number, number]> = overlapping.flatMap((booking) => [
    [booking.overlapStart, booking.peopleCount],
    [booking.overlapEnd, -booking.peopleCount],
  ]);
  events.push([startMinutes, peopleCount], [endMinutes, -peopleCount]);
  events.sort((left, right) => {
    if (left[0] !== right[0]) {
      return left[0] - right[0];
    }
    return left[1] - right[1];
  });

  let concurrent = 0;
  for (const [, delta] of events) {
    concurrent += delta;
    if (concurrent > config.maxSimultaneousBookings) {
      throw new Error('Capacité maximale atteinte sur cette plage horaire.');
    }
  }

  return {
    startAt: requestedStartUtc.toISOString(),
    endAt: requestedEndUtc.toISOString(),
    config,
  };
}

export function createBooking(input: {
  userId: number;
  date: string;
  startTime: string;
  endTime: string;
  title: string;
  companionCount: number;
  isPrivate: boolean;
}) {
  const validated = validateBookingRequest(input);
  db().prepare(`
    INSERT INTO bookings (user_id, start, end, title, allow_companion, companion_count, is_private, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    input.userId,
    validated.startAt,
    validated.endAt,
    input.title.trim() || null,
    input.companionCount > 0 ? 1 : 0,
    input.companionCount,
    input.isPrivate ? 1 : 0,
    new Date().toISOString(),
  );
}

export function updateBooking(input: {
  bookingId: number;
  userId: number;
  date: string;
  startTime: string;
  endTime: string;
  title: string;
  companionCount: number;
  isPrivate: boolean;
}) {
  const row = db().prepare(`
    SELECT id
    FROM bookings
    WHERE id = ? AND user_id = ?
    LIMIT 1
  `).get(input.bookingId, input.userId);
  if (!row) {
    throw new Error('Réservation introuvable.');
  }

  const validated = validateBookingRequest({
    ...input,
    excludeBookingId: input.bookingId,
  });
  db().prepare(`
    UPDATE bookings
    SET start = ?, end = ?, title = ?, allow_companion = ?, companion_count = ?, is_private = ?
    WHERE id = ? AND user_id = ?
  `).run(
    validated.startAt,
    validated.endAt,
    input.title.trim() || null,
    input.companionCount > 0 ? 1 : 0,
    input.companionCount,
    input.isPrivate ? 1 : 0,
    input.bookingId,
    input.userId,
  );
}

export function deleteBookingForUser(bookingId: number, userId: number) {
  db().prepare('DELETE FROM bookings WHERE id = ? AND user_id = ?').run(bookingId, userId);
}

export function deleteBookingForAdmin(bookingId: number) {
  db().prepare('DELETE FROM bookings WHERE id = ?').run(bookingId);
}

export function listBookingsForCalendar(config = loadReservationConfig()) {
  const result: Record<string, Array<{ bookingId: number; start: string; end: string; peopleCount: number; isPrivate: boolean }>> = {};
  for (const booking of allBookings()) {
    const start = localDateTimeFromStored(booking.startAt, config);
    const end = localDateTimeFromStored(booking.endAt, config);
    if (!start || !end) {
      continue;
    }
    result[start.dateKey] ??= [];
    result[start.dateKey].push({
      bookingId: booking.id,
      start: start.timeKey,
      end: end.timeKey,
      peopleCount: booking.companionCount + 1,
      isPrivate: booking.isPrivate,
    });
  }
  return result;
}

export function listBookingsForUser(userId: number, config = loadReservationConfig()) {
  const now = nowInReservationTimeZone(config);
  return allBookings()
    .filter((booking) => booking.userId === userId)
    .sort(sortByStart)
    .map((booking) => {
      const start = localDateTimeFromStored(booking.startAt, config);
      const end = localDateTimeFromStored(booking.endAt, config);
      if (!start || !end) {
        return null;
      }
      return {
        id: booking.id,
        dateKey: start.dateKey,
        dateLabel: start.dateKey,
        startTime: start.timeKey,
        endTime: end.timeKey,
        title: booking.title ?? '',
        companionCount: booking.companionCount,
        peopleCount: booking.companionCount + 1,
        isPrivate: booking.isPrivate,
        createdAt: booking.createdAt ?? '',
        isPast: end.date < now,
      };
    })
    .filter((row): row is NonNullable<typeof row> => row !== null);
}

export function listBookingsForAdmin(config = loadReservationConfig()) {
  const rows = db().prepare(`
    SELECT
      b.id,
      b.user_id,
      b.start,
      b.end,
      b.title,
      b.companion_count,
      b.is_private,
      b.created_at,
      u.full_name,
      u.email,
      u.phone
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    ORDER BY b.start ASC
  `).all() as Array<Record<string, unknown>>;

  const now = nowInReservationTimeZone(config);
  const todayKey = dateKeyInTimeZone(now, config);
  return rows
    .map((row) => {
      const start = localDateTimeFromStored(String(row.start), config);
      const end = localDateTimeFromStored(String(row.end), config);
      if (!start || !end) {
        return null;
      }
      const isPastToday = start.dateKey === todayKey && end.date < now;
      const monthDate = new Date(`${start.dateKey}T00:00:00Z`);
      return {
        id: Number(row.id),
        userId: Number(row.user_id),
        startDisplay: `${start.dateKey} ${start.timeKey}`,
        endDisplay: `${end.dateKey} ${end.timeKey}`,
        dateKey: start.dateKey,
        dateTitle: `${monthDate.getUTCDate()} ${FRENCH_MONTHS[monthDate.getUTCMonth() + 1] ?? ''}`.trim(),
        startTime: start.timeKey,
        endTime: end.timeKey,
        title: row.title ? String(row.title) : '',
        companionCount: Number(row.companion_count ?? 0),
        peopleCount: Number(row.companion_count ?? 0) + 1,
        isPrivate: Boolean(row.is_private),
        userName: row.full_name ? String(row.full_name) : '',
        userEmail: row.email ? String(row.email) : '',
        userPhone: row.phone ? String(row.phone) : '',
        createdAt: row.created_at ? String(row.created_at) : '',
        isPastToday,
      };
    })
    .filter((row): row is NonNullable<typeof row> => row !== null);
}

export function listUsersForAdmin(config = loadReservationConfig()) {
  const users = db().prepare(`
    SELECT id, full_name, email, phone, birth_date, created_at, is_blocked, reservation_limit
    FROM users
    ORDER BY created_at DESC
  `).all() as Array<Record<string, unknown>>;

  const allAdminBookings = listBookingsForAdmin(config);
  const now = nowInReservationTimeZone(config);

  return users.map((row) => {
    const userBookings = allAdminBookings.filter((booking) => booking.userId === Number(row.id));
    const nextBooking = userBookings.find((booking) => {
      const start = parseStoredInstant(`${booking.dateKey}T${booking.startTime}`, config);
      return start ? start >= now : false;
    });
    const lastBooking = [...userBookings].reverse()[0];
    const fullName = row.full_name ? String(row.full_name) : '';
    const [firstName = '', ...rest] = fullName.trim().split(/\s+/).filter(Boolean);
    return {
      id: Number(row.id),
      fullName,
      firstName,
      lastName: rest.join(' '),
      email: row.email ? String(row.email) : '',
      phone: row.phone ? String(row.phone) : '',
      birthDate: row.birth_date ? String(row.birth_date) : '',
      createdAt: row.created_at ? String(row.created_at) : '',
      isBlocked: Boolean(row.is_blocked),
      reservationLimit: row.reservation_limit === null || row.reservation_limit === undefined ? null : Number(row.reservation_limit),
      bookingCount: userBookings.length,
      lastBookingStart: lastBooking ? `${lastBooking.dateKey} ${lastBooking.startTime}` : '',
      nextBookingStart: nextBooking ? `${nextBooking.dateKey} ${nextBooking.startTime}` : '',
      recentBookings: userBookings.slice(-5).reverse().map((booking) => ({
        startDisplay: `${booking.dateKey} ${booking.startTime}`,
        endDisplay: `${booking.dateKey} ${booking.endTime}`,
        title: booking.title,
      })),
    };
  });
}

export function createBlockedSlot(input: {
  title: string;
  repeatType: 'once' | 'weekly' | 'yearly' | 'holiday';
  referenceDate: string;
  startTime: string;
  endTime: string;
  rangeStart: string;
  rangeEnd: string;
}) {
  const startMinutes = timeTextToMinutes(input.startTime);
  const endMinutes = timeTextToMinutes(input.endTime);
  if (startMinutes === null || endMinutes === null || endMinutes <= startMinutes) {
    throw new Error("L'heure de fin doit être après l'heure de début.");
  }

  let dateValue: string | null = null;
  let weekday: number | null = null;
  let monthDay: string | null = null;
  if (input.repeatType !== 'holiday' && !isValidIsoDate(input.referenceDate)) {
    throw new Error('Date de référence invalide.');
  }
  if (input.repeatType === 'once') {
    dateValue = input.referenceDate;
  }
  if (input.repeatType === 'weekly') {
    const day = new Date(`${input.referenceDate}T00:00:00Z`).getUTCDay();
    weekday = day === 0 ? 6 : day - 1;
  }
  if (input.repeatType === 'yearly') {
    monthDay = input.referenceDate.slice(5);
  }

  db().prepare(`
    INSERT INTO blocked_slots (title, repeat_type, date_value, weekday, month_day, start_time, end_time, range_start, range_end, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    input.title.trim() || null,
    input.repeatType,
    dateValue,
    weekday,
    monthDay,
    input.startTime,
    input.endTime,
    input.rangeStart || null,
    input.rangeEnd || null,
    new Date().toISOString(),
  );
}

export function deleteBlockedSlot(blockedSlotId: number) {
  db().prepare('DELETE FROM blocked_slots WHERE id = ?').run(blockedSlotId);
}

export function createActiveSlot(input: {
  title: string;
  date: string;
  startTime: string;
  endTime: string;
}) {
  const startMinutes = timeTextToMinutes(input.startTime);
  const endMinutes = timeTextToMinutes(input.endTime);
  if (!isValidIsoDate(input.date)) {
    throw new Error('Date de plage activée invalide.');
  }
  if (startMinutes === null || endMinutes === null || endMinutes <= startMinutes) {
    throw new Error('La plage activée doit se terminer après son début.');
  }
  db().prepare(`
    INSERT INTO active_slots (title, date_value, start_time, end_time, created_at)
    VALUES (?, ?, ?, ?, ?)
  `).run(input.title.trim() || null, input.date, input.startTime, input.endTime, new Date().toISOString());
}

export function deleteActiveSlot(activeSlotId: number) {
  db().prepare('DELETE FROM active_slots WHERE id = ?').run(activeSlotId);
}

export function setUserBlocked(userId: number, blocked: boolean) {
  db().prepare('UPDATE users SET is_blocked = ? WHERE id = ?').run(blocked ? 1 : 0, userId);
}

export function setUserReservationLimit(userId: number, limit: number | null) {
  db().prepare('UPDATE users SET reservation_limit = ? WHERE id = ?').run(limit, userId);
}

export function deleteUserAccount(userId: number) {
  transaction(() => {
    db().prepare('DELETE FROM bookings WHERE user_id = ?').run(userId);
    db().prepare('DELETE FROM password_reset_tokens WHERE user_id = ?').run(userId);
    db().prepare('DELETE FROM users WHERE id = ?').run(userId);
  });
}

export function listInvitationCodes(limit = 30) {
  return db().prepare(`
    SELECT id, code, expires_at, used_at, created_at
    FROM invitation_codes
    ORDER BY created_at DESC
    LIMIT ?
  `).all(limit) as Array<{ id: number; code: string; expires_at: string; used_at: string | null; created_at: string }>;
}

export function generateInvitationCode(validityDays: number) {
  if (!Number.isInteger(validityDays) || validityDays < 1 || validityDays > 365) {
    throw new Error('Durée invalide. Utilisez un nombre de jours >= 1.');
  }

  for (let attempt = 0; attempt < 20; attempt += 1) {
    const code = `${Math.floor(Math.random() * 1_000_000)}`.padStart(6, '0');
    const expiresAt = new Date(Date.now() + (validityDays * 24 * 60 * 60 * 1000)).toISOString();
    try {
      db().prepare(`
        INSERT INTO invitation_codes (code, expires_at, created_at)
        VALUES (?, ?, ?)
      `).run(code, expiresAt, new Date().toISOString());
      return { code, expiresAt };
    } catch {
      continue;
    }
  }

  throw new Error("Impossible de générer un code d'invitation unique.");
}

export function deleteInvitationCode(codeId: number) {
  db().prepare('DELETE FROM invitation_codes WHERE id = ?').run(codeId);
}

export function groupBookingsByDate(bookings = listBookingsForAdmin()) {
  const grouped = new Map<string, { dateKey: string; dateTitle: string; items: typeof bookings; upcomingItems: typeof bookings; pastTodayItems: typeof bookings }>();
  for (const booking of bookings) {
    if (!grouped.has(booking.dateKey)) {
      grouped.set(booking.dateKey, {
        dateKey: booking.dateKey,
        dateTitle: booking.dateTitle,
        items: [],
        upcomingItems: [],
        pastTodayItems: [],
      });
    }
    const group = grouped.get(booking.dateKey)!;
    group.items.push(booking);
    if (booking.isPastToday) {
      group.pastTodayItems.push(booking);
    } else {
      group.upcomingItems.push(booking);
    }
  }
  return Array.from(grouped.values());
}

export function formatBookingDateLabel(dateKey: string) {
  return formatMonthDay(dateKey);
}

export function buildCalendarDays(daysAhead = 42, config = loadReservationConfig()) {
  const calendarBookings = listBookingsForCalendar(config);
  const holidays = mergeWithQuebecHolidays(loadOpeningHoursPayload().holidays);
  const today = new Date();
  const result = [];

  for (let offset = 0; offset < daysAhead; offset += 1) {
    const current = new Date(today.getTime() + (offset * 24 * 60 * 60 * 1000));
    const dateKey = dateKeyInTimeZone(current, config);
    const date = new Date(`${dateKey}T00:00:00Z`);
    const windows = windowsForDate(dateKey, config);
    const bookings = calendarBookings[dateKey] ?? [];
    const totalWindowMinutes = windows.reduce((sum, item) => sum + (item.endMinutes - item.startMinutes), 0);
    const remainingCapacity = Math.max(
      0,
      config.maxSimultaneousBookings - Math.max(...bookings.map((booking) => booking.peopleCount), 0),
    );
    const holiday = holidays.find((item) => item.date === dateKey || item.monthDay === dateKey.slice(5)) ?? null;

    result.push({
      dateKey,
      label: `${date.getUTCDate()} ${FRENCH_MONTHS[date.getUTCMonth() + 1] ?? ''}`.trim(),
      weekday: new Intl.DateTimeFormat('fr-CA', { weekday: 'long' }).format(date),
      windows: windows.map((item) => ({
        start: item.startMinutes,
        end: item.endMinutes,
      })),
      bookings,
      totalWindowMinutes,
      remainingCapacity,
      holiday,
      closed: totalWindowMinutes === 0,
    });
  }

  return result;
}
