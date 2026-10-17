
"use strict";

// RailEase — Railway Reservation System
// Flask backend: http://127.0.0.1:5000

const API = "http://127.0.0.1:5000";
const REQUEST_TIMEOUT = 10000;

// ---------- HTML elements ----------

const searchForm = document.getElementById("search-form");
const sourceInput = document.getElementById("source");
const destinationInput = document.getElementById("destination");
const dateInput = document.getElementById("journey-date");
const budgetInput = document.getElementById("budget");
const swapButton = document.getElementById("swap-stations");
const searchButton = document.getElementById("search-button");

const trainList = document.getElementById("train-list");
const searchMessage = document.getElementById("search-message");
const resultCount = document.getElementById("result-count");

const bookingList = document.getElementById("booking-list");
const bookingMessage = document.getElementById("booking-message");
const refreshBookingsButton = document.getElementById("refresh-bookings");

const bookingDialog = document.getElementById("booking-dialog");
const passengerForm = document.getElementById("passenger-form");
const closeBookingButton = document.getElementById("close-booking");
const confirmBookingButton = document.getElementById("confirm-booking");

const passengerCountInput = document.getElementById("passenger-count");
const passengerDetailsContainer = document.getElementById(
    "passenger-details-container"
);
const familyFareSummary = document.getElementById("family-fare-summary");

const selectedTrainSummary = document.getElementById(
    "selected-train-summary"
);
const selectedTrainPreview = document.getElementById(
    "selected-train-preview"
);
const selectedTrainName = document.getElementById("selected-train-name");
const selectedTrainRoute = document.getElementById("selected-train-route");
const selectedTrainFare = document.getElementById("selected-train-fare");

const connectionLabel = document.getElementById("connection-label");
const toastContainer = document.getElementById("toast-container");

// Recommendation controls
const priceWeightInput = document.getElementById("priceWeight");
const durationWeightInput = document.getElementById("durationWeight");
const availabilityWeightInput = document.getElementById("availabilityWeight");
const timingWeightInput = document.getElementById("timingWeight");
const preferredTimeInput = document.getElementById("preferredTime");
const resetPreferencesButton = document.getElementById("reset-preferences");

// ---------- Application state ----------

let currentTrains = [];
let selectedTrain = null;
let searchNumber = 0;

// ---------- Helpers ----------

function makeElement(tag, className = "", text = "") {
    const element = document.createElement(tag);

    if (className) {
        element.className = className;
    }

    if (text !== undefined && text !== null) {
        element.textContent = String(text);
    }

    return element;
}

function formatMoney(amount) {
    const value = Number(amount);

    if (!Number.isFinite(value)) {
        return "Fare unavailable";
    }

    return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2
    }).format(value);
}

function showToast(message, type = "info") {
    if (!toastContainer) {
        console.log(message);
        return;
    }

    const toast = makeElement("div", `toast toast-${type}`, message);
    toast.setAttribute("role", "status");
    toastContainer.appendChild(toast);

    window.setTimeout(() => toast.remove(), 4000);
}

function setConnectionStatus(connected, message) {
    if (!connectionLabel) return;

    connectionLabel.textContent = message;

    const container = connectionLabel.closest(".system-status");

    if (container) {
        container.classList.toggle("is-connected", connected);
        container.classList.toggle("is-disconnected", !connected);
    }
}

function setSearchLoading(isLoading) {
    if (!searchButton) return;

    searchButton.disabled = isLoading;

    const buttonText = searchButton.querySelector("[data-button-text]");

    if (buttonText) {
        buttonText.textContent = isLoading ? "Searching..." : "Search trains";
    } else {
        searchButton.textContent = isLoading ? "Searching..." : "Search trains →";
    }
}

function setBookingLoading(isLoading) {
    if (!confirmBookingButton) return;

    confirmBookingButton.disabled = isLoading;
    confirmBookingButton.textContent = isLoading
        ? "Booking..."
        : "Confirm booking →";
}

