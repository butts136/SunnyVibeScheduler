'use strict';

(function initCalendarPage() {
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  const monthLabelEl = document.getElementById('monthLabel');
  const calendarGridEl = document.getElementById('calendarGrid');
  const calendarMobileListEl = document.getElementById('calendarMobileList');
  const dayPanelModalEl = document.getElementById('dayPanelModal');
  const closeDayPanelModalBtn = document.getElementById('closeDayPanelModalBtn');
  const prevMonthBtn = document.getElementById('prevMonthBtn');
  const nextMonthBtn = document.getElementById('nextMonthBtn');
  const selectedDateLabelEl = document.getElementById('selectedDateLabel');
  const selectedDateSubtextEl = document.getElementById('selectedDateSubtext');
  const daySummaryEl = document.getElementById('daySummary');
  const timelinePlaceHeadersEl = document.getElementById('timelinePlaceHeaders');
  const timelineContainerEl = document.getElementById('timelineContainer');
  const bookingsOverviewPanelEl = document.getElementById('bookingsOverviewPanel');
  const bookingManagerPanelEl = document.getElementById('bookingManagerPanel');
  const bookingManagerGridEl = document.querySelector('#bookingManagerPanel .booking-manager-grid');
  const bookingManagerPrevDateBtn = document.getElementById('bookingManagerPrevDateBtn');
  const bookingManagerNextDateBtn = document.getElementById('bookingManagerNextDateBtn');
  const bookingManagerDateBtn = document.getElementById('bookingManagerDateBtn');
  const bookingManagerDateLabelEl = document.getElementById('bookingManagerDateLabel');
  const adminCardTitleEl = document.querySelector('.admin-card > h1');
  const bookingsDayPanelHeadEl = document.querySelector('#bookings-panel .day-panel-head');
  const adminBookingsDetailsDateLabelEl = document.getElementById('adminBookingsDetailsDateLabel');
  const addBookingBtn = document.getElementById('addBookingBtn');
  const bookingModal = document.getElementById('bookingModal');
  const closeBookingModalBtn = document.getElementById('closeBookingModalBtn');
  const bookingForm = document.getElementById('bookingForm');
  const bookingDateInput = document.getElementById('bookingDateInput');
  const bookingStartInput = document.getElementById('bookingStartInput');
  const bookingEndInput = document.getElementById('bookingEndInput');
  const bookingTitleInput = document.getElementById('bookingTitleInput');
  const bookingCompanionCountInput = document.getElementById('bookingCompanionCountInput');
  const bookingCompanionWrap = document.getElementById('bookingCompanionWrap');
  const bookingPrivateInput = document.getElementById('bookingPrivateInput');
  const bookingPrivateWrap = document.getElementById('bookingPrivateWrap');
  const bookingFormMessage = document.getElementById('bookingFormMessage');
  const bookingRules = document.getElementById('bookingRules');
  const timeArrowButtons = document.querySelectorAll('.time-arrow-btn');
  const isBookingsDashboardPage = Boolean(
    bookingsOverviewPanelEl
    && bookingManagerPanelEl
    && bookingManagerPrevDateBtn
    && bookingManagerNextDateBtn
    && bookingManagerDateBtn
    && bookingManagerDateLabelEl
  );
  let bookingsManagerRerenderFrame = 0;

  if (!monthLabelEl || !calendarGridEl || !prevMonthBtn || !nextMonthBtn) {
    return;
  }

  const configuredToday = typeof window.SUNNYVIBE_TODAY_KEY === 'string'
    ? parseDateKey(window.SUNNYVIBE_TODAY_KEY)
    : null;
  const today = startOfDay(configuredToday || new Date());
  const minimumMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const usesDayPanelModal = Boolean(dayPanelModalEl);
  const isAdminMode = Boolean(window.SUNNYVIBE_ADMIN_MODE);
  const HOUR_HEIGHT = isAdminMode ? 32 : 42;
  const isCalendarPage = document.body.classList.contains('calendar-body');
  const calendarPanelEl = document.querySelector('.calendar-panel');
  const state = {
    viewMonth: new Date(today.getFullYear(), today.getMonth(), 1),
    selectedDate: usesDayPanelModal ? null : (isBookingsDashboardPage ? null : new Date(today)),
  };
  const dayPanelEl = document.getElementById('dayPanel') || document.querySelector('.day-panel');

  const availabilityCache = new Map();
  const configuredOpeningHours = sanitizeOpeningHours(window.SUNNYVIBE_OPENING_HOURS || {});
  const configuredHolidays = sanitizeHolidays(window.SUNNYVIBE_HOLIDAYS || []);
  const configuredSpecialDates = sanitizeSpecialDates(window.SUNNYVIBE_SPECIAL_DATES || []);
  const configuredReservationConfig = sanitizeReservationConfig(window.SUNNYVIBE_RESERVATION_CONFIG || {});
  const configuredBookings = sanitizeBookings(window.SUNNYVIBE_BOOKINGS || {});
  const configuredBlockedRules = sanitizeBlockedRules(window.SUNNYVIBE_BLOCKED_RULES || []);
  const configuredActiveSlots = sanitizeActiveSlots(window.SUNNYVIBE_ACTIVE_SLOTS || []);
  const userCanBook = Boolean(window.SUNNYVIBE_USER_CAN_BOOK);
  const createBookingApiUrl = resolveApiUrl(window.SUNNYVIBE_API_BOOKINGS_URL || 'api/bookings');
  const timeInputDirection = new WeakMap();
  const previousTimeValue = new WeakMap();
  const isCardsAvailabilityMode = (
    configuredReservationConfig.availability_mode === 'active_slots'
    && configuredReservationConfig.sunnygym_display_mode === 'cards'
  );
  const isSunnygymCardsMode = (
    Boolean(calendarMobileListEl)
    && (isCardsAvailabilityMode || isBookingsDashboardPage)
    && (isCalendarPage || isAdminMode || isBookingsDashboardPage)
  );
  let bookingsDashboardMode = isBookingsDashboardPage ? 'overview' : '';

  if (calendarPanelEl) {
    calendarPanelEl.classList.toggle('cards-mode', isSunnygymCardsMode);
  }

  const bookingsManagerResizeObserver =
    window.ResizeObserver && bookingManagerGridEl
      ? new ResizeObserver(() => {
          if (isBookingsDashboardPage && bookingsDashboardMode === 'manager') {
            scheduleBookingsManagerRerender();
          }
        })
      : null;

  prevMonthBtn.addEventListener('click', () => {
    if (isSameMonth(state.viewMonth, minimumMonth)) {
      return;
    }

    state.viewMonth = new Date(state.viewMonth.getFullYear(), state.viewMonth.getMonth() - 1, 1);

    if (state.selectedDate && !isInMonth(state.selectedDate, state.viewMonth)) {
      state.selectedDate = getDefaultSelectionForMonth(state.viewMonth, today);
    }

    render();
  });

  nextMonthBtn.addEventListener('click', () => {
    state.viewMonth = new Date(state.viewMonth.getFullYear(), state.viewMonth.getMonth() + 1, 1);

    if (state.selectedDate && !isInMonth(state.selectedDate, state.viewMonth)) {
      state.selectedDate = getDefaultSelectionForMonth(state.viewMonth, today);
    }

    render();
  });

  if (usesDayPanelModal && dayPanelModalEl) {
    if (closeDayPanelModalBtn) {
      closeDayPanelModalBtn.addEventListener('click', closeDayPanelModal);
    }
    dayPanelModalEl.addEventListener('click', (event) => {
      if (event.target === dayPanelModalEl) {
        closeDayPanelModal();
      }
    });
    dayPanelModalEl.addEventListener('close', () => {
      document.body.classList.remove('calendar-day-modal-open');
    });
  }

  if (userCanBook && addBookingBtn && bookingModal && bookingForm) {
    registerForwardRolloverFix(bookingStartInput);
    registerForwardRolloverFix(bookingEndInput);

    addBookingBtn.addEventListener('click', () => {
      if (!state.selectedDate) {
        return;
      }

      const selectedDateKey = toDateKey(state.selectedDate);
      const dayData = getDayData(state.selectedDate);

      bookingDateInput.value = selectedDateKey;
      bookingDateInput.min = toDateKey(today);

      bookingStartInput.step = configuredReservationConfig.fixed_time_only
        ? String(configuredReservationConfig.fixed_time_interval_minutes * 60)
        : '60';
      bookingEndInput.step = configuredReservationConfig.fixed_time_only
        ? String(configuredReservationConfig.fixed_time_interval_minutes * 60)
        : '60';

      const firstAvailable = dayData.availableIntervals[0];
      if (firstAvailable) {
        bookingStartInput.value = hourToTimeText(firstAvailable.start);
        let defaultEndHour = firstAvailable.start + (configuredReservationConfig.min_duration_minutes / 60);
        if (defaultEndHour > firstAvailable.end) {
          defaultEndHour = firstAvailable.end;
        }
        bookingEndInput.value = hourToTimeText(defaultEndHour);
      } else {
        bookingStartInput.value = '';
        bookingEndInput.value = '';
      }

      bookingTitleInput.value = '';
      if (bookingCompanionCountInput) {
        bookingCompanionCountInput.value = '0';
        bookingCompanionCountInput.min = '0';
        const maxCompanions = configuredReservationConfig.allow_companion_booking
          ? Math.max(configuredReservationConfig.max_simultaneous_bookings - 1, 0)
          : 0;
        bookingCompanionCountInput.max = String(maxCompanions);
      }
      if (bookingPrivateInput) {
        bookingPrivateInput.checked = false;
      }
      renderBookingRules();
      setBookingFormMessage('', '');
      previousTimeValue.set(bookingStartInput, bookingStartInput.value);
      previousTimeValue.set(bookingEndInput, bookingEndInput.value);
      if (usesDayPanelModal && dayPanelModalEl && dayPanelModalEl.open) {
        closeDayPanelModal();
      }
      bookingModal.showModal();
    });

    closeBookingModalBtn.addEventListener('click', () => {
      bookingModal.close();
    });

    bookingForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      setBookingFormMessage('', '');

      const payload = {
        date: bookingDateInput.value,
        start_time: bookingStartInput.value,
        end_time: bookingEndInput.value,
        title: bookingTitleInput.value.trim(),
        companion_count: bookingCompanionCountInput ? bookingCompanionCountInput.value : '0',
        is_private: bookingPrivateInput ? bookingPrivateInput.checked : false,
      };

      if (!payload.date || !payload.start_time || !payload.end_time) {
        setBookingFormMessage('Veuillez remplir la date et les heures.', 'error');
        return;
      }

      const companionCount = Number(payload.companion_count);
      if (!Number.isInteger(companionCount) || companionCount < 0) {
        setBookingFormMessage("Nombre d'accompagnateurs invalide.", 'error');
        return;
      }

      if ((companionCount + 1) > configuredReservationConfig.max_simultaneous_bookings) {
        setBookingFormMessage("Le nombre de personnes dépasse la capacité autorisée.", 'error');
        return;
      }
      if (companionCount > 0 && !configuredReservationConfig.allow_companion_booking) {
        setBookingFormMessage("Les accompagnateurs sont désactivés.", 'error');
        return;
      }

      if (payload.is_private && !configuredReservationConfig.allow_private_room_choice) {
        setBookingFormMessage("L'option de réservation privée n'est pas activée.", 'error');
        return;
      }

      if (timeTextToMinutes(payload.end_time) <= timeTextToMinutes(payload.start_time)) {
        setBookingFormMessage("L'heure de fin doit être après l'heure de début.", 'error');
        return;
      }

      const selectedDate = parseDateKey(payload.date);
      if (!selectedDate) {
        setBookingFormMessage('Date invalide.', 'error');
        return;
      }

      const dayWindows = getWindowsForDay(selectedDate);
      const startHour = timeTextToHour(payload.start_time);
      const endHour = timeTextToHour(payload.end_time);
      const insideWindow = dayWindows.some((window) => startHour >= window.start && endHour <= window.end);
      if (!insideWindow) {
        const modeLabel = configuredReservationConfig.availability_mode === 'active_slots'
          ? 'Plage hors créneaux activés.'
          : "Plage hors heures d'ouverture.";
        setBookingFormMessage(modeLabel, 'error');
        return;
      }

      try {
        const response = await fetch(createBookingApiUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok || !data.ok) {
          setBookingFormMessage(data.error || 'Réservation impossible.', 'error');
          return;
        }

        configuredBookings[payload.date] = configuredBookings[payload.date] || [];
        configuredBookings[payload.date].push({
          start: payload.start_time,
          end: payload.end_time,
          people_count: companionCount + 1,
          is_private: Boolean(payload.is_private),
        });
        availabilityCache.clear();
        state.selectedDate = selectedDate;
        render();

        setBookingFormMessage('Réservation ajoutée avec succès.', 'success');
        window.setTimeout(() => bookingModal.close(), 700);
      } catch (error) {
        setBookingFormMessage('Erreur réseau. Réessayez.', 'error');
      }
    });

    timeArrowButtons.forEach((button) => {
      button.addEventListener('click', () => {
        const targetId = button.dataset.target;
        const direction = button.dataset.direction;
        if (!targetId || !direction) {
          return;
        }

        const inputEl = document.getElementById(targetId);
        if (!inputEl) {
          return;
        }

        nudgeTimeInput(inputEl, direction);
        if (inputEl === bookingStartInput) {
          autoAdjustEndTime();
        }
      });
    });

    bookingStartInput.addEventListener('input', () => {
      autoAdjustEndTime();
    });

    bookingStartInput.addEventListener('change', () => {
      autoAdjustEndTime();
    });

    bookingEndInput.addEventListener('input', () => {
      normalizeEndTimeWithinRules(timeInputDirection.get(bookingEndInput));
    });

    bookingEndInput.addEventListener('change', () => {
      normalizeEndTimeWithinRules(timeInputDirection.get(bookingEndInput));
    });

    bookingDateInput.addEventListener('change', () => {
      const selectedDate = parseDateKey(bookingDateInput.value);
      if (!selectedDate) {
        return;
      }

      const currentStart = timeTextToMinutes(bookingStartInput.value);
      if (currentStart === null) {
        const dayData = getDayData(selectedDate);
        const firstAvailable = dayData.availableIntervals[0];
        if (firstAvailable) {
          bookingStartInput.value = hourToTimeText(firstAvailable.start);
          autoAdjustEndTime();
        }
        return;
      }

      autoAdjustEndTime();
    });

  if (bookingCompanionCountInput) {
      const clampCompanionCount = () => {
        const rawValue = bookingCompanionCountInput.value.trim();
        const maxAllowed = configuredReservationConfig.allow_companion_booking
          ? Math.max(configuredReservationConfig.max_simultaneous_bookings - 1, 0)
          : 0;
        if (rawValue === '') {
          bookingCompanionCountInput.value = '0';
          return;
        }

        let parsed = Number(rawValue);
        if (!Number.isFinite(parsed)) {
          parsed = 0;
        }

        parsed = Math.max(0, Math.min(Math.floor(parsed), maxAllowed));
        bookingCompanionCountInput.value = String(parsed);
      };

      bookingCompanionCountInput.addEventListener('input', clampCompanionCount);
      bookingCompanionCountInput.addEventListener('change', clampCompanionCount);
    }
  }

  if (isBookingsDashboardPage) {
    bookingManagerPrevDateBtn.addEventListener('click', () => {
      shiftBookingsSelectedDate(-1);
    });

    bookingManagerNextDateBtn.addEventListener('click', () => {
      shiftBookingsSelectedDate(1);
    });

    bookingManagerDateBtn.addEventListener('click', () => {
      showBookingsOverview();
    });

    syncBookingsDashboardVisibility();
  }

  function registerForwardRolloverFix(inputEl) {
    if (!inputEl) {
      return;
    }

    inputEl.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowUp') {
        timeInputDirection.set(inputEl, 'up');
      } else if (event.key === 'ArrowDown') {
        timeInputDirection.set(inputEl, 'down');
      }
    });

    inputEl.addEventListener('wheel', (event) => {
      if (document.activeElement !== inputEl) {
        return;
      }

      timeInputDirection.set(inputEl, event.deltaY < 0 ? 'up' : 'down');
    });

    const applyFix = () => {
      const currentValue = inputEl.value;
      const currentMinutes = timeTextToMinutes(currentValue);
      const previousValue = previousTimeValue.get(inputEl);
      const previousMinutes = timeTextToMinutes(previousValue || '');
      const direction = timeInputDirection.get(inputEl);

      if (currentMinutes !== null && previousMinutes !== null && direction === 'up') {
        const previousHour = Math.floor(previousMinutes / 60);
        const currentHour = Math.floor(currentMinutes / 60);
        const previousMinutePart = previousMinutes % 60;
        const currentMinutePart = currentMinutes % 60;

        const wrappedInSameHour = previousHour === currentHour && previousMinutePart > currentMinutePart;
        if (wrappedInSameHour && currentMinutePart === 0) {
          const corrected = (currentMinutes + 60) % (24 * 60);
          inputEl.value = minutesToTimeText(corrected);
        }
      }

      previousTimeValue.set(inputEl, inputEl.value);
    };

    inputEl.addEventListener('input', applyFix);
    inputEl.addEventListener('change', applyFix);
    inputEl.addEventListener('blur', () => {
      timeInputDirection.delete(inputEl);
      previousTimeValue.set(inputEl, inputEl.value);
    });
  }

  function nudgeTimeInput(inputEl, direction) {
    if (!inputEl || inputEl.type !== 'time') {
      return;
    }

    if (inputEl === bookingEndInput) {
      nudgeEndInputWithinRules(direction);
      return;
    }

    timeInputDirection.set(inputEl, direction === 'up' ? 'up' : 'down');
    inputEl.focus();

    try {
      if (direction === 'up') {
        inputEl.stepUp();
      } else {
        inputEl.stepDown();
      }
    } catch (error) {
      const currentMinutes = timeTextToMinutes(inputEl.value);
      if (currentMinutes === null) {
        return;
      }

      const stepSeconds = Number(inputEl.step) || 60;
      const stepMinutes = Math.max(Math.round(stepSeconds / 60), 1);
      const delta = direction === 'up' ? stepMinutes : -stepMinutes;
      const next = (currentMinutes + delta + (24 * 60)) % (24 * 60);
      inputEl.value = minutesToTimeText(next);
    }

    inputEl.dispatchEvent(new Event('input', { bubbles: true }));
    inputEl.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function nudgeEndInputWithinRules(direction) {
    const context = getBookingContext();
    if (!context || !context.validEndMinutes.length) {
      bookingEndInput.value = '';
      return;
    }

    const currentEnd = timeTextToMinutes(bookingEndInput.value);
    const valid = context.validEndMinutes;
    let next = valid[0];

    if (currentEnd !== null && valid.includes(currentEnd)) {
      if (direction === 'up') {
        next = valid.find((value) => value > currentEnd) ?? valid[valid.length - 1];
      } else {
        const lower = valid.filter((value) => value < currentEnd);
        next = lower.length ? lower[lower.length - 1] : valid[0];
      }
    } else if (currentEnd !== null) {
      next = pickBestEndMinute(valid, currentEnd, direction);
    } else {
      next = direction === 'down' ? valid[valid.length - 1] : valid[0];
    }

    timeInputDirection.set(bookingEndInput, direction === 'down' ? 'down' : 'up');
    bookingEndInput.value = minutesToTimeText(next);
    previousTimeValue.set(bookingEndInput, bookingEndInput.value);
    bookingEndInput.dispatchEvent(new Event('input', { bubbles: true }));
    bookingEndInput.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function autoAdjustEndTime() {
    const context = getBookingContext();
    if (!context || !context.validEndMinutes.length) {
      bookingEndInput.value = '';
      return;
    }

    const currentEnd = timeTextToMinutes(bookingEndInput.value);
    if (currentEnd !== null && context.validEndMinutes.includes(currentEnd)) {
      return;
    }

    bookingEndInput.value = minutesToTimeText(context.validEndMinutes[0]);
    previousTimeValue.set(bookingEndInput, bookingEndInput.value);
  }

  function getValidEndMinutes(date, startMinutes) {
    const windows = getWindowsForDay(date).map((window) => ({
      start: Math.round(window.start * 60),
      end: Math.round(window.end * 60),
    }));

    const containingWindow = windows.find((window) => startMinutes >= window.start && startMinutes < window.end);
    if (!containingWindow) {
      return [];
    }

    if (startMinutes > (containingWindow.end - configuredReservationConfig.latest_start_before_close_minutes)) {
      return [];
    }

    const validEnds = [];
    for (let end = startMinutes + 1; end <= containingWindow.end; end += 1) {
      const duration = end - startMinutes;

      if (duration < configuredReservationConfig.min_duration_minutes) {
        continue;
      }
      if (duration > configuredReservationConfig.max_duration_minutes) {
        break;
      }
      if (configuredReservationConfig.slot_interval_enabled) {
        const step = configuredReservationConfig.slot_interval_minutes;
        if (duration % step !== 0) {
          continue;
        }
      }
      if (configuredReservationConfig.fixed_time_only) {
        const fixedStep = configuredReservationConfig.fixed_time_interval_minutes;
        if ((startMinutes % fixedStep) !== 0 || (end % fixedStep) !== 0) {
          continue;
        }
      }

      validEnds.push(end);
    }

    return validEnds;
  }

  function getBookingContext() {
    const selectedDate = parseDateKey(bookingDateInput.value);
    const startMinutes = timeTextToMinutes(bookingStartInput.value);
    if (!selectedDate || startMinutes === null) {
      return null;
    }

    return {
      selectedDate,
      startMinutes,
      validEndMinutes: getValidEndMinutes(selectedDate, startMinutes),
    };
  }

  function normalizeEndTimeWithinRules(preferredDirection) {
    const context = getBookingContext();
    if (!context || !context.validEndMinutes.length) {
      bookingEndInput.value = '';
      return;
    }

    const currentEnd = timeTextToMinutes(bookingEndInput.value);
    if (currentEnd !== null && context.validEndMinutes.includes(currentEnd)) {
      return;
    }

    const next = pickBestEndMinute(context.validEndMinutes, currentEnd, preferredDirection);
    bookingEndInput.value = minutesToTimeText(next);
    previousTimeValue.set(bookingEndInput, bookingEndInput.value);
  }

  function pickBestEndMinute(validEndMinutes, currentEnd, preferredDirection) {
    if (!validEndMinutes.length) {
      return null;
    }

    if (currentEnd === null) {
      return validEndMinutes[0];
    }

    if (preferredDirection === 'up') {
      return validEndMinutes.find((value) => value >= currentEnd) ?? validEndMinutes[validEndMinutes.length - 1];
    }

    if (preferredDirection === 'down') {
      const lowerOrEqual = validEndMinutes.filter((value) => value <= currentEnd);
      return lowerOrEqual.length ? lowerOrEqual[lowerOrEqual.length - 1] : validEndMinutes[0];
    }

    let best = validEndMinutes[0];
    let bestDistance = Math.abs(best - currentEnd);

    for (let i = 1; i < validEndMinutes.length; i += 1) {
      const candidate = validEndMinutes[i];
      const distance = Math.abs(candidate - currentEnd);
      if (distance < bestDistance) {
        best = candidate;
        bestDistance = distance;
      }
    }

    return best;
  }

  function render() {
    renderMonthHeader();
    renderCalendarGrid();
    renderCalendarMobileList();
    renderSelectedDayPanel();
  }

  function renderMonthHeader() {
    monthLabelEl.textContent = new Intl.DateTimeFormat('fr-CA', {
      month: 'long',
      year: 'numeric',
    }).format(state.viewMonth);

    prevMonthBtn.disabled = isSameMonth(state.viewMonth, minimumMonth);
  }

  function renderCalendarGrid() {
    if (isSunnygymCardsMode) {
      calendarGridEl.innerHTML = '';
      return;
    }

    calendarGridEl.innerHTML = '';

    const year = state.viewMonth.getFullYear();
    const month = state.viewMonth.getMonth();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const firstDayWeekIndex = mondayIndex(new Date(year, month, 1).getDay());
    const totalCells = Math.ceil((firstDayWeekIndex + daysInMonth) / 7) * 7;

    for (let cellIndex = 0; cellIndex < totalCells; cellIndex += 1) {
      const dayNumber = cellIndex - firstDayWeekIndex + 1;
      const isCurrentMonthDay = dayNumber >= 1 && dayNumber <= daysInMonth;
      const cellBtn = document.createElement('button');
      cellBtn.type = 'button';
      cellBtn.className = 'day-cell';

      if (!isCurrentMonthDay) {
        cellBtn.classList.add('outside');
        cellBtn.disabled = true;
        cellBtn.setAttribute('aria-hidden', 'true');
        calendarGridEl.appendChild(cellBtn);
        continue;
      }

      const cellDate = new Date(year, month, dayNumber);
      const dayData = getDayData(cellDate);
      const isToday = isSameDay(cellDate, today);
      const isSelected = isSameDay(cellDate, state.selectedDate);
      const isPast = cellDate < today;
      const showFinishedBadge = isPast && isCalendarPage;
      const holidayData = getHolidayForDate(cellDate);

      cellBtn.dataset.dateKey = toDateKey(cellDate);
      const dateLabel = new Intl.DateTimeFormat('fr-CA', {
        day: 'numeric',
        month: 'short',
      }).format(cellDate);
      const hoursLabel = formatWindowsLabel(dayData.windows);
      const isClosedDay = dayData.totalMinutes === 0;
      const bookingCount = getBookingCountForDate(cellDate);
      const dayStateText = showFinishedBadge
        ? 'Terminé'
        : (isClosedDay
          ? 'Fermé'
          : (isAdminMode
            ? `${bookingCount} rés.`
            : (dayData.hasPartialReservations ? 'Partiel' : (dayData.hasAvailability ? 'Disponible' : 'Complet'))));
      cellBtn.innerHTML = `
        <div class="date-label">${escapeHtml(dateLabel)}</div>
        <div class="hours-label">${escapeHtml(hoursLabel)}</div>
        <div class="day-state-pill">${escapeHtml(dayStateText)}</div>
        ${holidayData ? `<div class="holiday-name">${escapeHtml(holidayData.name)}</div><div class="holiday-alert">${escapeHtml(holidayData.alert)}</div>` : ''}
      `;

      if (isClosedDay) {
        cellBtn.classList.add('full');
      } else {
        if (!dayData.hasAvailability) {
          cellBtn.classList.add('full');
        } else if (dayData.hasPartialReservations) {
          cellBtn.classList.add('partial');
        } else {
          cellBtn.classList.add('available');
        }
      }

      if (isToday) {
        cellBtn.classList.add('today');
      }
      if (holidayData) {
        cellBtn.classList.add('holiday');
      }

      if (isSelected) {
        cellBtn.classList.add('selected');
      }

      if (isPast) {
        cellBtn.classList.add('past');
      }

      if (isPast) {
        cellBtn.disabled = true;
      } else {
        cellBtn.addEventListener('click', () => {
          selectDate(cellDate);
        });
      }

      calendarGridEl.appendChild(cellBtn);
    }
  }

  function renderCalendarMobileList() {
    if (!calendarMobileListEl) {
      return;
    }

    if (isSunnygymCardsMode) {
      renderSunnygymCardsModeList();
      return;
    }

    calendarMobileListEl.classList.remove('is-desktop-cards');
    calendarMobileListEl.innerHTML = '';

    const year = state.viewMonth.getFullYear();
    const month = state.viewMonth.getMonth();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const monthTitle = new Intl.DateTimeFormat('fr-CA', {
      month: 'long',
      year: 'numeric',
    }).format(state.viewMonth);

    const divider = document.createElement('div');
    divider.className = 'calendar-mobile-month-divider';
    divider.textContent = monthTitle;
    calendarMobileListEl.appendChild(divider);

    let renderedDays = 0;
    for (let dayNumber = 1; dayNumber <= daysInMonth; dayNumber += 1) {
      const cellDate = new Date(year, month, dayNumber);
      const dayData = getDayData(cellDate);
      const isToday = isSameDay(cellDate, today);
      const isSelected = isSameDay(cellDate, state.selectedDate);
      const isPast = cellDate < today;
      if (isPast) {
        continue;
      }
      const holidayData = getHolidayForDate(cellDate);
      const isClosedDay = dayData.totalMinutes === 0;
      const bookingCount = getBookingCountForDate(cellDate);
      const dayStateText = isClosedDay
        ? 'Fermé'
        : (isAdminMode
          ? `${bookingCount} rés.`
          : (dayData.hasPartialReservations ? 'Partiel' : (dayData.hasAvailability ? 'Disponible' : 'Complet')));

      const dateWeekday = new Intl.DateTimeFormat('fr-CA', { weekday: 'long' }).format(cellDate);
      const dateLong = new Intl.DateTimeFormat('fr-CA', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }).format(cellDate);
      const hoursLabel = formatWindowsLabel(dayData.windows);

      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'calendar-mobile-day-card';
      if (isClosedDay) {
        card.classList.add('full');
      } else if (!dayData.hasAvailability) {
        card.classList.add('full');
      } else if (dayData.hasPartialReservations) {
        card.classList.add('partial');
      } else {
        card.classList.add('available');
      }
      if (isToday) {
        card.classList.add('today');
      }
      if (isSelected) {
        card.classList.add('selected');
      }
      if (isPast) {
        card.classList.add('past');
      }
      if (holidayData) {
        card.classList.add('holiday');
      }

      card.innerHTML = `
        <p class="calendar-mobile-weekday">${escapeHtml(dateWeekday)}</p>
        <p class="calendar-mobile-date">${escapeHtml(dateLong)}</p>
        <p class="calendar-mobile-hours">${escapeHtml(hoursLabel)}</p>
        <p class="calendar-mobile-state">${escapeHtml(dayStateText)}</p>
        ${holidayData ? `<p class="calendar-mobile-holiday">${escapeHtml(holidayData.name)}</p>` : ''}
      `;

      if (isPast) {
        card.disabled = true;
      } else {
        card.addEventListener('click', () => {
          selectDate(cellDate);
        });
      }

      calendarMobileListEl.appendChild(card);
      renderedDays += 1;
    }

    if (renderedDays === 0) {
      const emptyState = document.createElement('div');
      emptyState.className = 'calendar-mobile-empty-month';
      emptyState.textContent = 'Aucune date à venir pour ce mois.';
      calendarMobileListEl.appendChild(emptyState);
    }
  }

  function renderSunnygymCardsModeList() {
    if (isBookingsDashboardPage && bookingsDashboardMode !== 'overview') {
      calendarMobileListEl.innerHTML = '';
      calendarMobileListEl.classList.remove('is-desktop-cards');
      return;
    }

    if (isBookingsDashboardPage) {
      renderBookingsOverviewList();
      return;
    }

    calendarMobileListEl.innerHTML = '';
    calendarMobileListEl.classList.add('is-desktop-cards');

    const introCard = document.createElement('section');
    introCard.className = 'sunnygym-cards-intro';
    introCard.innerHTML = `
      <p class="sunnygym-cards-kicker">Plages activées</p>
      <h3>Réservez parmi les prochaines ouvertures disponibles</h3>
    `;
    calendarMobileListEl.appendChild(introCard);

    const activeSlotsByDate = new Map();
    configuredActiveSlots.forEach((slot) => {
      const slotDate = parseDateKey(slot.date);
      if (!slotDate || startOfDay(slotDate) < today) {
        return;
      }

      if (!activeSlotsByDate.has(slot.date)) {
        activeSlotsByDate.set(slot.date, []);
      }
      activeSlotsByDate.get(slot.date).push(slot);
    });

    const uniqueFutureDateKeys = Array.from(activeSlotsByDate.keys()).sort((a, b) => a.localeCompare(b));

    let renderedCards = 0;
    uniqueFutureDateKeys.forEach((dateKey) => {
      const dateObj = parseDateKey(dateKey);
      if (!dateObj) {
        return;
      }

      const dateSlots = activeSlotsByDate.get(dateKey) || [];
      if (!dateSlots.length) {
        return;
      }

      const activeWindows = mergeTimeWindows(
        dateSlots.map((slot) => ({
          start: timeTextToHour(slot.start),
          end: timeTextToHour(slot.end),
        }))
      );
      const displayIntervals = activeWindows.length
        ? activeWindows
        : dateSlots.map((slot) => ({
          start: timeTextToHour(slot.start),
          end: timeTextToHour(slot.end),
        }));

      const dateWeekday = new Intl.DateTimeFormat('fr-CA', { weekday: 'long' }).format(dateObj);
      const dateLong = new Intl.DateTimeFormat('fr-CA', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }).format(dateObj);
      const availableIntervalsLabel = displayIntervals
        .map((interval) => `${formatHour(interval.start)} - ${formatHour(interval.end)}`)
        .join(' | ');
      const slotTitles = Array.from(new Set(dateSlots.map((slot) => slot.title).filter(Boolean)));
      const slotTitleLabel = slotTitles.length ? slotTitles.join(' · ') : 'Plage activée';
      const holidayData = getHolidayForDate(dateObj);

      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'calendar-mobile-day-card sunnygym-slot-card available';
      if (isSameDay(dateObj, today)) {
        card.classList.add('today');
      }
      if (isSameDay(dateObj, state.selectedDate)) {
        card.classList.add('selected');
      }
      if (holidayData) {
        card.classList.add('holiday');
      }

      card.innerHTML = `
        <div class="sunnygym-slot-card__head">
          <div>
            <p class="calendar-mobile-weekday">${escapeHtml(dateWeekday)}</p>
            <p class="calendar-mobile-date">${escapeHtml(dateLong)}</p>
          </div>
          <span class="sunnygym-slot-card__badge">${isSameDay(dateObj, today) ? 'Aujourd’hui' : 'À venir'}</span>
        </div>
        <div class="sunnygym-slot-card__schedule">
          <p class="sunnygym-slot-card__label">Créneaux actifs</p>
          <p class="calendar-mobile-hours">${escapeHtml(availableIntervalsLabel)}</p>
        </div>
        <div class="sunnygym-slot-card__meta">
          <p class="sunnygym-slot-card__label">Titre</p>
          <p class="sunnygym-slot-card__meta-value">${escapeHtml(slotTitleLabel)}</p>
        </div>
        <div class="sunnygym-slot-card__footer">
          <span class="sunnygym-slot-card__cta">Voir le détail</span>
        </div>
        ${holidayData ? `<p class="calendar-mobile-holiday">${escapeHtml(holidayData.name)}</p>` : ''}
      `;
      card.addEventListener('click', () => {
        selectDate(dateObj);
      });

      calendarMobileListEl.appendChild(card);
      renderedCards += 1;
    });

    if (!renderedCards) {
      const emptyState = document.createElement('div');
      emptyState.className = 'calendar-mobile-empty-month';
      emptyState.textContent = 'Aucune plage horaire disponible à venir.';
      calendarMobileListEl.appendChild(emptyState);
    }
  }

  function renderSelectedDayPanel() {
    if (!state.selectedDate) {
      if (dayPanelEl && !usesDayPanelModal) {
        dayPanelEl.hidden = true;
        dayPanelEl.setAttribute('hidden', 'hidden');
      }

      if (selectedDateLabelEl) {
        selectedDateLabelEl.textContent = 'Jour sélectionné';
      }
      if (selectedDateSubtextEl) {
        selectedDateSubtextEl.textContent = 'Sélectionnez une date dans le calendrier.';
      }
      if (daySummaryEl) {
        daySummaryEl.innerHTML = '';
      }
      if (timelinePlaceHeadersEl) {
        timelinePlaceHeadersEl.innerHTML = '';
        timelinePlaceHeadersEl.hidden = true;
      }
      if (timelineContainerEl) {
        timelineContainerEl.innerHTML = '';
      }
      if (addBookingBtn) {
        addBookingBtn.disabled = true;
      }
      return;
    }

    if (dayPanelEl) {
      dayPanelEl.hidden = false;
      dayPanelEl.removeAttribute('hidden');
    }

    const data = getDayData(state.selectedDate);
    const windowsLabel = data.windows.map((window) => `${formatHour(window.start)} - ${formatHour(window.end)}`).join(' | ');
    const selectedDateKey = toDateKey(state.selectedDate);

    selectedDateLabelEl.textContent = new Intl.DateTimeFormat('fr-CA', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }).format(state.selectedDate);

    window.dispatchEvent(
      new CustomEvent('sunnyvibe:calendar-date-change', {
        detail: { dateKey: selectedDateKey },
      })
    );

    if (data.totalMinutes === 0) {
      selectedDateSubtextEl.textContent = 'Salle fermée pour cette journée.';
    } else if (data.hasAvailability) {
      selectedDateSubtextEl.textContent = `Plage ouverte: ${windowsLabel}. Des plages sont encore disponibles.`;
    } else {
      selectedDateSubtextEl.textContent = `Plage ouverte: ${windowsLabel}. Plus aucune disponibilité pour cette journée.`;
    }

    daySummaryEl.innerHTML = '';

    if (addBookingBtn) {
      addBookingBtn.disabled = !data.hasAvailability;
    }

    renderTimelinePlaceHeaders(data.capacity, data.windows.length > 0);

    if (data.windows.length === 0) {
      timelineContainerEl.innerHTML = '<div class="empty-state">Aucune plage horaire n\'est disponible pour ce jour.</div>';
      return;
    }

    const startMinutes = Math.round(Math.min(...data.windows.map((window) => window.start * 60)));
    const endMinutes = Math.round(Math.max(...data.windows.map((window) => window.end * 60)));
    const spanMinutes = Math.max(endMinutes - startMinutes, 1);
    let timelineScale = 1;
    let availableHeight = 0;
    if (isBookingsDashboardPage && bookingsDashboardMode === 'manager' && timelineContainerEl) {
      const timelineStyles = window.getComputedStyle(timelineContainerEl);
      const verticalPadding = (parseFloat(timelineStyles.paddingTop) || 0) + (parseFloat(timelineStyles.paddingBottom) || 0);
      availableHeight = Math.max(timelineContainerEl.clientHeight - verticalPadding, 0);
      const baseHeight = (spanMinutes * HOUR_HEIGHT) / 60;
      if (availableHeight > 0 && baseHeight > 0) {
        timelineScale = availableHeight / baseHeight;
      }
    }
    const timelineMinuteHeight = (HOUR_HEIGHT * timelineScale) / 60;
    const trackHeight = spanMinutes * timelineMinuteHeight;
    const tickStepMinutes = chooseTimelineStepMinutes(spanMinutes, availableHeight);

    const timelineTrackEl = document.createElement('div');
    timelineTrackEl.className = 'timeline-track';
    timelineTrackEl.style.height = `${trackHeight}px`;
    timelineTrackEl.style.setProperty('--capacity', String(Math.max(data.capacity, 1)));

    let lastRenderedMinute = startMinutes - tickStepMinutes;
    for (let minute = startMinutes; minute <= endMinutes; minute += tickStepMinutes) {
      lastRenderedMinute = minute;
      const offsetMinutes = minute - startMinutes;
      const isHourTick = minute % 60 === 0;
      const markerEl = document.createElement('div');
      markerEl.className = `time-marker ${isHourTick ? 'is-hour' : 'is-subtick'}`;
      markerEl.style.top = `${offsetMinutes * timelineMinuteHeight}px`;
      markerEl.textContent = formatHour(minute / 60);
      timelineTrackEl.appendChild(markerEl);

      if (minute < endMinutes) {
        const dividerEl = document.createElement('div');
        dividerEl.className = `time-divider ${isHourTick ? 'is-hour' : 'is-subtick'}`;
        dividerEl.style.top = `${offsetMinutes * timelineMinuteHeight}px`;
        timelineTrackEl.appendChild(dividerEl);
      }
    }

    if (lastRenderedMinute !== endMinutes) {
      const offsetMinutes = endMinutes - startMinutes;
      const isHourTick = endMinutes % 60 === 0;
      const markerEl = document.createElement('div');
      markerEl.className = `time-marker ${isHourTick ? 'is-hour' : 'is-subtick'}`;
      markerEl.style.top = `${offsetMinutes * timelineMinuteHeight}px`;
      markerEl.textContent = formatHour(endMinutes / 60);
      timelineTrackEl.appendChild(markerEl);
    }

    const reservationsLayerEl = document.createElement('div');
    reservationsLayerEl.className = 'timeline-reservations-layer';
    if (isAdminMode) {
      reservationsLayerEl.classList.add('admin-interactive');
    }
    reservationsLayerEl.style.setProperty('--capacity', String(Math.max(data.capacity, 1)));

    const placements = buildReservationPlacementsForDate(state.selectedDate, data.capacity);
    placements.forEach((placement) => {
      const itemEl = document.createElement('article');
      itemEl.className = `timeline-reservation ${placement.kind}`;
      itemEl.style.top = `${(placement.startMinutes - startMinutes) * timelineMinuteHeight}px`;
      itemEl.style.height = `${(placement.endMinutes - placement.startMinutes) * timelineMinuteHeight}px`;
      itemEl.style.left = `${((placement.columnStart - 1) / data.capacity) * 100}%`;
      itemEl.style.width = `${(placement.columnSpan / data.capacity) * 100}%`;
      if (placement.bookingId) {
        itemEl.dataset.bookingId = String(placement.bookingId);
      }
      itemEl.innerHTML = `
        <span class="timeline-reservation-time">${escapeHtml(formatHour(placement.startMinutes / 60))} - ${escapeHtml(formatHour(placement.endMinutes / 60))}</span>
        <span class="timeline-reservation-label">${escapeHtml(placement.label)}</span>
      `;
      if (isAdminMode && placement.bookingId) {
        itemEl.addEventListener('click', () => {
          window.dispatchEvent(
            new CustomEvent('sunnyvibe:calendar-booking-click', {
              detail: { dateKey: selectedDateKey, bookingId: placement.bookingId },
            })
          );
        });
      }
      reservationsLayerEl.appendChild(itemEl);
    });

    timelineTrackEl.appendChild(reservationsLayerEl);

    timelineContainerEl.innerHTML = '';
    timelineContainerEl.appendChild(timelineTrackEl);
  }

  function chooseTimelineStepMinutes(spanMinutes, availableHeight) {
    const candidates = [15, 30, 60];
    const targetSpacing = 76;
    const safeHeight = Math.max(Number(availableHeight) || 0, 0);
    let bestStep = candidates[candidates.length - 1];
    let bestScore = Number.POSITIVE_INFINITY;

    candidates.forEach((candidate) => {
      const ticks = Math.max(1, Math.ceil(spanMinutes / candidate));
      const spacing = safeHeight > 0 ? safeHeight / ticks : 0;
      const score = Math.abs(spacing - targetSpacing);
      if (score < bestScore) {
        bestScore = score;
        bestStep = candidate;
      }
    });

    return bestStep;
  }

  function renderTimelinePlaceHeaders(capacity, visible) {
    if (!timelinePlaceHeadersEl) {
      return;
    }

    timelinePlaceHeadersEl.innerHTML = '';
    if (!visible) {
      timelinePlaceHeadersEl.hidden = true;
      return;
    }

    const totalPlaces = Math.max(1, Number(capacity) || 1);
    timelinePlaceHeadersEl.hidden = false;
    timelinePlaceHeadersEl.style.setProperty('--capacity', String(totalPlaces));
    for (let index = 1; index <= totalPlaces; index += 1) {
      const chip = document.createElement('span');
      chip.className = 'timeline-place-chip';
      chip.textContent = `Place ${index}`;
      timelinePlaceHeadersEl.appendChild(chip);
    }
  }

  function summaryChip(label, value) {
    const chip = document.createElement('div');
    chip.className = 'summary-chip';
    chip.innerHTML = `<small>${label}</small><strong>${value}</strong>`;
    return chip;
  }

  function getDayData(date) {
    const key = toDateKey(date);
    if (availabilityCache.has(key)) {
      return availabilityCache.get(key);
    }

    const windows = getWindowsForDay(date);
    const windowsMinutes = windows.map((window) => ({
      start: Math.round(window.start * 60),
      end: Math.round(window.end * 60),
    }));

    const totalMinutes = windowsMinutes.reduce((sum, window) => sum + (window.end - window.start), 0);
    const capacity = configuredReservationConfig.max_simultaneous_bookings;

    if (totalMinutes === 0) {
      const closedData = {
        windows,
        timelineSegments: [],
        availableIntervals: [],
        totalMinutes: 0,
        fullMinutes: 0,
        availableMinutes: 0,
        capacity,
        hasAvailability: false,
      };
      availabilityCache.set(key, closedData);
      return closedData;
    }

    const timelineSegments = buildCapacitySegments(date, windowsMinutes, capacity);
    const availableIntervals = timelineSegments
      .filter((segment) => segment.type === 'available' || segment.type === 'partial')
      .map((segment) => ({ start: segment.start, end: segment.end }));
    const fullMinutes = timelineSegments
      .filter((segment) => segment.type === 'reserved')
      .reduce((sum, segment) => sum + Math.round((segment.end - segment.start) * 60), 0);
    const availableMinutes = timelineSegments
      .filter((segment) => segment.type === 'available' || segment.type === 'partial')
      .reduce((sum, segment) => sum + Math.round((segment.end - segment.start) * 60), 0);
    const hasPartialReservations = timelineSegments.some((segment) => segment.type === 'partial');

    const dayData = {
      windows,
      timelineSegments,
      availableIntervals,
      totalMinutes,
      fullMinutes,
      availableMinutes,
      capacity,
      hasPartialReservations,
      hasAvailability: availableMinutes > 0,
    };

    availabilityCache.set(key, dayData);
    return dayData;
  }

  function getBookingCountForDate(date) {
    const dateKey = toDateKey(date);
    const rows = configuredBookings[dateKey] || [];
    return rows.length;
  }

  function getMaxConcurrentPeopleForDate(date) {
    const dateKey = toDateKey(date);
    const dateBookings = [
      ...(configuredBookings[dateKey] || []),
      ...getBlockedBookingsForDate(date),
    ];

    if (!dateBookings.length) {
      return 0;
    }

    const points = new Set();
    dateBookings.forEach((booking) => {
      const bookingStart = timeTextToMinutes(booking.start);
      const bookingEnd = timeTextToMinutes(booking.end);
      if (bookingStart === null || bookingEnd === null || bookingEnd <= bookingStart) {
        return;
      }
      points.add(bookingStart);
      points.add(bookingEnd);
    });

    const sortedPoints = [...points].sort((a, b) => a - b);
    if (sortedPoints.length < 2) {
      return 0;
    }

    const safeCapacity = Math.max(Number(configuredReservationConfig.max_simultaneous_bookings) || 1, 1);
    let maxOccupied = 0;

    for (let i = 0; i < sortedPoints.length - 1; i += 1) {
      const segmentStart = sortedPoints[i];
      const segmentEnd = sortedPoints[i + 1];
      if (segmentEnd <= segmentStart) {
        continue;
      }

      let occupied = 0;
      let privateLock = false;

      dateBookings.forEach((booking) => {
        const bookingStart = timeTextToMinutes(booking.start);
        const bookingEnd = timeTextToMinutes(booking.end);
        if (bookingStart === null || bookingEnd === null || bookingEnd <= bookingStart) {
          return;
        }

        if (bookingStart < segmentEnd && bookingEnd > segmentStart) {
          if (booking.is_private) {
            privateLock = true;
          } else {
            occupied += Math.max(Number(booking.people_count) || 1, 1);
          }
        }
      });

      maxOccupied = Math.max(maxOccupied, privateLock ? safeCapacity : occupied);
    }

    return Math.min(maxOccupied, safeCapacity);
  }

  function buildCapacitySegments(date, windowsMinutes, capacity) {
    const dateKey = toDateKey(date);
    const dateBookings = [
      ...(configuredBookings[dateKey] || []),
      ...getBlockedBookingsForDate(date),
    ];
    const points = new Set();

    windowsMinutes.forEach((window) => {
      points.add(window.start);
      points.add(window.end);
    });

    dateBookings.forEach((booking) => {
      const bookingStart = timeTextToMinutes(booking.start);
      const bookingEnd = timeTextToMinutes(booking.end);
      if (bookingStart === null || bookingEnd === null || bookingEnd <= bookingStart) {
        return;
      }

      windowsMinutes.forEach((window) => {
        const start = Math.max(window.start, bookingStart);
        const end = Math.min(window.end, bookingEnd);
        if (end > start) {
          points.add(start);
          points.add(end);
        }
      });
    });

    const sortedPoints = [...points].sort((a, b) => a - b);
    if (sortedPoints.length < 2) {
      return [];
    }

    const rawSegments = [];
    for (let i = 0; i < sortedPoints.length - 1; i += 1) {
      const segmentStart = sortedPoints[i];
      const segmentEnd = sortedPoints[i + 1];
      if (segmentEnd <= segmentStart) {
        continue;
      }

      const insideWindow = windowsMinutes.some((window) => segmentStart >= window.start && segmentEnd <= window.end);
      if (!insideWindow) {
        continue;
      }

      let privateLock = false;
      let blockedLock = false;
      let occupied = 0;
      dateBookings.forEach((booking) => {
        const bookingStart = timeTextToMinutes(booking.start);
        const bookingEnd = timeTextToMinutes(booking.end);
        if (bookingStart === null || bookingEnd === null || bookingEnd <= bookingStart) {
          return;
        }

        if (bookingStart < segmentEnd && bookingEnd > segmentStart) {
          if (booking.is_private) {
            privateLock = true;
            if (booking.is_blocked_slot) {
              blockedLock = true;
            }
          } else {
            occupied += Math.max(Number(booking.people_count) || 1, 1);
          }
        }
      });

      if (privateLock) {
        occupied = capacity;
      } else {
        occupied = Math.min(occupied, capacity);
      }

      const remaining = Math.max(capacity - occupied, 0);
      const type = remaining <= 0 ? 'reserved' : (occupied > 0 ? 'partial' : 'available');
      rawSegments.push({
        start: segmentStart / 60,
        end: segmentEnd / 60,
        type,
        remaining,
        occupied,
        capacity,
        privateLock,
        blockedLock,
      });
    }

    if (!rawSegments.length) {
      return [];
    }

    const merged = [rawSegments[0]];
    for (let i = 1; i < rawSegments.length; i += 1) {
      const current = rawSegments[i];
      const last = merged[merged.length - 1];
      const canMerge = current.type === last.type
        && current.remaining === last.remaining
        && current.privateLock === last.privateLock
        && current.blockedLock === last.blockedLock
        && Math.abs(current.start - last.end) < 0.0001;
      if (canMerge) {
        last.end = current.end;
      } else {
        merged.push(current);
      }
    }

    return merged;
  }

  function buildReservationPlacementsForDate(date, capacity) {
    const safeCapacity = Math.max(Number(capacity) || 1, 1);
    const columnEndByIndex = Array.from({ length: safeCapacity }, () => -1);
    const rows = getTimelineBookingsForDate(date);
    const placements = [];

    rows.forEach((row) => {
      const requiresAllColumns = row.is_private || row.is_blocked_slot;
      const slotsNeeded = requiresAllColumns
        ? safeCapacity
        : Math.max(1, Math.min(Number(row.people_count) || 1, safeCapacity));

      if (requiresAllColumns) {
        for (let index = 0; index < safeCapacity; index += 1) {
          columnEndByIndex[index] = Math.max(columnEndByIndex[index], row.end_minutes);
        }
        placements.push({
          bookingId: row.booking_id || null,
          startMinutes: row.start_minutes,
          endMinutes: row.end_minutes,
          columnStart: 1,
          columnSpan: safeCapacity,
          label: row.is_blocked_slot ? 'Bloqué' : 'Privé',
          kind: row.is_blocked_slot ? 'blocked' : 'private',
        });
        return;
      }

      const freeColumns = [];
      for (let index = 0; index < safeCapacity; index += 1) {
        if (columnEndByIndex[index] <= row.start_minutes) {
          freeColumns.push(index);
        }
      }

      if (freeColumns.length < slotsNeeded) {
        return;
      }

      const selectedColumns = freeColumns.slice(0, slotsNeeded).sort((a, b) => a - b);
      selectedColumns.forEach((columnIndex) => {
        columnEndByIndex[columnIndex] = row.end_minutes;
      });

      let runStart = selectedColumns[0];
      let previous = selectedColumns[0];

      for (let i = 1; i < selectedColumns.length; i += 1) {
        const current = selectedColumns[i];
        if (current === previous + 1) {
          previous = current;
          continue;
        }

        placements.push({
          bookingId: row.booking_id || null,
          startMinutes: row.start_minutes,
          endMinutes: row.end_minutes,
          columnStart: runStart + 1,
          columnSpan: (previous - runStart) + 1,
          label: `${Math.max(0, row.people_count)} place${row.people_count > 1 ? 's' : ''}`,
          kind: 'booking',
        });

        runStart = current;
        previous = current;
      }

      placements.push({
        bookingId: row.booking_id || null,
        startMinutes: row.start_minutes,
        endMinutes: row.end_minutes,
        columnStart: runStart + 1,
        columnSpan: (previous - runStart) + 1,
        label: `${Math.max(0, row.people_count)} place${row.people_count > 1 ? 's' : ''}`,
        kind: 'booking',
      });
    });

    return placements;
  }

  function getTimelineBookingsForDate(date) {
    const dateKey = toDateKey(date);
    const rows = [
      ...(configuredBookings[dateKey] || []),
      ...getBlockedBookingsForDate(date),
    ];

    return rows
      .map((row) => {
        const startMinutes = timeTextToMinutes(row.start);
        const endMinutes = timeTextToMinutes(row.end);
        if (startMinutes === null || endMinutes === null || endMinutes <= startMinutes) {
          return null;
        }

        return {
          booking_id: row.booking_id || null,
          start_minutes: startMinutes,
          end_minutes: endMinutes,
          people_count: Math.max(Number(row.people_count) || 1, 1),
          is_private: Boolean(row.is_private),
          is_blocked_slot: Boolean(row.is_blocked_slot),
        };
      })
      .filter(Boolean)
      .sort((a, b) => {
        if (a.start_minutes !== b.start_minutes) {
          return a.start_minutes - b.start_minutes;
        }
        if (a.end_minutes !== b.end_minutes) {
          return a.end_minutes - b.end_minutes;
        }
        return (b.people_count || 1) - (a.people_count || 1);
      });
  }

  function getWindowsForDay(date) {
    const dateKey = toDateKey(date);
    if (configuredReservationConfig.availability_mode === 'active_slots') {
      const windows = configuredActiveSlots
        .filter((item) => item.date === dateKey)
        .map((item) => ({
          start: timeTextToHour(item.start),
          end: timeTextToHour(item.end),
        }));
      return mergeTimeWindows(windows);
    }

    const specialDay = configuredSpecialDates.find((item) => item.date === dateKey);
    if (specialDay) {
      if (specialDay.closed) {
        return [];
      }

      return [
        {
          start: timeTextToHour(specialDay.start),
          end: timeTextToHour(specialDay.end),
        },
      ];
    }

    const weekday = String(date.getDay());
    const windows = configuredOpeningHours[weekday] || [];

    return windows.map((window) => ({
      start: timeTextToHour(window.start),
      end: timeTextToHour(window.end),
    }));
  }

  function mergeTimeWindows(windows) {
    if (!Array.isArray(windows) || windows.length === 0) {
      return [];
    }

    const sorted = windows
      .filter((window) => window && Number.isFinite(window.start) && Number.isFinite(window.end) && window.end > window.start)
      .map((window) => ({ start: window.start, end: window.end }))
      .sort((a, b) => (a.start - b.start) || (a.end - b.end));

    if (!sorted.length) {
      return [];
    }

    const merged = [sorted[0]];
    for (let i = 1; i < sorted.length; i += 1) {
      const current = sorted[i];
      const last = merged[merged.length - 1];
      if (current.start <= last.end) {
        last.end = Math.max(last.end, current.end);
        continue;
      }
      merged.push(current);
    }
    return merged;
  }

  function sanitizeSpecialDates(rawSpecialDates) {
    if (!Array.isArray(rawSpecialDates)) {
      return [];
    }

    const normalized = rawSpecialDates
      .filter((item) => item && typeof item === 'object')
      .map((item) => ({
        date: typeof item.date === 'string' ? item.date.trim() : '',
        closed: Boolean(item.closed),
        start: typeof item.start === 'string' ? item.start.trim() : '',
        end: typeof item.end === 'string' ? item.end.trim() : '',
        reason: typeof item.reason === 'string' ? item.reason.trim() : '',
      }))
      .filter((item) => /^\d{4}-\d{2}-\d{2}$/.test(item.date))
      .filter((item) => item.closed || (
        isValidTimeText(item.start)
        && isValidTimeText(item.end)
        && timeTextToMinutes(item.end) > timeTextToMinutes(item.start)
      ));

    const byDate = new Map();
    normalized.forEach((item) => {
      byDate.set(item.date, item);
    });

    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  }

  function sanitizeOpeningHours(rawHours) {
    const defaults = {
      '0': [],
      '1': [{ start: '09:00', end: '17:00' }],
      '2': [{ start: '08:00', end: '14:00' }],
      '3': [{ start: '10:00', end: '18:00' }],
      '4': [{ start: '09:00', end: '15:00' }],
      '5': [{ start: '09:00', end: '16:00' }],
      '6': [{ start: '10:00', end: '13:00' }],
    };

    const safe = { ...defaults };

    Object.keys(defaults).forEach((dayKey) => {
      const dayWindows = Array.isArray(rawHours[dayKey]) ? rawHours[dayKey] : defaults[dayKey];
      const normalized = dayWindows
        .filter((window) => isValidTimeText(window.start) && isValidTimeText(window.end))
        .map((window) => ({ start: window.start, end: window.end }))
        .filter((window) => timeTextToMinutes(window.end) > timeTextToMinutes(window.start));

      safe[dayKey] = normalized;
    });

    return safe;
  }

  function sanitizeActiveSlots(rawSlots) {
    if (!Array.isArray(rawSlots)) {
      return [];
    }

    return rawSlots
      .filter((item) => item && typeof item === 'object')
      .map((item) => ({
        id: Number(item.id) || 0,
        date: typeof item.date === 'string' ? item.date.trim() : '',
        start: typeof item.start_time === 'string'
          ? item.start_time.trim()
          : (typeof item.start === 'string' ? item.start.trim() : ''),
        end: typeof item.end_time === 'string'
          ? item.end_time.trim()
          : (typeof item.end === 'string' ? item.end.trim() : ''),
        title: typeof item.title === 'string' ? item.title.trim() : '',
      }))
      .filter((item) => /^\d{4}-\d{2}-\d{2}$/.test(item.date))
      .filter((item) => isValidTimeText(item.start) && isValidTimeText(item.end))
      .filter((item) => timeTextToMinutes(item.end) > timeTextToMinutes(item.start))
      .sort((a, b) => {
        if (a.date !== b.date) {
          return a.date.localeCompare(b.date);
        }
        const startDiff = timeTextToMinutes(a.start) - timeTextToMinutes(b.start);
        if (startDiff !== 0) {
          return startDiff;
        }
        return timeTextToMinutes(a.end) - timeTextToMinutes(b.end);
      });
  }

  function sanitizeReservationConfig(rawConfig) {
    const defaults = {
      availability_mode: 'opening_hours',
      sunnygym_display_mode: 'calendar',
      max_simultaneous_bookings: 3,
      min_duration_minutes: 30,
      max_duration_minutes: 120,
      latest_start_before_close_minutes: 30,
      slot_interval_enabled: true,
      slot_interval_minutes: 30,
      allow_back_to_back: true,
      fixed_time_only: true,
      fixed_time_interval_minutes: 15,
      allow_companion_booking: true,
      allow_private_room_choice: false,
      single_booking_per_day: false,
      frequency_limit_enabled: false,
      frequency_limit_metric: 'bookings',
      frequency_limit_value: 3,
      frequency_limit_period_value: 1,
      frequency_limit_period_unit: 'weeks',
    };

    if (!rawConfig || typeof rawConfig !== 'object') {
      return defaults;
    }

    const slotInterval = Number(rawConfig.slot_interval_minutes);
    const fixedInterval = Number(rawConfig.fixed_time_interval_minutes);
    const frequencyLimitValue = Number(rawConfig.frequency_limit_value);
    const frequencyLimitPeriodValue = Number(rawConfig.frequency_limit_period_value);
    const availabilityMode = String(rawConfig.availability_mode || rawConfig.booking_availability_mode || '').toLowerCase();
    const sunnygymDisplayMode = String(rawConfig.sunnygym_display_mode || '').toLowerCase();
    const boolOrDefault = (value, defaultValue) => {
      if (value === undefined || value === null) {
        return defaultValue;
      }
      return Boolean(value);
    };

    return {
      availability_mode: ['opening_hours', 'active_slots'].includes(availabilityMode)
        ? availabilityMode
        : defaults.availability_mode,
      sunnygym_display_mode: ['calendar', 'cards'].includes(sunnygymDisplayMode)
        ? sunnygymDisplayMode
        : defaults.sunnygym_display_mode,
      max_simultaneous_bookings: Number(rawConfig.max_simultaneous_bookings) || defaults.max_simultaneous_bookings,
      min_duration_minutes: Number(rawConfig.min_duration_minutes) || defaults.min_duration_minutes,
      max_duration_minutes: Number(rawConfig.max_duration_minutes) || defaults.max_duration_minutes,
      latest_start_before_close_minutes: Number(rawConfig.latest_start_before_close_minutes) || defaults.latest_start_before_close_minutes,
      slot_interval_enabled: boolOrDefault(rawConfig.slot_interval_enabled, defaults.slot_interval_enabled),
      slot_interval_minutes: [15, 30, 60].includes(slotInterval) ? slotInterval : defaults.slot_interval_minutes,
      allow_back_to_back: boolOrDefault(rawConfig.allow_back_to_back, defaults.allow_back_to_back),
      fixed_time_only: boolOrDefault(rawConfig.fixed_time_only, defaults.fixed_time_only),
      fixed_time_interval_minutes: [15, 30, 60].includes(fixedInterval) ? fixedInterval : defaults.fixed_time_interval_minutes,
      allow_companion_booking: boolOrDefault(
        rawConfig.allow_companion_booking,
        boolOrDefault(rawConfig.allow_companion, defaults.allow_companion_booking)
      ),
      allow_private_room_choice: boolOrDefault(
        rawConfig.allow_private_room_choice,
        boolOrDefault(rawConfig.allow_solo_booking, defaults.allow_private_room_choice)
      ),
      single_booking_per_day: boolOrDefault(rawConfig.single_booking_per_day, defaults.single_booking_per_day),
      frequency_limit_enabled: boolOrDefault(rawConfig.frequency_limit_enabled, defaults.frequency_limit_enabled),
      frequency_limit_metric: ['bookings', 'hours'].includes(String(rawConfig.frequency_limit_metric || '').toLowerCase())
        ? String(rawConfig.frequency_limit_metric).toLowerCase()
        : defaults.frequency_limit_metric,
      frequency_limit_value: Number.isFinite(frequencyLimitValue) && frequencyLimitValue > 0
        ? Math.floor(frequencyLimitValue)
        : defaults.frequency_limit_value,
      frequency_limit_period_value: Number.isFinite(frequencyLimitPeriodValue) && frequencyLimitPeriodValue > 0
        ? Math.floor(frequencyLimitPeriodValue)
        : defaults.frequency_limit_period_value,
      frequency_limit_period_unit: ['days', 'weeks', 'months'].includes(String(rawConfig.frequency_limit_period_unit || '').toLowerCase())
        ? String(rawConfig.frequency_limit_period_unit).toLowerCase()
        : defaults.frequency_limit_period_unit,
    };
  }

  function sanitizeHolidays(rawHolidays) {
    if (!Array.isArray(rawHolidays)) {
      return [];
    }

    return rawHolidays
      .filter((item) => item && typeof item === 'object')
      .map((item) => ({
        date: typeof item.date === 'string' ? item.date.trim() : '',
        month_day: typeof item.month_day === 'string' ? item.month_day.trim() : '',
        name: typeof item.name === 'string' ? item.name.trim() : '',
        alert: typeof item.alert === 'string' && item.alert.trim()
          ? item.alert.trim()
          : "L'horaire officiel est affiché ici. De légères différences peuvent survenir selon les options de configuration à venir.",
      }))
      .filter((item) => item.name && (/^\d{4}-\d{2}-\d{2}$/.test(item.date) || /^\d{2}-\d{2}$/.test(item.month_day)));
  }

  function getHolidayForDate(date) {
    const dateKey = toDateKey(date);
    const monthDay = dateKey.slice(5);
    return configuredHolidays.find((item) => item.date === dateKey || item.month_day === monthDay) || null;
  }

  function formatWindowsLabel(windows) {
    if (!windows || !windows.length) {
      return 'Fermé';
    }

    return windows.map((window) => `${hourToClockText(window.start)} - ${hourToClockText(window.end)}`).join(' | ');
  }

  function renderBookingRules() {
    if (!bookingRules) {
      return;
    }

    const lines = [
      `Minimum ${configuredReservationConfig.min_duration_minutes} minutes`,
      `Maximum ${configuredReservationConfig.max_duration_minutes} minutes`,
      `Capacité max: ${configuredReservationConfig.max_simultaneous_bookings} personne(s) en même temps`,
    ];

    if (configuredReservationConfig.latest_start_before_close_minutes > 0) {
      lines.push(`Début au plus tard ${configuredReservationConfig.latest_start_before_close_minutes} minutes avant la fermeture`);
    }
    if (configuredReservationConfig.availability_mode === 'active_slots') {
      lines.push('Disponibilités basées sur les plages activées par l’administrateur');
    } else {
      lines.push('Disponibilités basées sur les heures d’ouverture');
    }

    if (configuredReservationConfig.fixed_time_only) {
      lines.push(`Heures fixes par blocs de ${configuredReservationConfig.fixed_time_interval_minutes} minutes`);
    }

    if (configuredReservationConfig.single_booking_per_day) {
      lines.push('Maximum 1 réservation par jour');
    }

    if (configuredReservationConfig.frequency_limit_enabled) {
      const metricLabel = configuredReservationConfig.frequency_limit_metric === 'hours' ? 'heures' : 'réservations';
      const periodLabelMap = {
        days: 'jour(s)',
        weeks: 'semaine(s)',
        months: 'mois',
      };
      const periodLabel = periodLabelMap[configuredReservationConfig.frequency_limit_period_unit] || 'semaine(s)';
      lines.push(
        `Limite: ${configuredReservationConfig.frequency_limit_value} ${metricLabel} par ${configuredReservationConfig.frequency_limit_period_value} ${periodLabel}`
      );
    }

    if (configuredReservationConfig.allow_companion_booking) {
      lines.push('Accompagnateurs autorisés');
    }

    bookingRules.innerHTML = lines.map((line) => `<p>${line}</p>`).join('');

    if (bookingCompanionCountInput) {
      const maxCompanions = configuredReservationConfig.allow_companion_booking
        ? Math.max(configuredReservationConfig.max_simultaneous_bookings - 1, 0)
        : 0;
      bookingCompanionCountInput.max = String(maxCompanions);
      if (!configuredReservationConfig.allow_companion_booking) {
        bookingCompanionCountInput.value = '0';
        bookingCompanionCountInput.disabled = true;
      } else {
        bookingCompanionCountInput.disabled = false;
      }
    }

    if (bookingCompanionWrap) {
      bookingCompanionWrap.hidden = !configuredReservationConfig.allow_companion_booking;
    }

    if (bookingPrivateInput && bookingPrivateWrap) {
      if (configuredReservationConfig.allow_private_room_choice) {
        bookingPrivateWrap.hidden = false;
        bookingPrivateInput.disabled = false;
      } else {
        bookingPrivateInput.checked = false;
        bookingPrivateInput.disabled = true;
        bookingPrivateWrap.hidden = true;
      }
    }
  }

  function formatBookingsDashboardDateLabel(date) {
    if (!date) {
      return 'Choisissez une date';
    }

    return new Intl.DateTimeFormat('fr-CA', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }).format(date);
  }

  function syncBookingsDashboardVisibility() {
    if (!isBookingsDashboardPage) {
      return;
    }

    const managerVisible = bookingsDashboardMode === 'manager';
    document.body.classList.toggle('bookings-manager-open', managerVisible);
    if (adminCardTitleEl) {
      adminCardTitleEl.hidden = managerVisible;
    }
    if (bookingsDayPanelHeadEl) {
      bookingsDayPanelHeadEl.hidden = managerVisible;
    }
    if (adminBookingsDetailsDateLabelEl) {
      adminBookingsDetailsDateLabelEl.hidden = managerVisible;
    }
    if (bookingsOverviewPanelEl) {
      bookingsOverviewPanelEl.hidden = managerVisible;
    }
    if (bookingManagerPanelEl) {
      bookingManagerPanelEl.hidden = !managerVisible;
    }
    if (bookingManagerDateLabelEl) {
      bookingManagerDateLabelEl.textContent = state.selectedDate
        ? formatBookingsDashboardDateLabel(state.selectedDate)
        : 'Choisissez une date';
    }
    if (bookingManagerDateBtn) {
      bookingManagerDateBtn.classList.toggle('is-active', managerVisible);
    }

    if (managerVisible) {
      syncBookingsManagerViewportHeight();
      scheduleBookingsManagerRerender();
    } else if (bookingManagerGridEl) {
      bookingManagerGridEl.style.height = '';
      bookingManagerGridEl.style.minHeight = '';
      bookingManagerGridEl.style.maxHeight = '';
    }
  }

  function scheduleBookingsManagerRerender() {
    if (!isBookingsDashboardPage || bookingsDashboardMode !== 'manager' || !state.selectedDate) {
      return;
    }

    if (bookingsManagerRerenderFrame) {
      window.cancelAnimationFrame(bookingsManagerRerenderFrame);
    }

    bookingsManagerRerenderFrame = window.requestAnimationFrame(() => {
      bookingsManagerRerenderFrame = 0;
      if (isBookingsDashboardPage && bookingsDashboardMode === 'manager' && state.selectedDate) {
        syncBookingsManagerViewportHeight();
        renderSelectedDayPanel();
      }
    });
  }

  function syncBookingsManagerViewportHeight() {
    if (!isBookingsDashboardPage || bookingsDashboardMode !== 'manager' || !bookingManagerGridEl) {
      return;
    }
    bookingManagerGridEl.style.removeProperty('height');
    bookingManagerGridEl.style.removeProperty('min-height');
    bookingManagerGridEl.style.removeProperty('max-height');
  }

  function showBookingsManager(date = state.selectedDate || today) {
    if (!isBookingsDashboardPage) {
      return;
    }

    bookingsDashboardMode = 'manager';
    state.selectedDate = date ? startOfDay(date) : null;
    syncBookingsDashboardVisibility();
    scheduleBookingsManagerRerender();
  }

  function showBookingsOverview() {
    if (!isBookingsDashboardPage) {
      return;
    }

    bookingsDashboardMode = 'overview';
    state.selectedDate = null;
    syncBookingsDashboardVisibility();
    render();
  }

  function shiftBookingsSelectedDate(deltaDays) {
    if (!isBookingsDashboardPage) {
      return;
    }

    const entries = getBookingsOverviewEntries();
    if (!entries.length) {
      return;
    }

    const step = deltaDays >= 0 ? 1 : -1;
    const currentDate = state.selectedDate ? startOfDay(state.selectedDate) : null;
    const currentIndex = currentDate
      ? entries.findIndex((entry) => isSameDay(entry.date, currentDate))
      : -1;

    let nextIndex = -1;
    if (currentIndex >= 0) {
      nextIndex = currentIndex + step;
    } else if (step > 0) {
      nextIndex = entries.findIndex((entry) => entry.date >= today);
      if (nextIndex < 0) {
        nextIndex = 0;
      }
    } else {
      nextIndex = entries.length - 1;
    }

    if (nextIndex < 0 || nextIndex >= entries.length) {
      return;
    }

    selectDate(entries[nextIndex].date);
  }

  function getBookingsOverviewEntries() {
    const entries = [];
    const horizonDays = 90;

    for (let offset = 0; offset <= horizonDays; offset += 1) {
      const date = new Date(today);
      date.setDate(date.getDate() + offset);
      const dayData = getDayData(date);
      if (!dayData.hasAvailability || !dayData.availableIntervals.length) {
        continue;
      }

      const dateKey = toDateKey(date);
      const dateBookings = Array.isArray(configuredBookings[dateKey]) ? configuredBookings[dateKey] : [];
      const bookingCount = dateBookings.length;
      const participantCount = dateBookings.reduce((sum, booking) => {
        return sum + Math.max(Number(booking.people_count) || 1, 1);
      }, 0);

      entries.push({
        date,
        bookingCount,
        participantCount,
        availableIntervalsLabel: formatWindowsLabel(dayData.availableIntervals),
      });
    }

    return entries;
  }

  function renderBookingsOverviewList() {
    if (!calendarMobileListEl || !isBookingsDashboardPage) {
      return;
    }

    const entries = getBookingsOverviewEntries();

    calendarMobileListEl.innerHTML = '';
    calendarMobileListEl.classList.add('is-desktop-cards');

    if (!entries.length) {
      const emptyState = document.createElement('div');
      emptyState.className = 'calendar-mobile-empty-month';
      emptyState.textContent = 'Aucune plage disponible à venir.';
      calendarMobileListEl.appendChild(emptyState);
      return;
    }

    entries.forEach((entry) => {
      const dateObj = entry.date;
      const dateWeekday = new Intl.DateTimeFormat('fr-CA', { weekday: 'long' }).format(dateObj);
      const dateLong = new Intl.DateTimeFormat('fr-CA', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }).format(dateObj);

      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'calendar-mobile-day-card sunnygym-slot-card bookings-overview-card';
      card.classList.add('available');
      if (isSameDay(dateObj, today)) {
        card.classList.add('today');
      }
      if (state.selectedDate && isSameDay(dateObj, state.selectedDate)) {
        card.classList.add('selected');
      }

      card.innerHTML = `
        <div class="sunnygym-slot-card__head">
          <div>
            <p class="calendar-mobile-weekday">${escapeHtml(dateWeekday)}</p>
            <p class="calendar-mobile-date">${escapeHtml(dateLong)}</p>
          </div>
        </div>
        <div class="bookings-overview-card__schedule">
          <p class="sunnygym-slot-card__label">Plages disponibles</p>
          <p class="calendar-mobile-hours">${escapeHtml(entry.availableIntervalsLabel)}</p>
        </div>
        <div class="bookings-overview-card__meta">
          <div>
            <small>Réservations</small>
            <strong>${escapeHtml(entry.bookingCount)}</strong>
          </div>
          <div>
            <small>Participants</small>
            <strong>${escapeHtml(entry.participantCount)}</strong>
          </div>
        </div>
        <div class="sunnygym-slot-card__footer">
          <span class="sunnygym-slot-card__cta">Voir le détail</span>
        </div>
      `;
      card.addEventListener('click', () => {
        selectDate(dateObj);
      });

      calendarMobileListEl.appendChild(card);
    });
  }

  function sanitizeBookings(rawBookings) {
    const safe = {};

    if (!rawBookings || typeof rawBookings !== 'object') {
      return safe;
    }

    Object.keys(rawBookings).forEach((dateKey) => {
      const rows = Array.isArray(rawBookings[dateKey]) ? rawBookings[dateKey] : [];
      const normalized = rows
        .filter((row) => isValidTimeText(row.start) && isValidTimeText(row.end))
        .map((row) => ({
          booking_id: Number(row.booking_id) > 0 ? Number(row.booking_id) : null,
          start: row.start,
          end: row.end,
          people_count: Math.max(Number(row.people_count) || 1, 1),
          is_private: Boolean(row.is_private),
          is_blocked_slot: Boolean(row.is_blocked_slot),
        }))
        .filter((row) => timeTextToMinutes(row.end) > timeTextToMinutes(row.start));

      if (normalized.length) {
        safe[dateKey] = normalized;
      }
    });

    return safe;
  }

  function sanitizeBlockedRules(rawRules) {
    if (!Array.isArray(rawRules)) {
      return [];
    }

    return rawRules
      .filter((row) => row && typeof row === 'object')
      .map((row) => ({
        repeat_type: typeof row.repeat_type === 'string' ? row.repeat_type : 'once',
        date_value: typeof row.date_value === 'string' ? row.date_value : '',
        weekday: /^-?\d+$/.test(String(row.weekday)) ? Number(row.weekday) : null,
        month_day: typeof row.month_day === 'string' ? row.month_day : '',
        start_time: typeof row.start_time === 'string' ? row.start_time : '',
        end_time: typeof row.end_time === 'string' ? row.end_time : '',
        range_start: typeof row.range_start === 'string' ? row.range_start : '',
        range_end: typeof row.range_end === 'string' ? row.range_end : '',
        title: typeof row.title === 'string' ? row.title : 'Blocage administrateur',
      }))
      .filter((row) => isValidTimeText(row.start_time) && isValidTimeText(row.end_time))
      .filter((row) => timeTextToMinutes(row.end_time) > timeTextToMinutes(row.start_time));
  }

  function getBlockedBookingsForDate(date) {
    const dateKey = toDateKey(date);
    const monthDay = dateKey.slice(5);
    const weekday = date.getDay() === 0 ? 6 : date.getDay() - 1;
    const isHoliday = Boolean(getHolidayForDate(date));
    const capacity = configuredReservationConfig.max_simultaneous_bookings;

    const safeDateInRange = (rule) => {
      if (rule.range_start && dateKey < rule.range_start) {
        return false;
      }
      if (rule.range_end && dateKey > rule.range_end) {
        return false;
      }
      return true;
    };

    return configuredBlockedRules
      .filter((rule) => safeDateInRange(rule))
      .filter((rule) => {
        if (rule.repeat_type === 'once') {
          return rule.date_value === dateKey;
        }
        if (rule.repeat_type === 'weekly') {
          return Number(rule.weekday) === weekday;
        }
        if (rule.repeat_type === 'yearly') {
          return rule.month_day === monthDay;
        }
        if (rule.repeat_type === 'holiday') {
          return isHoliday;
        }
        return false;
      })
      .map((rule) => ({
        start: rule.start_time,
        end: rule.end_time,
        people_count: capacity,
        is_private: true,
        is_blocked_slot: true,
      }));
  }

  function setBookingFormMessage(text, type) {
    if (!bookingFormMessage) {
      return;
    }

    if (!text) {
      bookingFormMessage.className = '';
      bookingFormMessage.textContent = '';
      return;
    }

    bookingFormMessage.className = type === 'error' ? 'alert error' : 'alert success';
    bookingFormMessage.textContent = text;
  }

  function parseDateKey(value) {
    const match = /^\d{4}-\d{2}-\d{2}$/.exec(value);
    if (!match) {
      return null;
    }

    const [year, month, day] = value.split('-').map((item) => Number(item));
    return new Date(year, month - 1, day);
  }

  function isValidTimeText(value) {
    return /^\d{2}:\d{2}$/.test(value) && timeTextToMinutes(value) !== null;
  }

  function timeTextToMinutes(value) {
    if (!/^\d{2}:\d{2}$/.test(value)) {
      return null;
    }

    const [hourText, minuteText] = value.split(':');
    const hour = Number(hourText);
    const minute = Number(minuteText);

    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
      return null;
    }

    return (hour * 60) + minute;
  }

  function timeTextToHour(value) {
    const minutes = timeTextToMinutes(value);
    if (minutes === null) {
      return 0;
    }

    return minutes / 60;
  }

  function hourToTimeText(value) {
    const hour = Math.floor(value);
    const minutes = Math.round((value - hour) * 60);
    return `${String(hour).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
  }

  function minutesToTimeText(value) {
    const hour = Math.floor(value / 60);
    const minutes = value % 60;
    return `${String(hour).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
  }

  function formatHour(value) {
    const hour = Math.floor(value);
    const minutes = Math.round((value - hour) * 60);
    const hourText = String(hour).padStart(2, '0');
    const minutesText = String(minutes).padStart(2, '0');
    return `${hourText}h${minutesText}`;
  }

  function hourToClockText(value) {
    const hour = Math.floor(value);
    const minutes = Math.round((value - hour) * 60);
    return `${String(hour).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
  }

  function minutesToHours(value) {
    return value / 60;
  }

  function toDateKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function startOfDay(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
  }

  function isSameDay(a, b) {
    if (!a || !b) {
      return false;
    }
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  function isSameMonth(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
  }

  function isInMonth(date, monthDate) {
    if (!date || !monthDate) {
      return false;
    }
    return date.getFullYear() === monthDate.getFullYear() && date.getMonth() === monthDate.getMonth();
  }

  function mondayIndex(jsDay) {
    return (jsDay + 6) % 7;
  }

  function selectDate(date) {
    state.selectedDate = startOfDay(date);
    if (isBookingsDashboardPage) {
      showBookingsManager(state.selectedDate);
    }
    render();
    if (isBookingsDashboardPage) {
      syncBookingsDashboardVisibility();
      scheduleBookingsManagerRerender();
    }
    if (usesDayPanelModal) {
      openDayPanelModal();
    }
  }

  function openDayPanelModal() {
    if (!dayPanelModalEl || !dayPanelEl || !usesDayPanelModal) {
      return;
    }

    dayPanelEl.hidden = false;
    dayPanelEl.removeAttribute('hidden');

    if (typeof dayPanelModalEl.showModal === 'function') {
      if (!dayPanelModalEl.open) {
        dayPanelModalEl.showModal();
      }
    } else {
      dayPanelModalEl.setAttribute('open', 'open');
    }
    document.body.classList.add('calendar-day-modal-open');
  }

  function closeDayPanelModal() {
    if (!dayPanelModalEl || !usesDayPanelModal) {
      return;
    }

    if (typeof dayPanelModalEl.close === 'function') {
      if (dayPanelModalEl.open) {
        dayPanelModalEl.close();
      }
    } else {
      dayPanelModalEl.removeAttribute('open');
    }
    document.body.classList.remove('calendar-day-modal-open');
  }

  function getDefaultSelectionForMonth(monthDate, currentDate) {
    if (isSameMonth(monthDate, currentDate)) {
      return new Date(currentDate);
    }

    return new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
  }

  function resolveApiUrl(value) {
    const raw = String(value || '').trim();
    if (!raw) {
      return 'api/bookings';
    }

    try {
      return new URL(raw, window.location.href).toString();
    } catch (error) {
      return raw;
    }
  }

  render();
  renderBookingRules();
  if (bookingsManagerResizeObserver && bookingManagerGridEl) {
    bookingsManagerResizeObserver.observe(bookingManagerGridEl);
  }
  window.addEventListener('resize', () => {
    if (isBookingsDashboardPage && bookingsDashboardMode === 'manager') {
      syncBookingsManagerViewportHeight();
      scheduleBookingsManagerRerender();
    }
  });
})();
