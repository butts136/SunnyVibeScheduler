import { redirect } from 'next/navigation';

import { PageMessageBanner } from '@/components/page-message';
import { requireUser } from '@/lib/auth-guards';
import { listBookingsForUser } from '@/lib/bookings';
import { loadReservationConfig } from '@/lib/configuration';

export default async function MyBookingsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const { session, user } = await requireUser();
  if (!user) {
    redirect('/login');
  }

  const config = loadReservationConfig();
  const bookings = listBookingsForUser(user.id, config);
  const message = typeof params.success === 'string'
    ? { kind: 'success' as const, text: params.success }
    : typeof params.error === 'string'
      ? { kind: 'error' as const, text: params.error }
      : null;

  return (
    <div className="page-stack">
      <PageMessageBanner message={message} />
      <section className="panel-card">
        <p className="card-subtitle">Compte utilisateur</p>
        <h1>Mes réservations</h1>
        <div className="list-grid spaced-top">
          {bookings.length > 0 ? bookings.map((booking) => (
            <div className="list-card" key={booking.id}>
              <div className="badge-row">
                <span className="badge neutral">{booking.dateLabel}</span>
                <span className={`badge ${booking.isPast ? 'danger' : ''}`}>{booking.startTime} à {booking.endTime}</span>
              </div>
              <strong>{booking.title || 'Sans titre'}</strong>
              <span className="muted">
                {booking.peopleCount} personne(s) · {booking.isPrivate ? 'Privée' : 'Partagée'}
              </span>
              {!booking.isPast ? (
                <>
                  <form action="/bookings/manage" method="post" className="field-grid">
                    <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                    <input type="hidden" name="bookingId" value={String(booking.id)} />
                    <input type="hidden" name="action" value="update" />
                    <div className="grid-two">
                      <label>
                        Date
                        <input name="date" type="date" defaultValue={booking.dateKey} required />
                      </label>
                      <label>
                        Titre
                        <input name="title" type="text" defaultValue={booking.title} maxLength={120} />
                      </label>
                    </div>
                    <div className="grid-two">
                      <label>
                        Début
                        <input name="startTime" type="time" defaultValue={booking.startTime} required />
                      </label>
                      <label>
                        Fin
                        <input name="endTime" type="time" defaultValue={booking.endTime} required />
                      </label>
                    </div>
                    <div className="grid-two">
                      <label>
                        Accompagnateurs
                        <input
                          name="companionCount"
                          type="number"
                          min="0"
                          max={Math.max(config.maxSimultaneousBookings - 1, 0)}
                          defaultValue={booking.companionCount}
                        />
                      </label>
                      <label className="checkbox-row">
                        <input name="isPrivate" type="checkbox" defaultChecked={booking.isPrivate} />
                        Réservation privée
                      </label>
                    </div>
                    <div className="button-row">
                      <button className="primary-button" type="submit">Enregistrer</button>
                    </div>
                  </form>
                  <form action="/bookings/manage" method="post">
                    <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                    <input type="hidden" name="bookingId" value={String(booking.id)} />
                    <input type="hidden" name="action" value="delete" />
                    <button className="danger-button" type="submit">Annuler</button>
                  </form>
                </>
              ) : (
                <span className="muted">Réservation terminée: modification désactivée.</span>
              )}
            </div>
          )) : (
            <div className="list-card">
              <strong>Aucune réservation</strong>
              <span>Votre compte ne contient encore aucune réservation.</span>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