// ---------- API requests ----------

async function apiRequest(path, options = {}) {
    const controller = new AbortController();

    const timeoutId = window.setTimeout(
        () => controller.abort(),
        REQUEST_TIMEOUT
    );

    try {
        const response = await fetch(`${API}${path}`, {
            ...options,
            signal: controller.signal,
            headers: {
                Accept: "application/json",
                ...(options.body ? { "Content-Type": "application/json" } : {}),
                ...(options.headers || {})
            }
        });

        const responseText = await response.text();
        let data = {};

        if (responseText) {
            try {
                data = JSON.parse(responseText);
            } catch {
                throw new Error(
                    "The server returned an invalid response. Check Flask."
                );
            }
        }

        if (!response.ok) {
            throw new Error(
                data.error || data.message || `Server error (${response.status})`
            );
        }

        return data;
    } catch (error) {
        if (error.name === "AbortError") {
            throw new Error("Request timed out. Check whether Flask is running.");
        }

        if (error instanceof TypeError) {
            throw new Error(
                "Cannot connect to Flask. Check the backend server and API address."
            );
        }

        throw error;
    } finally {
        window.clearTimeout(timeoutId);
    }
}

// ---------- Recommendation preferences ----------

function getWeight(input, defaultValue) {
    if (!input) return defaultValue;

    const value = Number(input.value);

    if (!Number.isInteger(value) || value < 1 || value > 5) {
        return defaultValue;
    }

    return value;
}

function updateWeightOutput(inputId, outputId) {
    const input = document.getElementById(inputId);
    const output = document.getElementById(outputId);

    if (!input || !output) return;

    const update = () => {
        output.textContent = `${input.value} / 5`;
    };

    input.addEventListener("input", update);
    update();
}

function getRecommendationPreferences() {
    return {
        price_weight: getWeight(priceWeightInput, 5),
        duration_weight: getWeight(durationWeightInput, 4),
        availability_weight: getWeight(availabilityWeightInput, 3),
        timing_weight: getWeight(timingWeightInput, 2),
        preferred_time: preferredTimeInput?.value || ""
    };
}

function resetPreferences() {
    const defaults = [
        [priceWeightInput, 5],
        [durationWeightInput, 4],
        [availabilityWeightInput, 3],
        [timingWeightInput, 2]
    ];

    defaults.forEach(([input, value]) => {
        if (input) {
            input.value = value;
            input.dispatchEvent(new Event("input"));
        }
    });

    if (preferredTimeInput) {
        preferredTimeInput.value = "08:00";
    }

    showToast("Recommendation preferences reset.", "info");
}

updateWeightOutput("priceWeight", "priceValue");
updateWeightOutput("durationWeight", "durationValue");
updateWeightOutput("availabilityWeight", "availabilityValue");
updateWeightOutput("timingWeight", "timingValue");

resetPreferencesButton?.addEventListener("click", resetPreferences);

// ---------- Train search ----------

function clearTrainResults(message = "") {
    trainList.replaceChildren();

    if (resultCount) {
        resultCount.textContent = "0 trains";
    }

    if (message && searchMessage) {
        searchMessage.textContent = message;
    }
}

function createScoreBreakdown(train) {
    const scores = train.component_scores;

    if (!scores || typeof scores !== "object") {
        return null;
    }

    const wrapper = makeElement("div", "score-breakdown");
    wrapper.appendChild(makeElement("strong", "", "Score breakdown"));

    const labels = {
        price: "Price",
        duration: "Duration",
        availability: "Seat availability",
        timing: "Departure timing"
    };

    Object.entries(labels).forEach(([key, label]) => {
        const value = Number(scores[key]);

        if (!Number.isFinite(value)) return;

        const item = makeElement("div", "score-item");
        const heading = makeElement("div", "score-item-heading");

        heading.appendChild(makeElement("span", "", label));
        heading.appendChild(
            makeElement("span", "", `${value.toFixed(1)} / 100`)
        );

        const bar = makeElement("div", "score-bar");
        const fill = makeElement("div", "score-bar-fill");

        fill.style.width = `${Math.max(0, Math.min(100, value))}%`;

        bar.appendChild(fill);
        item.appendChild(heading);
        item.appendChild(bar);
        wrapper.appendChild(item);
    });

    return wrapper;
}

