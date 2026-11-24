
"use strict";

/*
 * RailEase - Railway Reservation System
 * Backend: Flask at http://127.0.0.1:5000
 * Frontend: http://127.0.0.1:5500
 */

const API_HOST = window.location.hostname || "127.0.0.1";
const API_ORIGIN = `http://${API_HOST}:5000`;
const API_BASE = `${API_ORIGIN}/api`;
const TOKEN_KEY = "railwayToken";
const BOOKING_WINDOW_MONTHS = 6;

const state = {
  trains: [],
  selectedTrain: null,
  bookings: [],
  pendingPaymentBookingId: null,
  paymentExpiresAt: null,
  paymentTimerInterval: null,
  paymentStatusInterval: null,
  busy: false,
  selectedSeatNumbers: [],
  walletBalance: 0
};

const $ = (id) => document.getElementById(id);

// Booking window is calculated from the user's local current date (not UTC).
function localDateISO(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function sixMonthsFromTodayISO() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const day = now.getDate();
  const targetFirst = new Date(year, month + BOOKING_WINDOW_MONTHS, 1);
  const lastDay = new Date(targetFirst.getFullYear(), targetFirst.getMonth() + 1, 0).getDate();
  return localDateISO(new Date(targetFirst.getFullYear(), targetFirst.getMonth(), Math.min(day, lastDay)));
}

function isJourneyDateWithinBookingWindow(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return false;
  const today = localDateISO(new Date());
  return value >= today && value <= sixMonthsFromTodayISO();
}

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) ||
    localStorage.getItem(TOKEN_KEY) ||
    "";
}

function setMessage(id, message, type = "") {
  const element = $(id);
  if (!element) return;

  element.textContent = message;
  element.classList.remove("success", "error", "warning");

  if (type) element.classList.add(type);
}

async function apiRequest(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  const token = getToken();

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers
    });
  } catch (error) {
    throw new Error(
      "Cannot connect to the backend. Make sure Flask is running on port 5000."
    );
  }

  let data = {};

  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    if (response.status === 401) {
      sessionStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TOKEN_KEY);
    }

    throw new Error(
      data.error || data.message || `Request failed (${response.status}).`
    );
  }

  return data;
}

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

function formatCurrency(value) {
  const amount = Number(value);

  if (!Number.isFinite(amount)) return "₹—";

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0
  }).format(amount);
}

function formatTrainTime(value) {
  if (!value) return "—";
  const match = String(value).trim().match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if (!match) return String(value);

  const hours = Number(match[1]);
  const minutes = match[2];
  if (hours < 0 || hours > 23) return String(value);

  const suffix = hours >= 12 ? "PM" : "AM";
  const displayHour = hours % 12 || 12;
  return `${displayHour}:${minutes} ${suffix}`;
}

function formatDuration(minutes) {
  const value = Number(minutes);

  if (!Number.isFinite(value) || value < 0) {
    return "Duration unavailable";
  }

  const hours = Math.floor(value / 60);
  const mins = value % 60;

  if (hours === 0) return `${mins} min`;
  if (mins === 0) return `${hours} hr`;

  return `${hours} hr ${mins} min`;
}

function formatDate(value) {
  if (!value) return "Date not specified";

  const parsed = new Date(`${value}T00:00:00`);

  if (Number.isNaN(parsed.getTime())) return value;

  return parsed.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric"
  });
}

function showToast(message, type = "success") {
  const container = $("toast-container");
  if (!container) {
    console.log(message);
    return;
  }

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  window.setTimeout(() => toast.remove(), 4500);
}

function setButtonBusy(button, busy, busyText = "Please wait...") {
  if (!button) return;

  if (busy) {
    button.dataset.originalText = button.textContent;
    button.disabled = true;
    button.textContent = busyText;
  } else {
    button.disabled = false;

    if (button.dataset.originalText) {
      button.textContent = button.dataset.originalText;
      delete button.dataset.originalText;
    }
  }
}

function ensureLoggedIn() {
  if (!getToken()) {
    showToast("Please log in before booking or viewing your bookings.", "error");
    return false;
  }

  return true;
}

/* -------------------------------------------------------
   Train search and recommendations
------------------------------------------------------- */

