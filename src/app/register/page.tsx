import Link from 'next/link';
import { redirect } from 'next/navigation';

import { getOptionalAuthContext } from '@/lib/auth-guards';
import { getOrCreateGuestCsrfToken } from '@/lib/security/guest-csrf';

export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const auth = await getOptionalAuthContext();
  if (auth.session) {
    redirect('/sunnygym');
  }
  const guestCsrfToken = await getOrCreateGuestCsrfToken();

  return (
    <div className="page-stack">
      <section className="form-card">
        <p className="card-subtitle">Compte utilisateur</p>
        <h1>Créer un compte</h1>
        <p className="muted">Un code d’invitation valide est requis. Les questions secrètes ont été retirées pour réduire la surface d’attaque.</p>
        {typeof params.error === 'string' ? <div className="page-message error">{params.error}</div> : null}

        <form action="/auth/register" method="post" className="field-grid spaced-top">
          <input type="hidden" name="csrfToken" value={guestCsrfToken} />
          <div className="grid-two">
            <label>
              Prénom
              <input name="firstName" type="text" required />
            </label>
            <label>
              Nom
              <input name="lastName" type="text" required />
            </label>
          </div>
          <div className="grid-two">
            <label>
              Adresse courriel
              <input name="email" type="email" />
            </label>
            <label>
              Téléphone
              <input name="phone" type="tel" />
            </label>
          </div>
          <div className="grid-two">
            <label>
              Date de naissance
              <input name="birthDate" type="date" required />
            </label>
            <label>
              Code d’invitation
              <input name="invitationCode" type="text" required />
            </label>
          </div>
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
            <button className="primary-button" type="submit">Créer le compte</button>
            <Link className="ghost-button" href="/login">Retour à la connexion</Link>
          </div>
        </form>
      </section>
    </div>
  );
}
