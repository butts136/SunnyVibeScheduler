import { NextResponse } from 'next/server';

import { createBooking } from '@/lib/bookings';
import { assertCsrfToken } from '@/lib/security/csrf';
import { getSession } from '@/lib/security/session';

export async function POST(request: Request) {
  try {
    const session = await getSession();
    assertCsrfToken(session, request.headers.get('x-csrf-token'));
    if (!session || session.role !== 'user') {
      return NextResponse.json({ error: 'Connexion requise.' }, { status: 401 });
    }

    const payload = await request.json();
    createBooking({
      userId: session.subjectId,
      date: String(payload.date ?? ''),
      startTime: String(payload.startTime ?? ''),
      endTime: String(payload.endTime ?? ''),
      title: String(payload.title ?? ''),
      companionCount: Number(payload.companionCount ?? '0'),
      isPrivate: Boolean(payload.isPrivate),
    });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Réservation impossible.' },
      { status: 400 },
    );
  }
}
