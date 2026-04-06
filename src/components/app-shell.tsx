import Link from 'next/link';

import type { ReactNode } from 'react';

type AppShellProps = {
  children: ReactNode;
  connectionLabel: string;
  primaryAction?: ReactNode;
};

export function AppShell({ children, connectionLabel, primaryAction }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark">SV</span>
          <span>
            <strong>Sunny Vibe</strong>
            <small>Scheduler</small>
          </span>
        </Link>

        <nav className="nav-list">
          <Link href="/">Accueil</Link>
          <Link href="/horaire">Horaires</Link>
          <Link href="/sunnygym">SunnyGym</Link>
          <Link href="/mes-reservations">Mes réservations</Link>
          <Link href="/admin/dashboard">Admin</Link>
          <Link href="/login">Connexion</Link>
        </nav>

        <div className="sidebar-footer">
          <p className="status-label">Statut</p>
          <p className="status-value">{connectionLabel}</p>
          {primaryAction}
        </div>
      </aside>

      <main className="page-main">{children}</main>
    </div>
  );
}