async function searchTrains(event) {
  if (event) event.preventDefault();

  const source = $("source")?.value || "";
  const destination = $("destination")?.value || "";
  const journeyDate = $("journey-date")?.value || "";
  const budget = $("budget")?.value?.trim() || "";

  if (!source || !destination) {
    setMessage("search-message", "Select both departure and destination cities.", "error");
    return;
  }

  if (source.toLowerCase() === destination.toLowerCase()) {
    setMessage("search-message", "Departure and destination must be different.", "error");
    return;
  }

  if (!journeyDate) {
    setMessage("search-message", "Please select your journey date.", "error");
    return;
  }

  if (!isJourneyDateWithinBookingWindow(journeyDate)) {
    setMessage("search-message", `Choose a journey date from today through ${sixMonthsFromTodayISO()}. Booking is limited to the next 6 months.`, "error");
    return;
  }

  if (budget && (!Number.isFinite(Number(budget)) || Number(budget) < 0)) {
    setMessage("search-message", "Enter a valid budget.", "error");
    return;
  }

  const params = new URLSearchParams({
    source,
    destination,
    price_weight: $("priceWeight")?.value || "5",
    duration_weight: $("durationWeight")?.value || "4",
    availability_weight: $("availabilityWeight")?.value || "3",
    timing_weight: $("timingWeight")?.value || "2",
    preferred_time: $("preferredTime")?.value || "08:00",
    journey_date: journeyDate
  });

  if (budget) params.set("budget", budget);

  const button = $("search-button");
  setButtonBusy(button, true, "Searching...");
  setMessage("search-message", "Searching for available trains...");
  $("result-count").textContent = "Searching...";

  try {
    const data = await apiRequest(`/trains?${params.toString()}`);

    state.trains = Array.isArray(data.trains) ? data.trains : [];

    // Keep the chosen date for booking even if the date is not a backend
    // train-search parameter.
    state.trains = state.trains.map((train) => ({
      ...train,
      _journeyDate: journeyDate
    }));

    renderTrains();

    setMessage(
      "search-message",
      state.trains.length
        ? `Found ${state.trains.length} train(s) for ${formatDate(journeyDate)}.`
        : "No trains match this route and budget. Try another route or budget.",
      state.trains.length ? "success" : ""
    );
  } catch (error) {
    state.trains = [];
    renderTrains();

    setMessage("search-message", error.message, "error");
    $("result-count").textContent = "Search failed";
  } finally {
    setButtonBusy(button, false);
  }
}

