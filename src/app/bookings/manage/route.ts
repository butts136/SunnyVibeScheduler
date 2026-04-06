import { NextResponse } from 'next/server';

import { updateBooking, deleteBookingForUser } from '@/lib/bookings';
import { assertAuthenticatedFormCsrf } from '@/lib/security/request-csrf';

export async function POST(request: Request) {
  const formData = await request.formData();

  try {
    const session = await assertAuthenticatedFormCsrf(String(formData.get('csrfToken') ?? ''));
    if (session.role !== 'user') {
      throw new Error('Connexion utilisateur requise.');
    }

    const action = String(formData.get('action') ?? '');
    const bookingId = Number(formData.get('bookingId'));
    if (!Number.isInteger(bookingId) || bookingId < 1) {
      throw new Error('Réservation invalide.');
    }

    if (action === 'delete') {
      deleteBookingForUser(bookingId, session.subjectId);
    } else {
      updateBooking({
        bookingId,
        userId: session.subjectId,
        date: String(formData.get('date') ?? ''),
        startTime: String(formData.get('startTime') ?? ''),
        endTime: String(formData.get('endTime') ?? ''),
        title: String(formData.get('title') ?? ''),
        companionCount: Number(formData.get('companionCount') ?? '0'),
        isPrivate: formData.get('isPrivate') === 'on',
      });
    }

    return NextResponse.redirect(new URL('/mes-reservations?success=Action+enregistrée.', request.url));
  } catch (error) {
    const url = new URL('/mes-reservations', request.url);
    url.searchParams.set('error', error instanceof Error ? error.message : 'Action impossible.');
    return NextResponse.redirect(url);
  }
}
