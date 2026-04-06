import { NextResponse } from 'next/server';

import { adminExists, createAdmin } from '@/lib/accounts';
import { requestIp } from '@/lib/http';
import { assertGuestFormCsrf } from '@/lib/security/request-csrf';
import { assertRateLimit } from '@/lib/security/rate-limit';
import { secureCompare } from '@/lib/utils';

export async function POST(request: Request) {
  const formData = await request.formData();

  try {
    await assertGuestFormCsrf(String(formData.get('csrfToken') ?? ''));
    assertRateLimit({
      key: `setup:${requestIp(request)}`,
      limit: 5,
      windowMs: 30 * 60 * 1000,
    });

    if (adminExists()) {
      throw new Error("Le compte administrateur existe déjà.");
    }

    const expectedSetupToken = process.env.INITIAL_ADMIN_SETUP_TOKEN?.trim();
    const providedSetupToken = String(formData.get('setupToken') ?? '').trim();
    if (!expectedSetupToken || !providedSetupToken || !secureCompare(expectedSetupToken, providedSetupToken)) {
      throw new Error("Jeton d'installation invalide.");
    }

    const password = String(formData.get('password') ?? '');
    const passwordConfirm = String(formData.get('passwordConfirm') ?? '');
    if (password !== passwordConfirm) {
      throw new Error('La confirmation du mot de passe ne correspond pas.');
    }

    createAdmin(String(formData.get('email') ?? ''), password);
    const url = new URL('/login', request.url);
    url.searchParams.set('success', 'Compte administrateur créé. Vous pouvez maintenant vous connecter.');
    return NextResponse.redirect(url);
  } catch (error) {
    const url = new URL('/admin/setup', request.url);
    url.searchParams.set('error', error instanceof Error ? error.message : 'Installation impossible.');
    return NextResponse.redirect(url);
  }
}