function renderTrains() {
  const container = $("train-list");
  if (!container) return;

  const count = state.trains.length;
  $("result-count").textContent = `${count} train${count === 1 ? "" : "s"} found`;

  if (!count) {
    container.innerHTML = `
      <div class="empty-state">
        <span class="empty-illustration" aria-hidden="true">🚉</span>
        <h3>No matching trains</h3>
        <p>Try another route or increase your maximum budget.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = state.trains.map((train, index) => {
    const id = Number(train.id);
    const fare = Number(train.fare);
    const seats = Number(train.seats);
    const duration = Number(train.duration_minutes);

    return `
      <article class="train-card">
        <div class="train-card-top">
          <span class="train-number">TRAIN ${escapeHTML(train.number || train.id)}</span>
          <span class="seat-badge ${seats > 0 ? "available" : "unavailable"}">
            ${seats > 0 ? `${seats} seats available` : "Sold out"}
          </span>
        </div>

        <h3>${escapeHTML(train.name || "Train")}</h3>

        <div class="train-route">
          <div>
            <span class="route-label">FROM</span>
            <strong>${escapeHTML(train.source)}</strong>
          </div>

          <div class="route-line" aria-hidden="true">→</div>

          <div>
            <span class="route-label">TO</span>
            <strong>${escapeHTML(train.destination)}</strong>
          </div>
        </div>

        <div class="train-details">
          <div>
            <span class="detail-label">Departure</span>
            <strong>${escapeHTML(formatTrainTime(train.departure_time))}</strong>
          </div>

          <div>
            <span class="detail-label">Duration</span>
            <strong>${escapeHTML(formatDuration(duration))}</strong>
          </div>

          <div>
            <span class="detail-label">Fare / person</span>
            <strong class="train-fare">${escapeHTML(formatCurrency(fare))}</strong>
          </div>
        </div>

        <button
          type="button"
          class="primary-button book-train-button"
          data-train-index="${index}"
          ${seats <= 0 ? "disabled" : ""}>
          ${seats > 0 ? "Book this train →" : "No seats available"}
        </button>
      </article>
    `;
  }).join("");

  container.querySelectorAll(".book-train-button").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.trainIndex);
      const train = state.trains[index];

      if (train) openBookingDialog(train);
    });
  });
}

/* -------------------------------------------------------
   Family booking dialog
------------------------------------------------------- */

async function refreshLiveSeatMap() {
  const train = state.selectedTrain;
  const map = $("live-seat-map");
  if (!train || !map) return;
  const journeyDate = train._journeyDate || new Date().toISOString().slice(0, 10);
  try {
    const result = await apiRequest(
      `/trains/${Number(train.id)}/seats?journey_date=${encodeURIComponent(journeyDate)}`
    );
    const counts = result.counts || {};
    $("seat-map-counts").textContent =
      `Available: ${counts.Available || 0} · Booked: ${counts.Booked || 0} · Temporarily locked: ${counts.Locked || 0}`;
    const seats = result.seats || [];
    // If another user has temporarily held a seat that this user had selected,
    // remove the stale selection and explain why it is no longer selectable.
    const newlyUnavailableSelections = state.selectedSeatNumbers.filter((number) => {
      const current = seats.find((item) => String(item.seat_number) === number);
      return current && String(current.status).toLowerCase() !== "available";
    });
    if (newlyUnavailableSelections.length) {
      state.selectedSeatNumbers = state.selectedSeatNumbers.filter((number) => !newlyUnavailableSelections.includes(number));
      showToast(`Seat ${newlyUnavailableSelections.join(", ")} is now being booked by another user. Please choose another available seat.`, "warning");
    }
    map.innerHTML = seats.map((seat) => {
      const number = String(seat.seat_number);
      const selected = state.selectedSeatNumbers.includes(number);
      const berth = Number(number.split("-").pop());
      const pos = ((berth - 1) % 4);
      const windowSeat = pos === 0 || pos === 3;
      const status = String(seat.status).toLowerCase();
      // Keep temporarily locked seats clickable so the user gets an explicit
      // explanation. Booked seats remain disabled.
      const disabled = status === "booked";
      const title = status === "locked"
        ? "Someone else is currently booking this seat"
        : status === "booked"
          ? "Already booked"
          : (windowSeat ? "Available · Window seat" : "Available · Aisle/Middle seat");
      const seatLabel = status === "locked" ? "HOLD" : (windowSeat ? "W" : (pos === 1 || pos === 2 ? "A/M" : ""));
      return `<button type="button" class="seat-chip ${status} ${selected ? "selected" : ""} ${windowSeat ? "window-seat" : ""}"
        data-seat-number="${escapeHTML(number)}" data-seat-status="${status}" ${disabled ? "disabled" : ""}
        aria-pressed="${selected}" title="${title}">
        <span>${escapeHTML(number)}</span><small>${seatLabel}</small></button>`;
    }).join("");
    $("selected-seat-summary").textContent = `Selected seats (${state.selectedSeatNumbers.length}/${Number($("passenger-count").value || 1)}): ${state.selectedSeatNumbers.join(", ") || "None"}`;
  } catch (error) {
    map.innerHTML = `<p class="form-note error">${escapeHTML(error.message)}</p>`;
  }
}

function toggleSeatSelection(seatNumber) {
  const maxSeats = Number($("passenger-count")?.value || 1);
  if (state.selectedSeatNumbers.includes(seatNumber)) {
    state.selectedSeatNumbers = state.selectedSeatNumbers.filter((item) => item !== seatNumber);
  } else {
    if (state.selectedSeatNumbers.length >= maxSeats) {
      showToast(`Select exactly ${maxSeats} seat(s) for your passengers.`, "warning");
      return;
    }
    state.selectedSeatNumbers.push(seatNumber);
  }
  refreshLiveSeatMap();
}

function openBookingDialog(train) {
  const chosenJourneyDate = train?._journeyDate || $("journey-date")?.value || "";
  if (!isJourneyDateWithinBookingWindow(chosenJourneyDate)) {
    showToast(`Choose a journey date between today and ${sixMonthsFromTodayISO()}. Dates beyond six months cannot be booked.`, "error");
    return;
  }
  if (!ensureLoggedIn()) return;

  state.selectedTrain = train;

  $("selected-train-name").textContent = train.name || "Selected train";
  $("selected-train-route").textContent =
    `${train.source} → ${train.destination} · ${formatDate(train._journeyDate)}`;

  $("selected-train-fare").textContent =
    `${formatCurrency(train.fare)} per passenger`;

  $("selected-train-summary").textContent =
    `Train ${train.number || train.id}. Enter the details for each passenger.`;

  $("passenger-count").value = "1";
  state.selectedSeatNumbers = [];
  renderPassengerFields();
  updateFamilyFare();
  refreshLiveSeatMap();
  if (state.seatMapTimer) clearInterval(state.seatMapTimer);
  state.seatMapTimer = setInterval(refreshLiveSeatMap, 3000);

  const dialog = $("booking-dialog");

  if (dialog && typeof dialog.showModal === "function") {
    dialog.showModal();
  } else if (dialog) {
    dialog.setAttribute("open", "");
  }
}

function closeBookingDialog() {
  const dialog = $("booking-dialog");
  if (!dialog) return;

  if (typeof dialog.close === "function" && dialog.open) {
    dialog.close();
  } else {
    dialog.removeAttribute("open");
  }

  state.selectedTrain = null;
  if (state.seatMapTimer) {
    clearInterval(state.seatMapTimer);
    state.seatMapTimer = null;
  }
}

function renderPassengerFields() {
  const container = $("passenger-details-container");
  const count = Number($("passenger-count")?.value || 1);

  if (!container) return;

  const previous = [];

  container.querySelectorAll(".passenger-card").forEach((card) => {
    previous.push({
      name: card.querySelector('[name="passenger-name"]')?.value || "",
      age: card.querySelector('[name="passenger-age"]')?.value || "",
      gender: card.querySelector('[name="passenger-gender"]')?.value || "Prefer not to say"
    });
  });

  container.innerHTML = Array.from({ length: count }, (_, index) => {
    const passenger = previous[index] || {};

    return `
      <fieldset class="passenger-card">
        <legend>Passenger ${index + 1}</legend>

        <div class="form-field">
          <label for="passenger-name-${index}">FULL NAME</label>
          <input
            id="passenger-name-${index}"
            name="passenger-name"
            type="text"
            minlength="2"
            maxlength="100"
            autocomplete="off"
            placeholder="Enter passenger name"
            value="${escapeHTML(passenger.name || "")}"
            required>
        </div>

        <div class="passenger-row">
          <div class="form-field">
            <label for="passenger-age-${index}">AGE</label>
            <input
              id="passenger-age-${index}"
              name="passenger-age"
              type="number"
              min="0"
              max="120"
              value="${escapeHTML(passenger.age ?? "")}"
              required>
          </div>

          <div class="form-field">
            <label for="passenger-gender-${index}">GENDER</label>
            <select
              id="passenger-gender-${index}"
              name="passenger-gender"
              required>
              <option value="Prefer not to say" ${passenger.gender === "Prefer not to say" || !passenger.gender ? "selected" : ""}>Prefer not to say</option>
              <option value="Male" ${passenger.gender === "Male" ? "selected" : ""}>Male</option>
              <option value="Female" ${passenger.gender === "Female" ? "selected" : ""}>Female</option>
              <option value="Other" ${passenger.gender === "Other" ? "selected" : ""}>Other</option>
            </select>
          </div>
        </div>
      </fieldset>
    `;
  }).join("");

  state.selectedSeatNumbers = [];
  updateFamilyFare();
  refreshLiveSeatMap();
}

function updateFamilyFare() {
  const train = state.selectedTrain;
  if (!train) return;

  const count = Number($("passenger-count")?.value || 1);
  const total = Number(train.fare) * count;

  $("family-fare-summary").textContent =
    `${count} passenger${count === 1 ? "" : "s"} × ${formatCurrency(train.fare)} = ${formatCurrency(total)} total`;
}

async function submitBooking(event) {
  event.preventDefault();

  if (state.busy) return;

  if (!ensureLoggedIn()) return;

  const train = state.selectedTrain;

  if (!train) {
    showToast("Please select a train first.", "error");
    return;
  }

  const form = $("passenger-form");

  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }

  const passengerCards = [
    ...$("passenger-details-container").querySelectorAll(".passenger-card")
  ];

  const passengers = passengerCards.map((card) => ({
    name: card.querySelector('[name="passenger-name"]').value.trim(),
    age: Number(card.querySelector('[name="passenger-age"]').value),
    gender: card.querySelector('[name="passenger-gender"]').value
  }));

  const seen = new Set();

  for (const passenger of passengers) {
    const key = `${passenger.name.toLocaleLowerCase().replace(/\s+/g, " ")}|${passenger.age}`;

    if (seen.has(key)) {
      showToast(
        `${passenger.name} (age ${passenger.age}) is entered more than once. Please check the passenger list.`,
        "error"
      );
      return;
    }

    seen.add(key);
  }

  if (state.selectedSeatNumbers.length !== passengers.length) {
    showToast(`Please select exactly ${passengers.length} seat(s) on the coach layout.`, "error");
    return;
  }

  const journeyDate = train._journeyDate || $("journey-date")?.value;

  if (!journeyDate) {
    showToast("Please select a journey date.", "error");
    return;
  }

  if (!isJourneyDateWithinBookingWindow(journeyDate)) {
    showToast(`Bookings are available only from today through ${sixMonthsFromTodayISO()}. Please choose another date.`, "error");
    return;
  }

  const button = $("confirm-booking");
  state.busy = true;
  setButtonBusy(button, true, "Confirming booking...");

  try {
    const result = await apiRequest("/bookings", {
      method: "POST",
      body: JSON.stringify({
        train_id: Number(train.id),
        journey_date: journeyDate,
        passengers,
        selected_seats: state.selectedSeatNumbers,
        use_wallet: Boolean($("use-wallet")?.checked)
      })
    });

    state.pendingPaymentBookingId = result.booking_id;
    state.paymentExpiresAt = new Date(result.hold_expires_at).getTime();
    closeBookingDialog();

    $("payment-summary").textContent =
      `Booking #${result.booking_id} · Seats ${(result.seat_numbers || []).join(", ")} · Fare ${formatCurrency(result.total_fare)} · Wallet used ${formatCurrency(result.wallet_used || 0)} · Remaining QR payment ${formatCurrency(result.amount_due || 0)}.`;

    if (Number(result.amount_due || 0) <= 0) {
      await apiRequest("/bookings/confirm-payment", { method: "POST", body: JSON.stringify({ booking_id: result.booking_id, payment_method: "WALLET", outcome: "success" }) });
      state.pendingPaymentBookingId = null;
      state.paymentExpiresAt = null;
      showToast(`Booking #${result.booking_id} confirmed using your wallet!`, "success");
      await Promise.all([searchTrains(), loadBookings(), loadWallet()]);
    } else {
      $("payment-dialog").showModal();
      startPaymentCountdown();
      await createDemoPaymentQR();
      startPhonePaymentPolling();
    }
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    state.busy = false;
    setButtonBusy(button, false);
  }
}

