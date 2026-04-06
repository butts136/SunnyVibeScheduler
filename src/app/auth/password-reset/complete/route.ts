import { NextResponse } from 'next/server';

import { consumePasswordResetToken } from '@/lib/accounts';
import { requestIp } from '@/lib/http';
import { assertRateLimit } from '@/lib/security/rate-limit';

export async function POST(request: Request) {
  const formData = await request.formData();
  const token = String(formData.get('token') ?? '');
  const password = String(formData.get('password') ?? '');
  const passwordConfirm = String(formData.get('passwordConfirm') ?? '');

  try {
    assertRateLimit({
      key: `reset-complete:${requestIp(request)}:${token.slice(0, 8)}`,
      limit: 8,
      windowMs: 30 * 60 * 1000,
    });
    if (password !== passwordConfirm) {
      throw new Error('La confirmation du mot de passe ne correspond pas.');
    }
    consumePasswordResetToken(token, password);
    return NextResponse.redirect(new URL('/login?success=Mot+de+passe+mis+à+jour.', request.url));
  } catch (error) {
    const url = new URL('/account/password-reset', request.url);
    url.searchParams.set('token', token);
    url.searchParams.set('error', error instanceof Error ? error.message : 'Réinitialisation impossible.');
    return NextResponse.redirect(url);
  }
}