function createTrainCard(train, index) {
    const card = makeElement("article", "train-card");

    // Train name and fare
    const top = makeElement("div", "train-card-top");
    const identity = makeElement("div", "train-identity");

    identity.appendChild(
        makeElement("span", "train-number", `Train ${train.number ?? "—"}`)
    );

    identity.appendChild(
        makeElement("h3", "train-name", train.name || "Unnamed train")
    );

    top.appendChild(identity);
    top.appendChild(makeElement("span", "train-fare", formatMoney(train.fare)));
    card.appendChild(top);

    // Recommendation score
    const score = Number(train.recommendation_score);

    if (Number.isFinite(score)) {
        const scorePanel = makeElement("div", "recommendation-score");
        const scoreHeading = makeElement("div", "recommendation-score-heading");

        scoreHeading.appendChild(
            makeElement(
                "span",
                "recommendation-label",
                index === 0 ? "Top recommendation" : "Recommendation score"
            )
        );

        scoreHeading.appendChild(
            makeElement("strong", "recommendation-value", `${score.toFixed(2)} / 100`)
        );

        const scoreBar = makeElement("div", "score-bar");
        const scoreFill = makeElement("div", "score-bar-fill");

        scoreFill.style.width = `${Math.max(0, Math.min(100, score))}%`;

        scoreBar.appendChild(scoreFill);
        scorePanel.appendChild(scoreHeading);
        scorePanel.appendChild(scoreBar);
        card.appendChild(scorePanel);
    }

    // Route
    const route = makeElement("div", "train-route");

    const source = makeElement("div", "route-station");
    source.appendChild(makeElement("span", "route-label", "FROM"));
    source.appendChild(makeElement("strong", "route-city", train.source || "—"));

    const routeLine = makeElement("div", "route-line");
    routeLine.appendChild(makeElement("span", "route-line-dot"));
    routeLine.appendChild(makeElement("span", "route-line-track"));
    routeLine.appendChild(makeElement("span", "route-line-dot"));

    const destination = makeElement("div", "route-station route-end");
    destination.appendChild(makeElement("span", "route-label", "TO"));
    destination.appendChild(
        makeElement("strong", "route-city", train.destination || "—")
    );

    route.appendChild(source);
    route.appendChild(routeLine);
    route.appendChild(destination);
    card.appendChild(route);

    // Journey details
    const details = makeElement("div", "train-details");
    const duration = Number(train.duration_minutes);

    if (Number.isFinite(duration)) {
        const hours = Math.floor(duration / 60);
        const minutes = duration % 60;

        details.appendChild(
            makeElement("span", "train-detail", `Journey: ${hours}h ${minutes}m`)
        );
    }

    if (train.departure_time) {
        details.appendChild(
            makeElement("span", "train-detail", `Departure: ${train.departure_time}`)
        );
    }

    const seats = Number(train.seats);
    const seatsText = Number.isFinite(seats)
        ? `${seats} seat${seats === 1 ? "" : "s"} available`
        : "Seat count unavailable";

    details.appendChild(
        makeElement(
            "span",
            Number.isFinite(seats) && seats > 0
                ? "seat-status"
                : "seat-status seat-unavailable",
            seatsText
        )
    );

    card.appendChild(details);

    // Score explanation
    const breakdown = createScoreBreakdown(train);

    if (breakdown) {
        const disclosure = document.createElement("details");
        disclosure.className = "score-disclosure";

        const summary = document.createElement("summary");
        summary.textContent = "Why this score?";

        disclosure.appendChild(summary);
        disclosure.appendChild(breakdown);
        card.appendChild(disclosure);
    }

    // Book button
    const bottom = makeElement("div", "train-card-bottom");
    const bookButton = makeElement("button", "book-button", "Book Ticket");

    bookButton.type = "button";
    bookButton.disabled =
        !Number.isFinite(seats) ||
        seats <= 0 ||
        train.id === undefined ||
        train.id === null;

    bookButton.addEventListener("click", () => openBookingDialog(train));

    bottom.appendChild(bookButton);
    card.appendChild(bottom);

    return card;
}