/* -------------------------------------------------------
   Simulated payment
------------------------------------------------------- */

function stopPaymentCountdown() {
  if (state.paymentTimerInterval) {
    clearInterval(state.paymentTimerInterval);
    state.paymentTimerInterval = null;
  }
}

function startPaymentCountdown() {
  stopPaymentCountdown();
  const countdown = $("payment-countdown");
  const update = () => {
    const remaining = Math.max(0, Math.ceil((state.paymentExpiresAt - Date.now()) / 1000));
    const minutes = String(Math.floor(remaining / 60)).padStart(2, "0");
    const seconds = String(remaining % 60).padStart(2, "0");
    if (countdown) countdown.textContent = `Time remaining: ${minutes}:${seconds}`;
    if (remaining <= 0) {
      stopPaymentCountdown();
      stopPhonePaymentPolling();
      if ($("payment-dialog")?.open) $("payment-dialog").close();
      state.pendingPaymentBookingId = null;
      state.paymentExpiresAt = null;
      showToast("Payment time expired. Your temporary seat lock has been released.", "warning");
      searchTrains();
      loadBookings();
    }
  };
  update();
  state.paymentTimerInterval = setInterval(update, 1000);
}

async function createDemoPaymentQR() {
  const holder = $("demo-qr-code"); const link = $("demo-qr-link");
  if (!holder || !state.pendingPaymentBookingId) return;
  holder.innerHTML = "<p>Generating demo QR...</p>";
  try {
    const data = await apiRequest(`/bookings/${state.pendingPaymentBookingId}/demo-qr`);
    holder.innerHTML = "";
    if (typeof QRCode === "undefined") throw new Error("QR generator did not load. Check internet and refresh.");
    new QRCode(holder, { text: data.phone_url, width: 220, height: 220, correctLevel: QRCode.CorrectLevel.M });
    if (link) link.textContent = `Phone link: ${data.phone_url}`;
  } catch (error) { holder.textContent = error.message; }
}

