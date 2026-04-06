import { createHmac } from 'node:crypto';
import fs from 'node:fs';
import { cookies } from 'next/headers';

import { DATA_DIR, SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, SESSION_SECRET_PATH } from '@/lib/constants';
import type { SessionPayload } from '@/lib/types';
import { fromBase64Url, randomToken, toBase64Url } from '@/lib/utils';

function getSessionSecret() {
  const envSecret = process.env.APP_SESSION_SECRET?.trim();
  if (envSecret) {
    return envSecret;
  }

  fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(SESSION_SECRET_PATH)) {
    fs.writeFileSync(SESSION_SECRET_PATH, randomToken(32), { encoding: 'utf8', mode: 0o600 });
  }
  return fs.readFileSync(SESSION_SECRET_PATH, 'utf8').trim();
}

function sign(value: string) {
  return createHmac('sha256', getSessionSecret()).update(value).digest('base64url');
}

function serializeSession(payload: SessionPayload) {
  const encodedPayload = toBase64Url(JSON.stringify(payload));
  return `${encodedPayload}.${sign(encodedPayload)}`;
}

function deserializeSession(value: string | undefined) {
  if (!value || !value.includes('.')) {
    return null;
  }

  const [encodedPayload, signature] = value.split('.', 2);
  if (!encodedPayload || !signature) {
    return null;
  }

  const expectedSignature = sign(encodedPayload);
  if (signature !== expectedSignature) {
    return null;
  }

  try {
    const payload = JSON.parse(fromBase64Url(encodedPayload).toString('utf8')) as SessionPayload;
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    if (payload.expiresAt <= Date.now()) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}

async function cookieStore() {
  return cookies();
}

export async function getSession() {
  const store = await cookieStore();
  return deserializeSession(store.get(SESSION_COOKIE_NAME)?.value);
}

export async function setSession(role: SessionPayload['role'], subjectId: number) {
  const store = await cookieStore();
  const payload: SessionPayload = {
    role,
    subjectId,
    csrfToken: randomToken(24),
    expiresAt: Date.now() + (SESSION_MAX_AGE_SECONDS * 1000),
  };

  store.set(SESSION_COOKIE_NAME, serializeSession(payload), {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: SESSION_MAX_AGE_SECONDS,
  });

  return payload;
}

export async function refreshSession(session: SessionPayload) {
  const store = await cookieStore();
  const refreshed: SessionPayload = {
    ...session,
    expiresAt: Date.now() + (SESSION_MAX_AGE_SECONDS * 1000),
  };
  store.set(SESSION_COOKIE_NAME, serializeSession(refreshed), {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
  return refreshed;
}

export async function clearSession() {
  const store = await cookieStore();
  store.set(SESSION_COOKIE_NAME, '', {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    expires: new Date(0),
  });
}