async function searchTrains(event) {
    if (event) {
        event.preventDefault();
    }

    const thisSearch = ++searchNumber;
    const source = sourceInput.value;
    const destination = destinationInput.value;
    const budgetText = budgetInput?.value.trim() || "";

    if (!source || !destination) {
        clearTrainResults("Please select both stations.");
        return;
    }

    if (source === destination) {
        clearTrainResults(
            "Please choose different source and destination stations."
        );
        showToast("Source and destination must be different.", "error");
        return;
    }

    if (budgetText !== "") {
        const budget = Number(budgetText);

        if (!Number.isFinite(budget) || budget < 0) {
            clearTrainResults("Please enter a valid non-negative budget.");
            return;
        }
    }

    setSearchLoading(true);
    clearTrainResults();
    searchMessage.textContent = "Finding and ranking trains...";

    try {
        const query = new URLSearchParams({
            source,
            destination,
            ...getRecommendationPreferences()
        });

        if (budgetText !== "") {
            query.set("budget", budgetText);
        }

        // The current Flask API does not filter by journey date.
        const data = await apiRequest(`/api/trains?${query.toString()}`);

        if (thisSearch !== searchNumber) return;

        if (!Array.isArray(data.trains)) {
            throw new Error("The trains response has an unexpected format.");
        }

        currentTrains = data.trains;

        if (resultCount) {
            resultCount.textContent =
                `${currentTrains.length} train${currentTrains.length === 1 ? "" : "s"}`;
        }

        if (currentTrains.length === 0) {
            searchMessage.textContent =
                "No trains match your selected route and budget.";

            const empty = makeElement("div", "empty-state");
            empty.appendChild(makeElement("h3", "", "No matching trains"));
            empty.appendChild(
                makeElement("p", "", "Try a different route or increase your budget.")
            );
            trainList.appendChild(empty);

            setConnectionStatus(true, "Backend connected");
            return;
        }

        const fragment = document.createDocumentFragment();

        currentTrains.forEach((train, index) => {
            fragment.appendChild(createTrainCard(train, index));
        });

        trainList.appendChild(fragment);

        const allScored = currentTrains.every(
            train => Number.isFinite(Number(train.recommendation_score))
        );

        searchMessage.textContent = allScored
            ? `Showing ${currentTrains.length} ranked train(s) from ${source} to ${destination}.`
            : `Showing ${currentTrains.length} train(s).`;

        setConnectionStatus(true, "Backend connected");
    } catch (error) {
        if (thisSearch !== searchNumber) return;

        currentTrains = [];
        clearTrainResults(error.message);
        setConnectionStatus(false, "Backend unavailable");
        showToast(error.message, "error");
    } finally {
        if (thisSearch === searchNumber) {
            setSearchLoading(false);
        }
    }
}

// ---------- Swap stations ----------

swapButton?.addEventListener("click", () => {
    const oldSource = sourceInput.value;
    sourceInput.value = destinationInput.value;
    destinationInput.value = oldSource;

    showToast("Stations swapped.", "info");
});

// ---------- Family booking ----------

