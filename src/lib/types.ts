export type Role = 'admin' | 'user';

export type SessionPayload = {
  role: Role;
  subjectId: number;
  csrfToken: string;
  expiresAt: number;
};

export type AuthUser = {
  id: number;
  email: string | null;
  phone: string | null;
  fullName: string | null;
  birthDate: string | null;
  passwordHash: string;
  isBlocked: boolean;
  reservationLimit: number | null;
  createdAt: string | null;
};

export type AuthAdmin = {
  id: number;
  email: string;
  passwordHash: string;
  createdAt: string | null;
};

export type BookingRecord = {
  id: number;
  userId: number;
  startAt: string;
  endAt: string;
  title: string | null;
  companionCount: number;
  isPrivate: boolean;
  createdAt: string | null;
};

export type InvitationConfig = {
  customCodeEnabled: boolean;
  customCode: string;
  oneTimeValidityDays: number;
};

export type ReservationConfig = {
  timezone: string;
  availabilityMode: 'opening_hours' | 'active_slots';
  weekStartDay: 'sunday' | 'monday';
  warningDisplayCount: number;
  sunnygymDisplayMode: 'calendar' | 'cards';
  maxSimultaneousBookings: number;
  minDurationMinutes: number;
  maxDurationMinutes: number;
  latestStartBeforeCloseMinutes: number;
  slotIntervalEnabled: boolean;
  slotIntervalMinutes: 15 | 30 | 60;
  allowBackToBack: boolean;
  fixedTimeOnly: boolean;
  fixedTimeIntervalMinutes: 15 | 30 | 60;
  allowCompanionBooking: boolean;
  allowPrivateRoomChoice: boolean;
  singleBookingPerDay: boolean;
  frequencyLimitEnabled: boolean;
  frequencyLimitMetric: 'bookings' | 'hours';
  frequencyLimitValue: number;
  frequencyLimitPeriodValue: number;
  frequencyLimitPeriodUnit: 'days' | 'weeks' | 'months';
};

export type DayOpeningHours = {
  closed: boolean;
  start: string;
  end: string;
};

export type OpeningHours = Record<string, DayOpeningHours>;

export type HolidayConfig = {
  name: string;
  date: string;
  monthDay: string;
  alert: string;
};

export type SpecialDateConfig = {
  date: string;
  closed: boolean;
  start: string;
  end: string;
  reason: string;
};

export type BlockedSlotRule = {
  id: number;
  title: string;
  repeatType: 'once' | 'weekly' | 'yearly' | 'holiday';
  dateValue: string;
  weekday: number | null;
  monthDay: string;
  startTime: string;
  endTime: string;
  rangeStart: string;
  rangeEnd: string;
  startMinutes: number;
  endMinutes: number;
  repeatLabel: string;
  repeatDescription: string;
  createdAt: string;
};

export type ActiveSlotRule = {
  id: number;
  title: string;
  date: string;
  startTime: string;
  endTime: string;
  startMinutes: number;
  endMinutes: number;
  createdAt: string;
};

export type PageMessage = {
  kind: 'error' | 'success';
  text: string;
};
