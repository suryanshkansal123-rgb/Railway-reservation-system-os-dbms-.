
"use strict";

/*
 * RailEase - Railway Reservation System
 * Backend: Flask at http://127.0.0.1:5000
 * Frontend: http://127.0.0.1:5500
 */

const API_BASE = "http://127.0.0.1:5000/api";
const TOKEN_KEY = "railwayToken";

const state = {
  trains: [],
  selectedTrain: null,
  bookings: [],
  busy: false
};

const $ = (id) => document.getElementById(id);

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
    preferred_time: $("preferredTime")?.value || "08:00"
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
            <strong>${escapeHTML(train.departure_time || "—")}</strong>
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

function openBookingDialog(train) {
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
  renderPassengerFields();
  updateFamilyFare();

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

  updateFamilyFare();
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

  const journeyDate = train._journeyDate || $("journey-date")?.value;

  if (!journeyDate) {
    showToast("Please select a journey date.", "error");
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
        passengers
      })
    });

    closeBookingDialog();

    showToast(
      result.message ||
      `Booking confirmed! Total fare: ${formatCurrency(result.total_fare)}`
    );

    setMessage(
      "booking-message",
      "Booking completed. Refreshing your booking history..."
    );

    // Search again to display the updated seat count.
    await searchTrains();

    await loadBookings();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    state.busy = false;
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
        </div>

        <details class="passenger-list-details">
          <summary>View passenger details</summary>
          <ul class="booking-passenger-list">${passengerHTML}</ul>
        </details>
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
    const response = await fetch("http://127.0.0.1:5000/", {
      method: "GET"
    });

    if (!response.ok) throw new Error("Backend unavailable");

    label.textContent = "System online";
  } catch {
    label.textContent = "Backend offline";
  }
}

/* -------------------------------------------------------
   Initialize the page
------------------------------------------------------- */

function initializeRailEase() {
  $("search-form")?.addEventListener("submit", searchTrains);

  $("swap-stations")?.addEventListener("click", swapStations);

  $("passenger-count")?.addEventListener("change", renderPassengerFields);

  $("passenger-details-container")?.addEventListener("input", updateFamilyFare);

  $("passenger-form")?.addEventListener("submit", submitBooking);

  $("close-booking")?.addEventListener("click", closeBookingDialog);

  $("booking-dialog")?.addEventListener("click", (event) => {
    if (event.target === $("booking-dialog")) {
      closeBookingDialog();
    }
  });

  $("refresh-bookings")?.addEventListener("click", loadBookings);

  $("sync-run-btn")?.addEventListener("click", runConcurrencyDemo);

  checkBackend();

  if (getToken()) {
    loadBookings();
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
