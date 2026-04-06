import Link from 'next/link';

export default async function PasswordResetPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const token = typeof params.token === 'string' ? params.token : '';

  return (
    <div className="page-stack">
      <section className="form-card">
        <p className="card-subtitle">Réinitialisation sécurisée</p>
        <h1>Mot de passe oublié</h1>
        {!token ? (
          <>
            <p className="muted">
              La récupération libre par date de naissance et questions secrètes a été retirée.
              Demandez à un administrateur de générer un lien de réinitialisation à usage unique.
            </p>
            <div className="button-row spaced-top">
              <Link className="primary-button" href="/login">Retour à la connexion</Link>
            </div>
          </>
        ) : (
          <form action="/auth/password-reset/complete" method="post" className="field-grid spaced-top">
            {typeof params.error === 'string' ? <div className="page-message error">{params.error}</div> : null}
            <input type="hidden" name="token" value={token} />
            <label>
              Nouveau mot de passe
              <input name="password" type="password" minLength={12} required />
            </label>
            <label>
              Confirmation
              <input name="passwordConfirm" type="password" minLength={12} required />
            </label>
            <div className="button-row">
              <button className="primary-button" type="submit">Mettre à jour le mot de passe</button>
              <Link className="ghost-button" href="/login">Annuler</Link>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
