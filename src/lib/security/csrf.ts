import type { SessionPayload } from '@/lib/types';
import { secureCompare } from '@/lib/utils';

export function assertCsrfToken(session: SessionPayload | null, submittedToken: string | null) {
  if (!session || !submittedToken || !secureCompare(session.csrfToken, submittedToken)) {
    throw new Error('Jeton de sécurité invalide. Veuillez réessayer.');
  }
}
