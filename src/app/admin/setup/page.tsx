import Link from 'next/link';
import { redirect } from 'next/navigation';

import { adminExists } from '@/lib/accounts';
import { getOrCreateGuestCsrfToken } from '@/lib/security/guest-csrf';

export default async function AdminSetupPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  if (adminExists()) {
    redirect('/login?success=Le+compte+administrateur+existe+déjà.');
  }
  const guestCsrfToken = await getOrCreateGuestCsrfToken();

  return (
    <div className="page-stack">
      <section className="form-card">
        <p className="card-subtitle">Installation initiale</p>
        <h1>Créer le premier administrateur</h1>
        <p className="muted">
          Cette opération nécessite le secret d’installation défini dans `INITIAL_ADMIN_SETUP_TOKEN`.
        </p>
        {typeof params.error === 'string' ? <div className="page-message error">{params.error}</div> : null}

        <form action="/auth/setup" method="post" className="field-grid spaced-top">
          <input type="hidden" name="csrfToken" value={guestCsrfToken} />
          <label>
            Jeton d’installation
            <input name="setupToken" type="password" required />
          </label>
          <label>
            Courriel administrateur
            <input name="email" type="email" required />
          </label>
          <div className="grid-two">
            <label>
              Mot de passe
              <input name="password" type="password" minLength={12} required />
            </label>
            <label>
              Confirmation
              <input name="passwordConfirm" type="password" minLength={12} required />
            </label>
          </div>
          <div className="button-row">
            <button className="primary-button" type="submit">Créer l’administrateur</button>
            <Link className="ghost-button" href="/login">Retour</Link>
          </div>
        </form>
      </section>
    </div>
  );
}
