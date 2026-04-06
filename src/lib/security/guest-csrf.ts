import { cookies } from 'next/headers';

import { GUEST_CSRF_COOKIE_NAME } from '@/lib/constants';
import { randomToken } from '@/lib/utils';

export async function getOrCreateGuestCsrfToken() {
  const store = await cookies();
  const existing = store.get(GUEST_CSRF_COOKIE_NAME)?.value;
  if (existing) {
    return existing;
  }

  const token = randomToken(24);
  store.set(GUEST_CSRF_COOKIE_NAME, token, {
    httpOnly: false,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: 60 * 60 * 4,
  });
  return token;
}

export async function getGuestCsrfToken() {
  const store = await cookies();
  return store.get(GUEST_CSRF_COOKIE_NAME)?.value ?? null;
}
