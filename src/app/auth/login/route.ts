import { NextResponse } from 'next/server';

import { authenticateIdentifier } from '@/lib/accounts';
import { requestIp } from '@/lib/http';
import { assertGuestFormCsrf } from '@/lib/security/request-csrf';
import { assertRateLimit } from '@/lib/security/rate-limit';
import { setSession } from '@/lib/security/session';

export async function POST(request: Request) {
  const formData = await request.formData();
  const identifier = String(formData.get('identifier') ?? '').trim();
  const password = String(formData.get('password') ?? '');

  try {
    await assertGuestFormCsrf(String(formData.get('csrfToken') ?? ''));
    assertRateLimit({
      key: `login:${requestIp(request)}:${identifier.toLowerCase()}`,
      limit: 10,
      windowMs: 10 * 60 * 1000,
    });
    const auth = authenticateIdentifier(identifier, password);
    await setSession(auth.role, auth.subjectId);
    return NextResponse.redirect(new URL(auth.role === 'admin' ? '/admin/dashboard' : '/sunnygym', request.url));
  } catch (error) {
    const url = new URL('/login', request.url);
    url.searchParams.set('error', error instanceof Error ? error.message : 'Connexion impossible.');
    return NextResponse.redirect(url);
  }
}