function stopPhonePaymentPolling() {
  if (state.paymentStatusInterval) clearInterval(state.paymentStatusInterval);
  state.paymentStatusInterval = null;
}

function startPhonePaymentPolling() {
  stopPhonePaymentPolling();
  state.paymentStatusInterval = setInterval(async () => {
    if (!state.pendingPaymentBookingId) return;
    try {
      const result = await apiRequest(`/bookings/${state.pendingPaymentBookingId}/payment-status`);
      if (result.payment_status === "Successful") {
        const id = state.pendingPaymentBookingId; stopPhonePaymentPolling(); stopPaymentCountdown();
        if ($("payment-dialog")?.open) $("payment-dialog").close();
        state.pendingPaymentBookingId = null; state.paymentExpiresAt = null;
        showToast(`Phone demo payment received. Booking #${id} confirmed!`, "success");
        await searchTrains(); await loadBookings();
      } else if (["Expired", "Failed"].includes(result.payment_status)) {
        stopPhonePaymentPolling(); stopPaymentCountdown();
        if ($("payment-dialog")?.open) $("payment-dialog").close();
        state.pendingPaymentBookingId = null; state.paymentExpiresAt = null;
        showToast("Payment was not completed; seat hold ended.", "warning");
        await searchTrains(); await loadBookings();
      }
    } catch (_) {}
  }, 2000);
}

