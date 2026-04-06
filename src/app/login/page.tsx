import Link from 'next/link';
import { redirect } from 'next/navigation';

import { adminExists, anyUserExists } from '@/lib/accounts';
import { getOptionalAuthContext } from '@/lib/auth-guards';
import { getOrCreateGuestCsrfToken } from '@/lib/security/guest-csrf';

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const auth = await getOptionalAuthContext();

  if (auth.session?.role === 'admin') {
    redirect('/admin/dashboard');
  }
  if (auth.session?.role === 'user') {
    redirect('/sunnygym');
  }

  const guestCsrfToken = await getOrCreateGuestCsrfToken();
  const hasAdmin = adminExists();
  const hasUsers = anyUserExists();

  return (
    <div className="page-stack">
      <section className="form-card">
        <p className="card-subtitle">Authentification sécurisée</p>
        <h1>Connexion</h1>
        {typeof params.error === 'string' ? <div className="page-message error">{params.error}</div> : null}
        {typeof params.success === 'string' ? <div className="page-message success">{params.success}</div> : null}

        {!hasAdmin ? (
          <div className="page-message error">Aucun compte administrateur actif. Utilisez la procédure d’installation sécurisée.</div>
        ) : null}

        <form action="/auth/login" method="post" className="field-grid spaced-top">
          <input type="hidden" name="csrfToken" value={guestCsrfToken} />
          <label>
            Courriel ou téléphone
            <input name="identifier" type="text" required />
          </label>
          <label>
            Mot de passe
            <input name="password" type="password" minLength={12} required />
          </label>
          <div className="button-row">
            <button className="primary-button" type="submit">Connexion</button>
            <Link className="secondary-button" href="/account/password-reset">Mot de passe oublié</Link>
            {!hasUsers ? <Link className="ghost-button" href="/register">Créer le premier utilisateur</Link> : null}
          </div>
        </form>

        {!hasAdmin ? (
          <div className="spaced-top">
            <Link className="secondary-button" href="/admin/setup">Installer le premier admin</Link>
          </div>
        ) : null}
      </section>
    </div>
  );
}
