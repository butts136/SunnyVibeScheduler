import { NextResponse } from 'next/server';

import { createUser } from '@/lib/accounts';
import { requestIp } from '@/lib/http';
import { assertGuestFormCsrf } from '@/lib/security/request-csrf';
import { assertRateLimit } from '@/lib/security/rate-limit';
import { setSession } from '@/lib/security/session';

export async function POST(request: Request) {
  const formData = await request.formData();

  try {
    await assertGuestFormCsrf(String(formData.get('csrfToken') ?? ''));
    assertRateLimit({
      key: `register:${requestIp(request)}`,
      limit: 6,
      windowMs: 15 * 60 * 1000,
    });

    const password = String(formData.get('password') ?? '');
    const passwordConfirm = String(formData.get('passwordConfirm') ?? '');
    if (password !== passwordConfirm) {
      throw new Error('La confirmation du mot de passe ne correspond pas.');
    }

    const user = createUser({
      firstName: String(formData.get('firstName') ?? ''),
      lastName: String(formData.get('lastName') ?? ''),
      email: String(formData.get('email') ?? ''),
      phone: String(formData.get('phone') ?? ''),
      birthDate: String(formData.get('birthDate') ?? ''),
      password,
      invitationCode: String(formData.get('invitationCode') ?? ''),
    });

    if (!user) {
      throw new Error('Impossible de créer le compte.');
    }

    await setSession('user', user.id);
    return NextResponse.redirect(new URL('/sunnygym?success=Compte+créé+avec+succès.', request.url));
  } catch (error) {
    const url = new URL('/register', request.url);
    url.searchParams.set('error', error instanceof Error ? error.message : 'Création de compte impossible.');
    return NextResponse.redirect(url);
  }
}
