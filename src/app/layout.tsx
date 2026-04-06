import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { AppShell } from '@/components/app-shell';
import { LogoutButton } from '@/components/logout-button';
import '@/app/globals.css';
import { getOptionalAuthContext } from '@/lib/auth-guards';

export const metadata: Metadata = {
  title: 'Sunny Vibe Scheduler',
  description: "Gestion des utilisateurs et réservations Sunny Vibe Nutrition en Next.js sécurisé.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  const auth = await getOptionalAuthContext();
  const connectionLabel = auth.admin
    ? `Admin: ${auth.admin.email}`
    : auth.user
      ? auth.user.fullName || auth.user.email || auth.user.phone || 'Utilisateur'
      : 'Non connecté';

  return (
    <html lang="fr">
      <body>
        <AppShell
          connectionLabel={connectionLabel}
          primaryAction={auth.session ? <LogoutButton csrfToken={auth.session.csrfToken} /> : null}
        >
          {children}
        </AppShell>
      </body>
    </html>
  );
}
