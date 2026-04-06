import { NextResponse } from 'next/server';

import { createAdmin, createPasswordResetTokenForUser } from '@/lib/accounts';
import {
  createActiveSlot,
  createBlockedSlot,
  deleteActiveSlot,
  deleteBlockedSlot,
  deleteBookingForAdmin,
  deleteInvitationCode,
  deleteUserAccount,
  generateInvitationCode,
  setUserBlocked,
  setUserReservationLimit,
} from '@/lib/bookings';
import {
  loadInvitationConfig,
  loadOpeningHoursPayload,
  loadReservationConfig,
  normalizeInvitationConfig,
  normalizeOpeningHours,
  normalizeReservationConfig,
  saveInvitationConfig,
  saveOpeningHoursPayload,
  saveReservationConfig,
} from '@/lib/configuration';
import { assertAuthenticatedFormCsrf } from '@/lib/security/request-csrf';

export async function POST(request: Request) {
  const formData = await request.formData();

  try {
    const session = await assertAuthenticatedFormCsrf(String(formData.get('csrfToken') ?? ''));
    if (session.role !== 'admin') {
      throw new Error('Connexion administrateur requise.');
    }

    const action = String(formData.get('action') ?? '');
    if (action === 'toggleUserBlock') {
      setUserBlocked(Number(formData.get('userId')), String(formData.get('blocked')) === '1');
    } else if (action === 'setUserLimit') {
      const rawLimit = String(formData.get('reservationLimit') ?? '').trim();
      setUserReservationLimit(Number(formData.get('userId')), rawLimit === '' ? null : Number(rawLimit));
    } else if (action === 'deleteUser') {
      deleteUserAccount(Number(formData.get('userId')));
    } else if (action === 'createUserResetLink') {
      const token = createPasswordResetTokenForUser(Number(formData.get('userId')));
      const url = new URL('/admin/dashboard', request.url);
      url.searchParams.set('success', 'Lien de réinitialisation généré.');
      url.searchParams.set('resetToken', token.token);
      url.searchParams.set('resetExpires', token.expiresAt);
      return NextResponse.redirect(url);
    } else if (action === 'deleteBooking') {
      deleteBookingForAdmin(Number(formData.get('bookingId')));
    } else if (action === 'saveReservationConfig') {
      const current = loadReservationConfig();
      saveReservationConfig(normalizeReservationConfig({
        timezone: String(formData.get('timezone') ?? current.timezone),
        availability_mode: current.availabilityMode,
        sunnygym_display_mode: current.sunnygymDisplayMode,
        max_simultaneous_bookings: Number(formData.get('maxSimultaneousBookings') ?? current.maxSimultaneousBookings),
        min_duration_minutes: Number(formData.get('minDurationMinutes') ?? current.minDurationMinutes),
        max_duration_minutes: Number(formData.get('maxDurationMinutes') ?? current.maxDurationMinutes),
        latest_start_before_close_minutes: Number(formData.get('latestStartBeforeCloseMinutes') ?? current.latestStartBeforeCloseMinutes),
        slot_interval_enabled: current.slotIntervalEnabled,
        slot_interval_minutes: current.slotIntervalMinutes,
        allow_back_to_back: formData.get('allowBackToBack') === 'on',
        fixed_time_only: current.fixedTimeOnly,
        fixed_time_interval_minutes: Number(formData.get('fixedTimeIntervalMinutes') ?? current.fixedTimeIntervalMinutes),
        allow_companion_booking: formData.get('allowCompanionBooking') === 'on',
        allow_private_room_choice: formData.get('allowPrivateRoomChoice') === 'on',
        single_booking_per_day: current.singleBookingPerDay,
        frequency_limit_enabled: current.frequencyLimitEnabled,
        frequency_limit_metric: current.frequencyLimitMetric,
        frequency_limit_value: current.frequencyLimitValue,
        frequency_limit_period_value: current.frequencyLimitPeriodValue,
        frequency_limit_period_unit: current.frequencyLimitPeriodUnit,
      }));
    } else if (action === 'saveInvitationConfig') {
      saveInvitationConfig(normalizeInvitationConfig({
        custom_code_enabled: formData.get('customCodeEnabled') === 'on',
        custom_code: String(formData.get('customCode') ?? ''),
        one_time_validity_days: Number(formData.get('oneTimeValidityDays') ?? loadInvitationConfig().oneTimeValidityDays),
      }));
    } else if (action === 'generateInvitationCode') {
      const generated = generateInvitationCode(loadInvitationConfig().oneTimeValidityDays);
      const url = new URL('/admin/dashboard', request.url);
      url.searchParams.set('success', `Code généré: ${generated.code}`);
      return NextResponse.redirect(url);
    } else if (action === 'deleteInvitationCode') {
      deleteInvitationCode(Number(formData.get('invitationCodeId')));
    } else if (action === 'createActiveSlot') {
      createActiveSlot({
        title: String(formData.get('title') ?? ''),
        date: String(formData.get('date') ?? ''),
        startTime: String(formData.get('startTime') ?? ''),
        endTime: String(formData.get('endTime') ?? ''),
      });
    } else if (action === 'deleteActiveSlot') {
      deleteActiveSlot(Number(formData.get('activeSlotId')));
    } else if (action === 'createBlockedSlot') {
      createBlockedSlot({
        title: String(formData.get('title') ?? ''),
        repeatType: String(formData.get('repeatType') ?? 'once') as 'once' | 'weekly' | 'yearly' | 'holiday',
        referenceDate: String(formData.get('referenceDate') ?? ''),
        startTime: String(formData.get('startTime') ?? ''),
        endTime: String(formData.get('endTime') ?? ''),
        rangeStart: '',
        rangeEnd: '',
      });
    } else if (action === 'deleteBlockedSlot') {
      deleteBlockedSlot(Number(formData.get('blockedSlotId')));
    } else if (action === 'saveOpeningHours') {
      const current = loadOpeningHoursPayload();
      const updated: Record<string, { closed: boolean; start: string; end: string }> = {};
      for (const [dayKey] of Object.entries(current.openingHours)) {
        updated[dayKey] = {
          closed: formData.get(`closed_${dayKey}`) === 'on',
          start: String(formData.get(`start_${dayKey}`) ?? current.openingHours[dayKey].start),
          end: String(formData.get(`end_${dayKey}`) ?? current.openingHours[dayKey].end),
        };
      }
      saveOpeningHoursPayload({
        openingHours: normalizeOpeningHours(updated),
        holidays: current.holidays,
        specialDates: current.specialDates,
      });
    } else if (action === 'createAdminAccount') {
      const password = String(formData.get('password') ?? '');
      const passwordConfirm = String(formData.get('passwordConfirm') ?? '');
      if (password !== passwordConfirm) {
        throw new Error('La confirmation du mot de passe administrateur ne correspond pas.');
      }
      createAdmin(String(formData.get('email') ?? ''), password);
    } else {
      throw new Error('Action administrateur invalide.');
    }

    return NextResponse.redirect(new URL('/admin/dashboard?success=Action+administrateur+enregistrée.', request.url));
  } catch (error) {
    const url = new URL('/admin/dashboard', request.url);
    url.searchParams.set('error', error instanceof Error ? error.message : 'Action administrateur impossible.');
    return NextResponse.redirect(url);
  }
}
