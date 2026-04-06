import { PageMessageBanner } from '@/components/page-message';
import { requireAdmin } from '@/lib/auth-guards';
import {
  listAdmins,
} from '@/lib/accounts';
import {
  buildCalendarDays,
  groupBookingsByDate,
  loadActiveSlotRules,
  loadBlockedSlotRules,
  listBookingsForAdmin,
  listInvitationCodes,
  listUsersForAdmin,
} from '@/lib/bookings';
import {
  DAY_CONFIG,
  VALID_SLOT_INTERVALS,
} from '@/lib/constants';
import {
  loadInvitationConfig,
  loadOpeningHoursPayload,
  loadReservationConfig,
} from '@/lib/configuration';

export default async function AdminDashboardPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const { session, admin } = await requireAdmin();
  const openingHoursPayload = loadOpeningHoursPayload();
  const reservationConfig = loadReservationConfig();
  const invitationConfig = loadInvitationConfig();
  const bookings = listBookingsForAdmin(reservationConfig);
  const users = listUsersForAdmin(reservationConfig);
  const blockedSlots = loadBlockedSlotRules();
  const activeSlots = loadActiveSlotRules();
  const invitationCodes = listInvitationCodes();
  const groupedBookings = groupBookingsByDate(bookings);
  const latestResetToken = typeof params.resetToken === 'string' && typeof params.resetExpires === 'string'
    ? { token: params.resetToken, expiresAt: params.resetExpires }
    : null;
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
          <p className="card-subtitle">Admin connecté: {admin?.email}</p>
          <h1>Tableau de bord</h1>
          <p className="muted">
            Toutes les actions critiques passent par POST + CSRF. Les réinitialisations utilisent
            des liens à usage unique de 30 minutes.
          </p>
        </div>
        <div className="stats-grid">
          <div className="list-card">
            <strong>{users.length}</strong>
            <span>Utilisateur(s)</span>
          </div>
          <div className="list-card">
            <strong>{bookings.length}</strong>
            <span>Réservation(s)</span>
          </div>
          <div className="list-card">
            <strong>{listAdmins().length}</strong>
            <span>Admin(s)</span>
          </div>
        </div>
      </section>

      {latestResetToken ? (
        <section className="panel-card">
          <h2 className="section-title">Lien de réinitialisation généré</h2>
          <p className="muted">Valide jusqu’au {latestResetToken.expiresAt}.</p>
          <code>{`${process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000'}/account/password-reset?token=${latestResetToken.token}`}</code>
        </section>
      ) : null}

      <section className="dashboard-grid">
        <div className="dashboard-card">
          <h2 className="section-title">Réservations</h2>
          <div className="list-grid spaced-top">
            {groupedBookings.map((group) => (
              <div className="list-card" key={group.dateKey}>
                <strong>{group.dateTitle}</strong>
                <span className="muted">{group.items.length} réservation(s)</span>
                <div className="list-grid">
                  {group.items.map((booking) => (
                    <div className="list-card" key={booking.id}>
                      <div className="badge-row">
                        <span className="badge">{booking.startTime} à {booking.endTime}</span>
                        <span className={`badge ${booking.isPrivate ? 'danger' : 'neutral'}`}>
                          {booking.isPrivate ? 'Privée' : 'Partagée'}
                        </span>
                      </div>
                      <strong>{booking.userName || 'Utilisateur inconnu'}</strong>
                      <span className="muted">{booking.userEmail || booking.userPhone || 'Sans contact'}</span>
                      <form action="/admin/actions" method="post" className="button-row">
                        <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                        <input type="hidden" name="action" value="deleteBooking" />
                        <input type="hidden" name="bookingId" value={String(booking.id)} />
                        <button className="danger-button" type="submit">Supprimer</button>
                      </form>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="dashboard-card">
          <h2 className="section-title">Utilisateurs</h2>
          <div className="list-grid spaced-top">
            {users.map((user) => (
              <div className="list-card" key={user.id}>
                <strong>{user.fullName || user.email || user.phone || `Utilisateur #${user.id}`}</strong>
                <span className="muted">{user.email || user.phone || 'Aucun contact'}</span>
                <div className="badge-row">
                  <span className={`badge ${user.isBlocked ? 'danger' : ''}`}>{user.isBlocked ? 'Bloqué' : 'Actif'}</span>
                  <span className="badge neutral">{user.bookingCount} réservation(s)</span>
                </div>
                <div className="button-row">
                  <form action="/admin/actions" method="post">
                    <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                    <input type="hidden" name="action" value="toggleUserBlock" />
                    <input type="hidden" name="userId" value={String(user.id)} />
                    <input type="hidden" name="blocked" value={user.isBlocked ? '0' : '1'} />
                    <button className="secondary-button" type="submit">{user.isBlocked ? 'Débloquer' : 'Bloquer'}</button>
                  </form>
                  <form action="/admin/actions" method="post">
                    <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                    <input type="hidden" name="action" value="createUserResetLink" />
                    <input type="hidden" name="userId" value={String(user.id)} />
                    <button className="ghost-button" type="submit">Créer un lien reset</button>
                  </form>
                </div>
                <form action="/admin/actions" method="post" className="field-grid">
                  <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                  <input type="hidden" name="action" value="setUserLimit" />
                  <input type="hidden" name="userId" value={String(user.id)} />
                  <label>
                    Limite de réservations
                    <input name="reservationLimit" type="number" min="0" defaultValue={user.reservationLimit ?? ''} />
                  </label>
                  <div className="button-row">
                    <button className="primary-button" type="submit">Appliquer</button>
                  </div>
                </form>
                <form action="/admin/actions" method="post">
                  <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                  <input type="hidden" name="action" value="deleteUser" />
                  <input type="hidden" name="userId" value={String(user.id)} />
                  <button className="danger-button" type="submit">Supprimer</button>
                </form>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="dashboard-grid">
        <div className="dashboard-card">
          <h2 className="section-title">Configuration</h2>
          <form action="/admin/actions" method="post" className="field-grid spaced-top">
            <input type="hidden" name="csrfToken" value={session!.csrfToken} />
            <input type="hidden" name="action" value="saveOpeningHours" />
            {DAY_CONFIG.map(([dayKey, label]) => (
              <div className="grid-three" key={dayKey}>
                <label className="checkbox-row">
                  <input
                    name={`closed_${dayKey}`}
                    type="checkbox"
                    defaultChecked={openingHoursPayload.openingHours[dayKey].closed}
                  />
                  {label} fermé
                </label>
                <label>
                  Début
                  <input
                    name={`start_${dayKey}`}
                    type="time"
                    defaultValue={openingHoursPayload.openingHours[dayKey].start}
                  />
                </label>
                <label>
                  Fin
                  <input
                    name={`end_${dayKey}`}
                    type="time"
                    defaultValue={openingHoursPayload.openingHours[dayKey].end}
                  />
                </label>
              </div>
            ))}
            <button className="secondary-button" type="submit">Enregistrer les horaires</button>
          </form>

          <form action="/admin/actions" method="post" className="field-grid spaced-top">
            <input type="hidden" name="csrfToken" value={session!.csrfToken} />
            <input type="hidden" name="action" value="saveReservationConfig" />
            <div className="grid-three">
              <label>
                Fuseau horaire
                <input name="timezone" type="text" defaultValue={reservationConfig.timezone} required />
              </label>
              <label>
                Capacité max
                <input name="maxSimultaneousBookings" type="number" min="1" defaultValue={reservationConfig.maxSimultaneousBookings} />
              </label>
              <label>
                Heure fixe
                <select name="fixedTimeIntervalMinutes" defaultValue={String(reservationConfig.fixedTimeIntervalMinutes)}>
                  {VALID_SLOT_INTERVALS.map((value) => <option key={value} value={value}>{value} min</option>)}
                </select>
              </label>
            </div>
            <div className="grid-three">
              <label>
                Durée min
                <input name="minDurationMinutes" type="number" min="1" defaultValue={reservationConfig.minDurationMinutes} />
              </label>
              <label>
                Durée max
                <input name="maxDurationMinutes" type="number" min="1" defaultValue={reservationConfig.maxDurationMinutes} />
              </label>
              <label>
                Début avant fermeture
                <input name="latestStartBeforeCloseMinutes" type="number" min="0" defaultValue={reservationConfig.latestStartBeforeCloseMinutes} />
              </label>
            </div>
            <div className="grid-three">
              <label className="checkbox-row"><input name="allowBackToBack" type="checkbox" defaultChecked={reservationConfig.allowBackToBack} />Réservations consécutives</label>
              <label className="checkbox-row"><input name="allowCompanionBooking" type="checkbox" defaultChecked={reservationConfig.allowCompanionBooking} />Accompagnateurs</label>
              <label className="checkbox-row"><input name="allowPrivateRoomChoice" type="checkbox" defaultChecked={reservationConfig.allowPrivateRoomChoice} />Salle privée</label>
            </div>
            <button className="primary-button" type="submit">Enregistrer</button>
          </form>

          <form action="/admin/actions" method="post" className="field-grid spaced-top">
            <input type="hidden" name="csrfToken" value={session!.csrfToken} />
            <input type="hidden" name="action" value="saveInvitationConfig" />
            <div className="grid-two">
              <label className="checkbox-row"><input name="customCodeEnabled" type="checkbox" defaultChecked={invitationConfig.customCodeEnabled} />Code personnalisé</label>
              <label>
                Validité par défaut (jours)
                <input name="oneTimeValidityDays" type="number" min="1" max="365" defaultValue={invitationConfig.oneTimeValidityDays} />
              </label>
            </div>
            <label>
              Code personnalisé
              <input name="customCode" type="text" defaultValue={invitationConfig.customCode} maxLength={32} />
            </label>
            <div className="button-row">
              <button className="primary-button" type="submit">Enregistrer</button>
            </div>
          </form>
          <form action="/admin/actions" method="post" className="spaced-top">
            <input type="hidden" name="csrfToken" value={session!.csrfToken} />
            <input type="hidden" name="action" value="generateInvitationCode" />
            <button className="secondary-button" type="submit">Générer un code unique</button>
          </form>
        </div>

        <div className="dashboard-card">
          <h2 className="section-title">Horaires, blocages et créneaux</h2>
          <div className="list-grid spaced-top">
            {DAY_CONFIG.map(([dayKey, label]) => (
              <div className="list-card" key={dayKey}>
                <strong>{label}</strong>
                <span>
                  {openingHoursPayload.openingHours[dayKey].closed
                    ? 'Fermé'
                    : `${openingHoursPayload.openingHours[dayKey].start} à ${openingHoursPayload.openingHours[dayKey].end}`}
                </span>
              </div>
            ))}
          </div>
          <div className="grid-two spaced-top">
            <form action="/admin/actions" method="post" className="field-grid">
              <input type="hidden" name="csrfToken" value={session!.csrfToken} />
              <input type="hidden" name="action" value="createActiveSlot" />
              <label>
                Date activée
                <input name="date" type="date" required />
              </label>
              <div className="grid-two">
                <label>
                  Début
                  <input name="startTime" type="time" required />
                </label>
                <label>
                  Fin
                  <input name="endTime" type="time" required />
                </label>
              </div>
              <label>
                Titre
                <input name="title" type="text" />
              </label>
              <button className="primary-button" type="submit">Ajouter créneau</button>
            </form>

            <form action="/admin/actions" method="post" className="field-grid">
              <input type="hidden" name="csrfToken" value={session!.csrfToken} />
              <input type="hidden" name="action" value="createBlockedSlot" />
              <label>
                Type
                <select name="repeatType" defaultValue="once">
                  <option value="once">Une seule fois</option>
                  <option value="weekly">Chaque semaine</option>
                  <option value="yearly">Chaque année</option>
                  <option value="holiday">Chaque férié</option>
                </select>
              </label>
              <label>
                Date de référence
                <input name="referenceDate" type="date" />
              </label>
              <div className="grid-two">
                <label>
                  Début
                  <input name="startTime" type="time" required />
                </label>
                <label>
                  Fin
                  <input name="endTime" type="time" required />
                </label>
              </div>
              <label>
                Titre
                <input name="title" type="text" />
              </label>
              <button className="primary-button" type="submit">Ajouter blocage</button>
            </form>
          </div>
          <div className="grid-two spaced-top">
            <div className="list-grid">
              {activeSlots.map((slot) => (
                <div className="list-card" key={slot.id}>
                  <strong>{slot.title}</strong>
                  <span>{slot.date} · {slot.startTime} à {slot.endTime}</span>
                  <form action="/admin/actions" method="post">
                    <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                    <input type="hidden" name="action" value="deleteActiveSlot" />
                    <input type="hidden" name="activeSlotId" value={String(slot.id)} />
                    <button className="danger-button" type="submit">Supprimer</button>
                  </form>
                </div>
              ))}
            </div>
            <div className="list-grid">
              {blockedSlots.map((slot) => (
                <div className="list-card" key={slot.id}>
                  <strong>{slot.title}</strong>
                  <span>{slot.repeatDescription} · {slot.startTime} à {slot.endTime}</span>
                  <form action="/admin/actions" method="post">
                    <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                    <input type="hidden" name="action" value="deleteBlockedSlot" />
                    <input type="hidden" name="blockedSlotId" value={String(slot.id)} />
                    <button className="danger-button" type="submit">Supprimer</button>
                  </form>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="dashboard-grid">
        <div className="dashboard-card">
          <h2 className="section-title">Codes d’invitation</h2>
          <div className="list-grid spaced-top">
            {invitationCodes.map((code) => (
              <div className="list-card" key={code.id}>
                <strong>{code.code}</strong>
                <span>Expire: {code.expires_at}</span>
                <span className="muted">{code.used_at ? `Utilisé: ${code.used_at}` : 'Disponible'}</span>
                <form action="/admin/actions" method="post">
                  <input type="hidden" name="csrfToken" value={session!.csrfToken} />
                  <input type="hidden" name="action" value="deleteInvitationCode" />
                  <input type="hidden" name="invitationCodeId" value={String(code.id)} />
                  <button className="danger-button" type="submit">Supprimer</button>
                </form>
              </div>
            ))}
          </div>
        </div>

        <div className="dashboard-card">
          <h2 className="section-title">Vue rapide calendrier</h2>
          <div className="list-grid spaced-top">
            {buildCalendarDays(14, reservationConfig).map((day) => (
              <div className="list-card" key={day.dateKey}>
                <strong>{day.weekday} {day.label}</strong>
                <span>{day.closed ? 'Fermé' : `${day.windows.length} plage(s) ouverte(s)`}</span>
                <span className="muted">{day.bookings.length} réservation(s)</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