function renderPassengerFields() {
    if (!passengerCountInput || !passengerDetailsContainer) return;

    const count = Number(passengerCountInput.value);

    if (!Number.isInteger(count) || count < 1 || count > 10) return;

    passengerDetailsContainer.replaceChildren();

    for (let i = 0; i < count; i++) {
        const section = makeElement("section", "passenger-field");
        section.appendChild(makeElement("h3", "", `Passenger ${i + 1}`));

        // Name
        const nameLabel = makeElement("label", "", "FULL NAME");
        nameLabel.htmlFor = `family-name-${i}`;

        const nameInput = makeElement("input");
        nameInput.type = "text";
        nameInput.id = `family-name-${i}`;
        nameInput.name = `passenger-name-${i}`;
        nameInput.minLength = 2;
        nameInput.maxLength = 100;
        nameInput.required = true;
        nameInput.placeholder = "Enter full name";
        nameInput.autocomplete = "off";

        section.appendChild(nameLabel);
        section.appendChild(nameInput);

        // Age
        const ageLabel = makeElement("label", "", "AGE");
        ageLabel.htmlFor = `family-age-${i}`;

        const ageInput = makeElement("input");
        ageInput.type = "number";
        ageInput.id = `family-age-${i}`;
        ageInput.name = `passenger-age-${i}`;
        ageInput.min = 0;
        ageInput.max = 120;
        ageInput.step = 1;
        ageInput.value = "20";
        ageInput.required = true;
        ageInput.placeholder = "Enter age";

        section.appendChild(ageLabel);
        section.appendChild(ageInput);

        // Gender
        const genderLabel = makeElement("label", "", "GENDER");
        genderLabel.htmlFor = `family-gender-${i}`;

        const genderSelect = makeElement("select");
        genderSelect.id = `family-gender-${i}`;
        genderSelect.name = `passenger-gender-${i}`;
        genderSelect.required = true;

        ["Male", "Female", "Other", "Prefer not to say"].forEach(gender => {
            const option = makeElement("option", "", gender);
            option.value = gender;
            genderSelect.appendChild(option);
        });

        section.appendChild(genderLabel);
        section.appendChild(genderSelect);

        passengerDetailsContainer.appendChild(section);
    }

    updateFamilyFare();
}

function updateFamilyFare() {
    if (!selectedTrain || !passengerCountInput || !familyFareSummary) return;

    const count = Number(passengerCountInput.value);
    const total = Number(selectedTrain.fare) * count;

    familyFareSummary.textContent =
        `${count} passenger(s) × ${formatMoney(selectedTrain.fare)} = ` +
        `${formatMoney(total)} total`;
}

function openBookingDialog(train) {
    selectedTrain = train;

    selectedTrainName.textContent =
        `${train.number ?? ""} ${train.name || "Train"}`.trim();

    selectedTrainRoute.textContent =
        `${train.source} → ${train.destination}`;

    selectedTrainFare.textContent = formatMoney(train.fare);

    selectedTrainSummary.hidden = false;
    selectedTrainPreview.hidden = false;

    passengerCountInput.value = "1";
    renderPassengerFields();

    if (bookingDialog && typeof bookingDialog.showModal === "function") {
        bookingDialog.showModal();
    } else {
        showToast("Your browser does not support the booking dialog.", "error");
    }
}

function closeBookingDialog() {
    if (bookingDialog?.open) {
        bookingDialog.close();
    }

    selectedTrain = null;
}

closeBookingButton?.addEventListener("click", closeBookingDialog);

bookingDialog?.addEventListener("click", event => {
    if (event.target === bookingDialog) {
        closeBookingDialog();
    }
});

passengerCountInput?.addEventListener("change", renderPassengerFields);

