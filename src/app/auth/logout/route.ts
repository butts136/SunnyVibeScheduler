import { NextResponse } from 'next/server';

import { assertAuthenticatedFormCsrf } from '@/lib/security/request-csrf';
import { clearSession } from '@/lib/security/session';

export async function POST(request: Request) {
  const formData = await request.formData();

  try {
    await assertAuthenticatedFormCsrf(String(formData.get('csrfToken') ?? ''));
    await clearSession();
    return NextResponse.redirect(new URL('/?success=Déconnexion+effectuée.', request.url));
  } catch {
    return NextResponse.redirect(new URL('/?error=Impossible+de+terminer+la+session.', request.url));
  }
}
