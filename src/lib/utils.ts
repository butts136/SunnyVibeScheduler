import { randomBytes, timingSafeEqual } from 'node:crypto';

export function toBase64Url(input: Buffer | string) {
  const buffer = Buffer.isBuffer(input) ? input : Buffer.from(input, 'utf8');
  return buffer.toString('base64url');
}

export function fromBase64Url(input: string) {
  return Buffer.from(input, 'base64url');
}

export function secureCompare(left: string, right: string) {
  const leftBuffer = Buffer.from(left, 'utf8');
  const rightBuffer = Buffer.from(right, 'utf8');
  if (leftBuffer.length !== rightBuffer.length) {
    return false;
  }
  return timingSafeEqual(leftBuffer, rightBuffer);
}

export function randomToken(size = 32) {
  return randomBytes(size).toString('hex');
}

export function normalizeEmail(value: string) {
  const normalized = value.trim().toLowerCase();
  return normalized || null;
}

export function normalizePhone(value: string) {
  const normalized = value.trim();
  return normalized || null;
}

export function isValidIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value);
}

export function isValidMonthDay(value: string) {
  if (!/^\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const date = new Date(`2000-${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(5, 10) === value;
}

export function timeTextToMinutes(value: string) {
  if (!/^\d{2}:\d{2}$/.test(value)) {
    return null;
  }
  const [hourText, minuteText] = value.split(':');
  const hour = Number(hourText);
  const minute = Number(minuteText);
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) {
    return null;
  }
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    return null;
  }
  return (hour * 60) + minute;
}

export function minutesToTimeText(minutes: number) {
  const safe = Math.max(0, Math.min(minutes, (24 * 60) - 1));
  const hour = Math.floor(safe / 60);
  const minute = safe % 60;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

export function parseStoredDateTime(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  const normalized = value.replace(' ', 'T');
  const date = new Date(normalized);
  if (!Number.isNaN(date.getTime())) {
    return date;
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(normalized)) {
    const localDate = new Date(`${normalized}:00`);
    if (!Number.isNaN(localDate.getTime())) {
      return localDate;
    }
  }
  return null;
}

export function redirectMessage(kind: 'error' | 'success', text: string) {
  return new URLSearchParams({ [kind]: text }).toString();
}
