import { FRENCH_MONTHS } from '@/lib/constants';
import { loadOpeningHoursPayload, mergeWithQuebecHolidays } from '@/lib/configuration';
import type { HolidayConfig, OpeningHours, SpecialDateConfig } from '@/lib/types';

const PYTHON_WEEKDAY_LABELS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
const DAY_KEY_BY_WEEKDAY = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'] as const;

function formatHours(row: { closed: boolean; start: string; end: string }) {
  return row.closed ? 'Fermé' : `${row.start} à ${row.end}`;
}

function formatDateFr(dateKey: string) {
  const date = new Date(`${dateKey}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return dateKey;
  }
  return `${date.getUTCDate()} ${FRENCH_MONTHS[date.getUTCMonth() + 1]} ${date.getUTCFullYear()}`;
}

function pushUnique(values: string[], value: string) {
  const text = value.trim();
  if (text && !values.includes(text)) {
    values.push(text);
  }
}

function buildWeeklyHours(openingHours: OpeningHours) {
  const orderedDays = [
    ['sunday', 'Dimanche'],
    ['monday', 'Lundi'],
    ['tuesday', 'Mardi'],
    ['wednesday', 'Mercredi'],
    ['thursday', 'Jeudi'],
    ['friday', 'Vendredi'],
    ['saturday', 'Samedi'],
  ] as const;
  const rows: Array<{
    dayKey: string;
    dayLabel: string;
    hoursText: string;
    isClosed: boolean;
    span: number;
    columnStart: number;
  }> = [];

  orderedDays.forEach(([dayKey, dayLabel], index) => {
    const hoursText = formatHours(openingHours[dayKey]);
    const previous = rows[rows.length - 1];

    if (previous && previous.hoursText === hoursText) {
      previous.dayLabel = previous.span === 1
        ? `${previous.dayLabel} et ${dayLabel}`
        : `${previous.dayLabel.split(' à ')[0].split(' et ')[0]} à ${dayLabel}`;
      previous.span += 1;
      return;
    }

    rows.push({
      dayKey,
      dayLabel,
      hoursText,
      isClosed: hoursText === 'Fermé',
      span: 1,
      columnStart: index + 1,
    });
  });

  return rows;
}

function buildUpcomingSpecialDates(openingHours: OpeningHours, holidays: HolidayConfig[], specialDates: SpecialDateConfig[]) {
  const today = new Date();
  const todayKey = [
    today.getUTCFullYear(),
    String(today.getUTCMonth() + 1).padStart(2, '0'),
    String(today.getUTCDate()).padStart(2, '0'),
  ].join('-');
  const events = new Map<string, {
    date: string;
    weekdayLabel: string;
    dateLabel: string;
    titleParts: string[];
    notes: string[];
    badges: string[];
    hoursText: string;
    hoursContext: string;
    isClosed: boolean;
    hasSpecialHours: boolean;
    isHoliday: boolean;
  }>();

  const eventFor = (dateKey: string) => {
    let event = events.get(dateKey);
    if (!event) {
      const date = new Date(`${dateKey}T00:00:00Z`);
      const dayKey = DAY_KEY_BY_WEEKDAY[date.getUTCDay()];
      const regularHours = formatHours(openingHours[dayKey]);
      event = {
        date: dateKey,
        weekdayLabel: PYTHON_WEEKDAY_LABELS[(date.getUTCDay() + 6) % 7],
        dateLabel: formatDateFr(dateKey),
        titleParts: [],
        notes: [],
        badges: [],
        hoursText: regularHours,
        hoursContext: 'Horaire régulier',
        isClosed: regularHours === 'Fermé',
        hasSpecialHours: false,
        isHoliday: false,
      };
      events.set(dateKey, event);
    }
    return event;
  };

  for (const holiday of holidays) {
    const occurrences: string[] = [];

    if (holiday.date && holiday.date >= todayKey) {
      occurrences.push(holiday.date);
    } else if (holiday.monthDay) {
      const [monthText, dayText] = holiday.monthDay.split('-');
      const month = Number(monthText);
      const day = Number(dayText);
      for (let year = today.getUTCFullYear(); year <= today.getUTCFullYear() + 3; year += 1) {
        const date = new Date(Date.UTC(year, month - 1, day));
        if (date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
          continue;
        }
        const dateKey = date.toISOString().slice(0, 10);
        if (dateKey >= todayKey) {
          occurrences.push(dateKey);
        }
      }
    }

    for (const dateKey of occurrences) {
      const event = eventFor(dateKey);
      event.isHoliday = true;
      pushUnique(event.badges, 'Férié');
      pushUnique(event.titleParts, holiday.name);
      pushUnique(event.notes, holiday.alert);
    }
  }

  for (const specialDate of specialDates) {
    if (specialDate.date < todayKey) {
      continue;
    }

    const event = eventFor(specialDate.date);
    event.hasSpecialHours = true;
    pushUnique(event.badges, 'Horaire spécial');
    pushUnique(event.notes, specialDate.reason);

    if (specialDate.closed) {
      event.hoursText = 'Fermé';
      event.hoursContext = 'Fermé exceptionnellement';
      event.isClosed = true;
    } else {
      event.hoursText = `${specialDate.start} à ${specialDate.end}`;
      event.hoursContext = 'Horaire spécial';
      event.isClosed = false;
    }
  }

  return Array.from(events.values())
    .sort((left, right) => left.date.localeCompare(right.date))
    .slice(0, 10)
    .map((event) => ({
      ...event,
      title: event.titleParts.length > 0 ? event.titleParts.join(' · ') : 'Horaire modifié',
      notes:
        event.notes.length > 0
          ? event.notes
          : event.hasSpecialHours
            ? ["Modification ponctuelle de l'horaire habituel."]
            : [],
    }));
}

export default function OpeningHoursPage() {
  const payload = loadOpeningHoursPayload();
  const holidays = mergeWithQuebecHolidays(payload.holidays);
  const weeklyHours = buildWeeklyHours(payload.openingHours);
  const upcomingSpecialDates = buildUpcomingSpecialDates(payload.openingHours, holidays, payload.specialDates);

  return (
    <div className="page-stack">
      <section className="panel-card">
        <h1 style={{ textAlign: 'center' }}>Horaires</h1>
        <div className="hours-grid spaced-top">
          {weeklyHours.map((row) => (
            <div className="list-card" key={String(row.dayKey)} style={{ gridColumn: `${row.columnStart} / span ${row.span}` }}>
              <strong>{row.dayLabel}</strong>
              <span>{row.hoursText}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel-card">
        <p className="card-subtitle">Avertissement</p>
        <h2 className="section-title">10 prochaines dates spéciales</h2>
        <div className="list-grid spaced-top">
          {upcomingSpecialDates.length > 0 ? upcomingSpecialDates.map((item) => (
            <div className="list-card" key={item.date}>
              <strong>{`${item.weekdayLabel}, ${item.dateLabel}`}</strong>
              <span>{item.title}</span>
              <div className="badge-row">
                {item.badges.map((badge) => (
                  <span className="badge neutral" key={`${item.date}-${badge}`}>{badge}</span>
                ))}
              </div>
              {item.notes.map((note) => (
                <span className="muted" key={`${item.date}-${note}`}>{note}</span>
              ))}
            </div>
          )) : (
            <div className="list-card">
              <strong>Aucune date spéciale à venir</strong>
              <span>Les horaires hebdomadaires s’appliquent en continu pour le moment.</span>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
