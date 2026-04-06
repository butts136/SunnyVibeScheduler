import { assertCsrfToken } from '@/lib/security/csrf';
import { getGuestCsrfToken } from '@/lib/security/guest-csrf';
import { getSession } from '@/lib/security/session';
import { secureCompare } from '@/lib/utils';

export async function assertAuthenticatedFormCsrf(formToken: string | null) {
  const session = await getSession();
  assertCsrfToken(session, formToken);
  if (!session) {
    throw new Error('Session invalide.');
  }
  return session;
}

export async function assertGuestFormCsrf(formToken: string | null) {
  const cookieToken = await getGuestCsrfToken();
  if (!cookieToken || !formToken || !secureCompare(cookieToken, formToken)) {
    throw new Error('Jeton de sécurité invalide. Veuillez réessayer.');
  }
}