passengerForm?.addEventListener("submit", async event => {
    event.preventDefault();

    if (!selectedTrain) {
        showToast("Please select a train first.", "error");
        return;
    }

    const count = Number(passengerCountInput.value);
    const passengers = [];

    for (let i = 0; i < count; i++) {
        const nameInput = document.getElementById(`family-name-${i}`);
        const ageInput = document.getElementById(`family-age-${i}`);
        const genderInput = document.getElementById(`family-gender-${i}`);

        if (!nameInput || !ageInput || !genderInput) {
            showToast("Passenger fields are missing. Reopen the booking form.", "error");
            return;
        }

        const name = nameInput.value.trim();
        const ageText = ageInput.value.trim();
        const age = Number(ageText);
        const gender = genderInput.value;

        if (name.length < 2 || name.length > 100) {
            showToast(`Enter a valid name for passenger ${i + 1}.`, "error");
            nameInput.focus();
            return;
        }

        if (
            ageText === "" ||
            !Number.isInteger(age) ||
            age < 0 ||
            age > 120
        ) {
            showToast(`Enter a valid age for passenger ${i + 1}.`, "error");
            ageInput.focus();
            return;
        }

        passengers.push({ name, age, gender });
    }

    await submitBooking(passengers);
});

async function submitBooking(passengers) {
    if (!selectedTrain) {
        showToast("Please select a train first.", "error");
        return;
    }

    setBookingLoading(true);

    try {
        const data = await apiRequest("/api/bookings", {
            method: "POST",
            body: JSON.stringify({
                train_id: selectedTrain.id,
                passengers
            })
        });

        closeBookingDialog();

        showToast(
            `${data.message} Total fare: ${formatMoney(data.total_fare)}`,
            "success"
        );

        await Promise.allSettled([
            searchTrains(),
            loadBookings()
        ]);
    } catch (error) {
        showToast(`Booking failed: ${error.message}`, "error");
    } finally {
        setBookingLoading(false);
    }
}

// ---------- Booking history ----------

function renderBooking(booking) {
    const card = makeElement("article", "booking-card");
    const heading = makeElement("div", "booking-card-heading");

    heading.appendChild(
        makeElement(
            "span",
            "booking-reference",
            `Booking #${booking.booking_id ?? "—"}`
        )
    );

    heading.appendChild(
        makeElement("span", "booking-status", booking.status || "Unknown")
    );

    card.appendChild(heading);

    card.appendChild(
        makeElement("h3", "booking-passenger", booking.passenger_name || "Passenger")
    );

    card.appendChild(
        makeElement("p", "booking-train", booking.train_name || "Train details unavailable")
    );

    if (booking.source || booking.destination) {
        card.appendChild(
            makeElement(
                "p",
                "booking-route",
                `${booking.source || "—"} → ${booking.destination || "—"}`
            )
        );
    }

    // Show all passengers for family bookings.
    if (Array.isArray(booking.passengers) && booking.passengers.length > 0) {
        const passengerList = makeElement("ul", "booking-passenger-list");

        booking.passengers.forEach((passenger, index) => {
            const details = [
                passenger.name || `Passenger ${index + 1}`,
                passenger.age !== null && passenger.age !== undefined
                    ? `Age: ${passenger.age}`
                    : null,
                passenger.gender || null
            ].filter(Boolean).join(" · ");

            passengerList.appendChild(makeElement("li", "", details));
        });

        card.appendChild(passengerList);
    }

    const totalFare = booking.total_fare ?? booking.fare;

    card.appendChild(
        makeElement("p", "booking-fare", `Total fare: ${formatMoney(totalFare)}`)
    );

    if (booking.passenger_count) {
        card.appendChild(
            makeElement(
                "p",
                "booking-count",
                `${booking.passenger_count} passenger(s)`
            )
        );
    }

    return card;
}

