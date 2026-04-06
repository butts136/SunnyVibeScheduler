import { redirect } from 'next/navigation';

import { getAdminById, getUserById } from '@/lib/accounts';
import { getSession, refreshSession } from '@/lib/security/session';

export async function getOptionalAuthContext() {
  const session = await getSession();
  if (!session) {
    return {
      session: null,
      admin: null,
      user: null,
    };
  }

  await refreshSession(session);

  if (session.role === 'admin') {
    return {
      session,
      admin: getAdminById(session.subjectId),
      user: null,
    };
  }

  return {
    session,
    admin: null,
    user: getUserById(session.subjectId),
  };
}

export async function requireAdmin() {
  const context = await getOptionalAuthContext();
  if (!context.session || context.session.role !== 'admin' || !context.admin) {
    redirect('/login?error=Connexion+administrateur+requise.');
  }
  return context;
}

export async function requireUser() {
  const context = await getOptionalAuthContext();
  if (!context.session || context.session.role !== 'user' || !context.user) {
    redirect('/login?error=Connexion+utilisateur+requise.');
  }
  return context;
}
