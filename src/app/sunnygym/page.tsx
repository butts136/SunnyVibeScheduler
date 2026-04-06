import { SunnyGymClient } from '@/components/sunnygym-client';
import { getOptionalAuthContext } from '@/lib/auth-guards';
import { buildCalendarDays } from '@/lib/bookings';
import { loadReservationConfig } from '@/lib/configuration';

export default async function SunnyGymPage() {
  const auth = await getOptionalAuthContext();
  const config = loadReservationConfig();

  return (
    <SunnyGymClient
      csrfToken={auth.session?.csrfToken ?? null}
      userCanBook={Boolean(auth.user) && !auth.user?.isBlocked}
      maxCompanions={Math.max(config.maxSimultaneousBookings - 1, 0)}
      days={buildCalendarDays(42, config)}
    />
  );
}