async function cancelPendingPayment() {
  const bookingId = state.pendingPaymentBookingId;
  if (!bookingId) return;
  const confirmed = window.confirm(`Cancel booking #${bookingId}?\n\nYour temporary seat reservation will be released. Any wallet amount used for this pending booking will be returned to your RailEase wallet.`);
  if (!confirmed) return;
  const button = $("cancel-pending-payment");
  if (button) setButtonBusy(button, true, "Cancelling...");
  try {
    const result = await apiRequest(`/bookings/${bookingId}/cancel-pending`, {
      method: "POST",
      body: JSON.stringify({})
    });
    stopPaymentCountdown();
    stopPhonePaymentPolling();
    if ($("payment-dialog")?.open) $("payment-dialog").close();
    state.pendingPaymentBookingId = null;
    state.paymentExpiresAt = null;
    showToast(result.message || "Pending booking cancelled and seats released.", "success");
    await Promise.all([searchTrains(), loadBookings(), loadWallet()]);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    if (button) setButtonBusy(button, false);
  }
}

async function submitDemoPayment(event) { event.preventDefault(); await createDemoPaymentQR(); }

/* -------------------------------------------------------
   Priority scheduling demonstration
------------------------------------------------------- */

function renderPriorityInputs() {
  const count = Number($("priority-count")?.value || 5);
  const container = $("priority-request-inputs");
  if (!container) return;

  container.innerHTML = Array.from({length: count}, (_, index) => `
    <div class="form-field">
      <label for="priority-request-${index}">Request ${index + 1} priority</label>
      <select id="priority-request-${index}" class="priority-choice">
        <option value="High" ${index === 0 ? "selected" : ""}>High</option>
        <option value="Medium" ${index === 0 ? "" : "selected"}>Medium</option>
        <option value="Low">Low</option>
      </select>
      <label for="priority-passengers-${index}">Passengers</label>
      <input id="priority-passengers-${index}" class="priority-passengers" type="number" min="1" max="10" value="1">
    </div>
  `).join("");
}

async function runPriorityDemo() {
  const seats = Number($("priority-seats").value);
  const priorities = [...document.querySelectorAll(".priority-choice")];
  const counts = [...document.querySelectorAll(".priority-passengers")];

  const requests = priorities.map((select, index) => ({
    request_id: index + 1,
    priority: select.value,
    passengers: Number(counts[index].value)
  }));

  const button = $("priority-run-btn");
  setButtonBusy(button, true, "Simulating...");

  try {
    const data = await apiRequest("/demo/priority-allocation", {
      method: "POST",
      body: JSON.stringify({seats, requests})
    });

    $("priority-message").textContent =
      `${data.successful_requests} requests accepted; ${data.rejected_requests} rejected. ${data.processing_rule}.`;

    $("priority-results").innerHTML = data.results.map(item => `
      <div class="sync-result-row ${item.result === "SUCCESS" ? "success" : "rejected"}">
        <span>Request ${escapeHTML(item.request_id)}</span>
        <strong>${escapeHTML(item.priority)} — ${escapeHTML(item.result)}</strong>
        <span>${escapeHTML(item.passengers)} passenger(s); ${escapeHTML(item.remaining_seats)} seats left</span>
      </div>
    `).join("");
  } catch (error) {
    $("priority-message").textContent = error.message;
  } finally {
    setButtonBusy(button, false);
  }
}

/* -------------------------------------------------------
   Booking history
------------------------------------------------------- */

async function loadBookings() {
  if (!ensureLoggedIn()) {
    setMessage(
      "booking-message",
      "Please log in to view your booking history.",
      "warning"
    );

    $("booking-list").innerHTML = `
      <div class="empty-state compact">
        <p>Log in to see your reservations.</p>
      </div>
    `;
    return;
  }

  const refreshButton = $("refresh-bookings");
  setButtonBusy(refreshButton, true, "Refreshing...");

  setMessage("booking-message", "Loading your booking history...");

  try {
    const data = await apiRequest("/bookings");

    state.bookings = Array.isArray(data.bookings) ? data.bookings : [];

    renderBookings();

    setMessage(
      "booking-message",
      state.bookings.length
        ? `${state.bookings.length} booking record(s) found.`
        : "You have no bookings yet."
    );
  } catch (error) {
    setMessage("booking-message", error.message, "error");
  } finally {
    setButtonBusy(refreshButton, false);
  }
}

async function loadWallet() {
  if (!getToken()) return;
  try {
    const data = await apiRequest("/wallet");
    state.walletBalance = Number(data.balance || 0);
    const hint = $("wallet-use-hint");
    if (hint) hint.textContent = `Available wallet balance: ${formatCurrency(state.walletBalance)}. It will be applied first; only the remaining amount needs QR payment.`;
    const balance = $("wallet-balance");
    if (balance) balance.textContent = formatCurrency(data.balance || 0);
    setMessage("wallet-message", "Wallet balance updated.", "success");
  } catch (error) {
    setMessage("wallet-message", error.message, "error");
  }
}

