import Link from 'next/link';

import { PageMessageBanner } from '@/components/page-message';
import { getOptionalAuthContext } from '@/lib/auth-guards';

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const auth = await getOptionalAuthContext();
  const message = typeof params.success === 'string'
    ? { kind: 'success' as const, text: params.success }
    : typeof params.error === 'string'
      ? { kind: 'error' as const, text: params.error }
      : null;

  return (
    <div className="page-stack">
      <PageMessageBanner message={message} />

      <section className="hero-card">
        <div>
          <p className="card-subtitle">Application migrée vers Next.js + TypeScript</p>
          <h1>Gestion sécurisée des réservations Sunny Vibe Nutrition</h1>
          <p className="muted">
            L’application gère désormais l’authentification, les réservations et l’administration
            avec sessions signées, anti-CSRF, limitation de débit et réinitialisation par jeton.
          </p>
          <div className="hero-actions spaced-top">
            <Link className="primary-button" href="/sunnygym">Ouvrir SunnyGym</Link>
            <Link className="secondary-button" href="/horaire">Voir les horaires</Link>
            {!auth.session ? <Link className="ghost-button" href="/login">Connexion</Link> : null}
          </div>
        </div>

        <div className="stats-grid">
          <div className="list-card">
            <strong>Frontend</strong>
            <span>React + Next.js App Router</span>
          </div>
          <div className="list-card">
            <strong>Backend</strong>
            <span>Route handlers sécurisés</span>
          </div>
          <div className="list-card">
            <strong>Persistance</strong>
            <span>SQLite conservé</span>
          </div>
        </div>
      </section>
    </div>
  );
}