async function loadBookings() {
    if (!bookingMessage || !bookingList) return;

    bookingMessage.textContent = "Loading booking history...";
    bookingList.replaceChildren();

    if (refreshBookingsButton) {
        refreshBookingsButton.disabled = true;
    }

    try {
        const data = await apiRequest("/api/bookings");

        if (!Array.isArray(data.bookings)) {
            throw new Error("The bookings response has an unexpected format.");
        }

        if (data.bookings.length === 0) {
            bookingMessage.textContent = "No bookings yet.";

            const empty = makeElement("div", "empty-state compact");
            empty.appendChild(
                makeElement("p", "", "Your bookings will appear here after you book a ticket.")
            );

            bookingList.appendChild(empty);
            setConnectionStatus(true, "Backend connected");
            return;
        }

        const fragment = document.createDocumentFragment();

        data.bookings.forEach(booking => {
            fragment.appendChild(renderBooking(booking));
        });

        bookingList.appendChild(fragment);

        bookingMessage.textContent =
            `${data.bookings.length} booking${data.bookings.length === 1 ? "" : "s"} found.`;

        setConnectionStatus(true, "Backend connected");
    } catch (error) {
        bookingMessage.textContent = `Could not load bookings: ${error.message}`;
        setConnectionStatus(false, "Backend unavailable");
    } finally {
        if (refreshBookingsButton) {
            refreshBookingsButton.disabled = false;
        }
    }
}

refreshBookingsButton?.addEventListener("click", loadBookings);

// ---------- Default journey date ----------

if (dateInput) {
    const today = new Date();

    const localToday = [
        today.getFullYear(),
        String(today.getMonth() + 1).padStart(2, "0"),
        String(today.getDate()).padStart(2, "0")
    ].join("-");

    dateInput.min = localToday;

    if (!dateInput.value) {
        dateInput.value = localToday;
    }
}

// ---------- Connect events ----------

searchForm?.addEventListener("submit", searchTrains);

// ---------- Initial page load ----------

setConnectionStatus(false, "Connecting to backend...");
searchTrains();
loadBookings();

// OS synchronization demonstration
(() => {
    const runButton = document.getElementById("sync-run-btn");

    // Safe if this script is also used on pages without the demo section.
    if (!runButton) return;

    const attemptsInput = document.getElementById("sync-attempts");
    const seatsInput = document.getElementById("sync-seats");
    const message = document.getElementById("sync-message");
    const totalOutput = document.getElementById("sync-total");
    const successOutput = document.getElementById("sync-success");
    const rejectedOutput = document.getElementById("sync-rejected");
    const remainingOutput = document.getElementById("sync-remaining");
    const resultsContainer = document.getElementById("sync-request-results");

    runButton.addEventListener("click", async () => {
        const attempts = Number(attemptsInput.value);
        const seats = Number(seatsInput.value);

        if (
            !Number.isInteger(attempts) ||
            attempts < 1 || attempts > 50 ||
            !Number.isInteger(seats) ||
            seats < 0 || seats > 50
        ) {
            message.textContent =
                "Enter requests from 1–50 and seats from 0–50.";
            return;
        }

        runButton.disabled = true;
        message.textContent = "Running concurrent requests...";
        resultsContainer.replaceChildren();

        try {
            const url =
                `http://127.0.0.1:5000/api/demo/concurrency` +
                `?attempts=${attempts}&seats=${seats}`;

            const response = await fetch(url);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Demo request failed.");
            }

            totalOutput.textContent = data.total_requests;
            successOutput.textContent = data.successful_bookings;
            rejectedOutput.textContent = data.rejected_requests;
            remainingOutput.textContent = data.remaining_seats;

            message.textContent =
                `Completed. Real database changed: ${
                    data.real_database_changed ? "Yes" : "No"
                }.`;

            data.results.forEach((result) => {
                const row = document.createElement("div");
                row.className = "sync-result-row";

                const requestLabel = document.createElement("span");
                requestLabel.textContent = `Request ${result.request}`;

                const status = document.createElement("strong");
                status.textContent = result.result;
                status.className =
                    result.result === "SUCCESS"
                        ? "sync-status-success"
                        : "sync-status-rejected";

                const seatsLabel = document.createElement("span");
                seatsLabel.textContent =
                    `Remaining seats: ${result.remaining_seats}`;

                row.append(requestLabel, status, seatsLabel);
                resultsContainer.appendChild(row);
            });
        } catch (error) {
            message.textContent =
                `Could not run demo: ${error.message}. ` +
                "Check that Flask is running on port 5000.";
        } finally {
            runButton.disabled = false;
        }
    });
})();
