'use client';

import { useMemo, useState } from 'react';

type CalendarDay = {
  dateKey: string;
  label: string;
  weekday: string;
  windows: Array<{ start: number; end: number }>;
  bookings: Array<{ bookingId: number; start: string; end: string; peopleCount: number; isPrivate: boolean }>;
  totalWindowMinutes: number;
  remainingCapacity: number;
  holiday: { name: string; alert: string } | null;
  closed: boolean;
};

type SunnyGymClientProps = {
  csrfToken: string | null;
  userCanBook: boolean;
  maxCompanions: number;
  days: CalendarDay[];
};

function minutesToTime(value: number) {
  const hour = Math.floor(value / 60);
  const minute = value % 60;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

export function SunnyGymClient({
  csrfToken,
  userCanBook,
  maxCompanions,
  days,
}: SunnyGymClientProps) {
  const [selectedDate, setSelectedDate] = useState(days[0]?.dateKey ?? '');
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const selectedDay = useMemo(
    () => days.find((day) => day.dateKey === selectedDate) ?? days[0],
    [days, selectedDate],
  );

  async function handleBookingSubmit(formData: FormData) {
    if (!selectedDay) {
      return;
    }

    setSubmitting(true);
    setMessage(null);
    try {
      const payload = {
        date: selectedDay.dateKey,
        startTime: String(formData.get('startTime') ?? ''),
        endTime: String(formData.get('endTime') ?? ''),
        title: String(formData.get('title') ?? ''),
        companionCount: Number(formData.get('companionCount') ?? '0'),
        isPrivate: formData.get('isPrivate') === 'on',
      };

      const response = await fetch('/api/bookings', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-csrf-token': csrfToken ?? '',
        },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Réservation impossible.');
      }
      setMessage({ kind: 'success', text: 'Réservation créée. Rechargez la page pour voir la disponibilité mise à jour.' });
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof Error ? error.message : 'Réservation impossible.' });
    } finally {
      setSubmitting(false);
    }
  }

  if (!selectedDay) {
    return <div className="panel-card">Aucune journée disponible.</div>;
  }

  return (
    <div className="page-stack">
      <section className="dashboard-grid">
        <div className="panel-card">
          <h2 className="section-title">Prochaines disponibilités</h2>
          <div className="calendar-grid spaced-top">
            {days.map((day) => {
              const availabilityClass = day.closed || day.remainingCapacity === 0 ? 'full' : 'available';
              return (
                <button
                  key={day.dateKey}
                  className={`calendar-day ${availabilityClass}`}
                  type="button"
                  onClick={() => setSelectedDate(day.dateKey)}
                >
                  <strong>{day.label}</strong>
                  <span className="muted">{day.weekday}</span>
                  <div className="badge-row">
                    <span className="badge neutral">{day.closed ? 'Fermé' : `${day.windows.length} plage(s)`}</span>
                    <span className="badge">{day.remainingCapacity} place(s) restantes</span>
                  </div>
                  {day.holiday ? <span className="badge danger">{day.holiday.name}</span> : null}
                </button>
              );
            })}
          </div>
        </div>

        <div className="panel-card">
          <h2 className="section-title">{selectedDay.weekday} {selectedDay.label}</h2>
          {selectedDay.holiday ? (
            <div className="page-message error">{selectedDay.holiday.alert}</div>
          ) : null}

          <div className="list-grid spaced-top">
            {selectedDay.windows.length > 0 ? selectedDay.windows.map((window) => (
              <div className="list-card" key={`${window.start}-${window.end}`}>
                <strong>Plage ouverte</strong>
                <span>{minutesToTime(window.start)} à {minutesToTime(window.end)}</span>
              </div>
            )) : (
              <div className="list-card">
                <strong>Fermé</strong>
                <span>Aucune plage disponible pour cette journée.</span>
              </div>
            )}

            {selectedDay.bookings.length > 0 ? selectedDay.bookings.map((booking) => (
              <div className="list-card" key={booking.bookingId}>
                <strong>{booking.start} à {booking.end}</strong>
                <div className="badge-row">
                  <span className="badge">{booking.peopleCount} personne(s)</span>
                  <span className={`badge ${booking.isPrivate ? 'danger' : 'neutral'}`}>
                    {booking.isPrivate ? 'Privée' : 'Partagée'}
                  </span>
                </div>
              </div>
            )) : (
              <div className="list-card">
                <strong>Aucune réservation</strong>
                <span>Cette journée est encore libre sur les plages affichées.</span>
              </div>
            )}
          </div>
        </div>
      </section>

      {userCanBook ? (
        <section className="form-card">
          <h2 className="section-title">Créer une réservation</h2>
          {message ? <div className={`page-message ${message.kind}`}>{message.text}</div> : null}
          <form
            className="field-grid spaced-top"
            action={async (formData) => {
              await handleBookingSubmit(formData);
            }}
          >
            <div className="grid-two">
              <label>
                Heure de début
                <input name="startTime" type="time" required />
              </label>
              <label>
                Heure de fin
                <input name="endTime" type="time" required />
              </label>
            </div>
            <label>
              Titre
              <input name="title" type="text" maxLength={120} placeholder="Ex: Entraînement personnel" />
            </label>
            <div className="grid-two">
              <label>
                Accompagnateurs
                <input name="companionCount" type="number" min="0" max={maxCompanions} defaultValue="0" />
              </label>
              <label className="checkbox-row">
                <input name="isPrivate" type="checkbox" />
                Réservation privée
              </label>
            </div>
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? 'Envoi...' : `Réserver le ${selectedDay.dateKey}`}
            </button>
          </form>
        </section>
      ) : (
        <section className="panel-card">
          <h2 className="section-title">Connexion requise</h2>
          <p className="muted">Connectez-vous avec un compte utilisateur pour réserver une plage horaire.</p>
        </section>
      )}
    </div>
  );
}