async function cancelBooking(bookingId) {
  const booking = state.bookings.find((item) => Number(item.booking_id) === Number(bookingId));
  if (!booking) return;
  const refund = Number(booking.total_fare || 0) * 0.60;
  const confirmed = window.confirm(`Cancel booking #${bookingId}?\n\n60% refund: ${formatCurrency(refund)} will be credited to your RailEase wallet. The remaining 40% is non-refundable. The selected seats will be released.`);
  if (!confirmed) return;
  try {
    const result = await apiRequest(`/bookings/${bookingId}/cancel`, { method: "POST", body: JSON.stringify({}) });
    setMessage("booking-message", `${result.message} Wallet credited: ${formatCurrency(result.wallet_credit)}.`, "success");
    await Promise.all([loadBookings(), loadWallet()]);
  } catch (error) {
    setMessage("booking-message", error.message, "error");
  }
}

function renderBookings() {
  const container = $("booking-list");
  if (!container) return;

  if (!state.bookings.length) {
    container.innerHTML = `
      <div class="empty-state compact">
        <span aria-hidden="true">🎟️</span>
        <p>No reservations yet. Search for a train to get started.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = state.bookings.map((booking) => {
    const passengers = Array.isArray(booking.passengers)
      ? booking.passengers
      : [];

    const passengerHTML = passengers.length
      ? passengers.map((person) => `
          <li>
            ${escapeHTML(person.name)}
            <span>Age ${escapeHTML(person.age)} · ${escapeHTML(person.gender)}</span>
          </li>
        `).join("")
      : `<li>${escapeHTML(booking.passenger_name || "Passenger details unavailable")}</li>`;

    return `
      <article class="booking-card">
        <div class="booking-card-header">
          <span class="booking-reference">BOOKING #${escapeHTML(booking.booking_id)}</span>
          <span class="booking-status">${escapeHTML(booking.status || "Confirmed")}</span>
        </div>

        <h3>${escapeHTML(booking.train_name || "Train reservation")}</h3>

        <p class="booking-route">
          ${escapeHTML(booking.source || "")}
          <span aria-hidden="true">→</span>
          ${escapeHTML(booking.destination || "")}
        </p>

        <div class="booking-details">
          <span>Journey date</span>
          <strong>${escapeHTML(formatDate(booking.journey_date))}</strong>

          <span>Passengers</span>
          <strong>${escapeHTML(booking.passenger_count ?? passengers.length)}</strong>

          <span>Total fare</span>
          <strong>${escapeHTML(formatCurrency(booking.total_fare))}</strong>

          <span>Priority</span>
          <strong>${escapeHTML(booking.priority_level || "Medium")}</strong>

          <span>Payment</span>
          <strong>${escapeHTML(booking.payment_status || "Paid")}</strong>
          ${Number(booking.refund_amount || 0) > 0 ? `<span>Wallet refund</span><strong>${escapeHTML(formatCurrency(booking.refund_amount))}</strong>` : ""}
        </div>

        <details class="passenger-list-details">
          <summary>View passenger details</summary>
          <ul class="booking-passenger-list">${passengerHTML}</ul>
        </details>
        ${booking.status === "Confirmed" && ["Successful", "Paid"].includes(booking.payment_status || "Paid") ? `<button type="button" class="secondary-button cancel-booking-btn" data-booking-id="${escapeHTML(booking.booking_id)}">Cancel booking · 60% wallet refund</button>` : ""}
      </article>
    `;
  }).join("");
}

/* -------------------------------------------------------
   OS synchronization demonstration
------------------------------------------------------- */

async function runConcurrencyDemo() {
  const attempts = Number($("sync-attempts")?.value || 10);
  const seats = Number($("sync-seats")?.value || 5);

  if (!Number.isInteger(attempts) || attempts < 1 || attempts > 50) {
    setMessage("sync-message", "Requests must be between 1 and 50.", "error");
    return;
  }

  if (!Number.isInteger(seats) || seats < 0 || seats > 50) {
    setMessage("sync-message", "Seats must be between 0 and 50.", "error");
    return;
  }

  const button = $("sync-run-btn");
  setButtonBusy(button, true, "Simulating...");

  setMessage("sync-message", "Simulating simultaneous booking requests...");

  try {
    const params = new URLSearchParams({
      attempts: String(attempts),
      seats: String(seats)
    });

    const data = await apiRequest(`/demo/concurrency?${params.toString()}`);

    $("sync-total").textContent = data.total_requests ?? "—";
    $("sync-success").textContent = data.successful_bookings ?? "—";
    $("sync-rejected").textContent = data.rejected_requests ?? "—";
    $("sync-remaining").textContent = data.remaining_seats ?? "—";

    const resultsContainer = $("sync-request-results");
    const results = Array.isArray(data.results) ? data.results : [];

    resultsContainer.innerHTML = `
      <div class="sync-result-list">
        ${results.map((result) => `
          <div class="sync-result-row ${result.result === "SUCCESS" ? "success" : "rejected"}">
            <span>Request ${escapeHTML(result.request)}</span>
            <strong>${escapeHTML(result.result)}</strong>
            <span>Seats left: ${escapeHTML(result.remaining_seats)}</span>
          </div>
        `).join("")}
      </div>
    `;

    setMessage(
      "sync-message",
      `Simulation complete: ${data.successful_bookings} successful, ${data.rejected_requests} rejected. The real database was not changed.`,
      "success"
    );
  } catch (error) {
    setMessage("sync-message", error.message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

/* -------------------------------------------------------
   Station swapping and backend status
------------------------------------------------------- */

function swapStations() {
  const source = $("source");
  const destination = $("destination");

  if (!source || !destination) return;

  const previousSource = source.value;
  source.value = destination.value;
  destination.value = previousSource;
}

async function checkBackend() {
  const label = $("connection-label");
  if (!label) return;

  try {
    const response = await fetch(`${API_ORIGIN}/`, {
      method: "GET"
    });

    if (!response.ok) throw new Error("Backend unavailable");

    label.textContent = "System online";
  } catch {
    label.textContent = "Backend offline";
  }
}

function renderSignedInUser() {
  const nameElement = $("signed-in-user-name");
  const avatarElement = $("signed-in-user-avatar");
  if (!nameElement || !avatarElement) return;

  let user = null;
  try {
    user = JSON.parse(sessionStorage.getItem("railwayUser") || localStorage.getItem("railwayUser") || "null");
  } catch (error) {
    console.warn("Could not read signed-in user details.", error);
  }

  const name = user?.name || user?.username || user?.email || "Guest";
  nameElement.textContent = name;
  avatarElement.textContent = String(name).trim().charAt(0).toUpperCase() || "G";
}

/* -------------------------------------------------------
   Initialize the page
------------------------------------------------------- */

function initializeRailEase() {
  renderSignedInUser();
  $("search-form")?.addEventListener("submit", searchTrains);

  $("swap-stations")?.addEventListener("click", swapStations);

  $("passenger-count")?.addEventListener("change", renderPassengerFields);

  $("passenger-details-container")?.addEventListener("input", updateFamilyFare);

  $("passenger-form")?.addEventListener("submit", submitBooking);
  $("payment-form")?.addEventListener("submit", submitDemoPayment);
  $("refresh-demo-qr")?.addEventListener("click", createDemoPaymentQR);
  $("cancel-pending-payment")?.addEventListener("click", cancelPendingPayment);
  $("payment-dialog")?.addEventListener("cancel", (event) => {
    if (state.pendingPaymentBookingId) event.preventDefault();
  });
  $("priority-count")?.addEventListener("change", renderPriorityInputs);
  $("priority-run-btn")?.addEventListener("click", runPriorityDemo);
  renderPriorityInputs();

  $("close-booking")?.addEventListener("click", closeBookingDialog);

  $("booking-dialog")?.addEventListener("click", (event) => {
    if (event.target === $("booking-dialog")) {
      closeBookingDialog();
    }
  });

  $("refresh-bookings")?.addEventListener("click", loadBookings);
  $("refresh-wallet")?.addEventListener("click", loadWallet);
  $("use-wallet")?.addEventListener("change", loadWallet);
  $("booking-list")?.addEventListener("click", (event) => {
    const button = event.target.closest(".cancel-booking-btn");
    if (button) cancelBooking(button.dataset.bookingId);
  });

  $("sync-run-btn")?.addEventListener("click", runConcurrencyDemo);

  checkBackend();

  if (getToken()) {
    loadBookings();
    loadWallet();
  } else {
    setMessage(
      "booking-message",
      "Please log in to view your booking history."
    );
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeRailEase);
} else {
  initializeRailEase();
}

$("refresh-seat-map")?.addEventListener("click", refreshLiveSeatMap);
$("live-seat-map")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-seat-number]");
  if (!button || button.disabled) return;
  const status = button.dataset.seatStatus;
  if (status === "locked") {
    showToast(`Seat ${button.dataset.seatNumber} is currently being booked by another user. Please select a different seat.`, "warning");
    return;
  }
  toggleSeatSelection(button.dataset.seatNumber);
});
