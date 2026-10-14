
"use strict";

// Railway Reservation System — RailEase Frontend
// Flask backend: http://127.0.0.1:5000

const API = "http://127.0.0.1:5000";
const REQUEST_TIMEOUT = 10000;

// ---------- Get HTML elements ----------

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
const refreshBookingsButton =
    document.getElementById("refresh-bookings");

const bookingDialog = document.getElementById("booking-dialog");
const passengerForm = document.getElementById("passenger-form");
const passengerNameInput = document.getElementById("passenger-name");
const closeBookingButton = document.getElementById("close-booking");
const confirmBookingButton =
    document.getElementById("confirm-booking");

const selectedTrainSummary =
    document.getElementById("selected-train-summary");
const selectedTrainPreview =
    document.getElementById("selected-train-preview");
const selectedTrainName =
    document.getElementById("selected-train-name");
const selectedTrainRoute =
    document.getElementById("selected-train-route");
const selectedTrainFare =
    document.getElementById("selected-train-fare");

const connectionLabel = document.getElementById("connection-label");
const toastContainer = document.getElementById("toast-container");

// Recommendation controls added to index.html
const priceWeightInput = document.getElementById("priceWeight");
const durationWeightInput = document.getElementById("durationWeight");
const availabilityWeightInput =
    document.getElementById("availabilityWeight");
const timingWeightInput = document.getElementById("timingWeight");
const preferredTimeInput = document.getElementById("preferredTime");
const resetPreferencesButton =
    document.getElementById("reset-preferences");

// ---------- Application state ----------

let currentTrains = [];
let selectedTrain = null;
let searchNumber = 0;

// ---------- Helpers ----------

function makeElement(tag, className, text) {
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

    const toast = makeElement(
        "div",
        `toast toast-${type}`,
        message
    );

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
        buttonText.textContent = isLoading
            ? "Searching..."
            : "Search trains";
    } else {
        searchButton.textContent = isLoading
            ? "Searching..."
            : "Search trains →";
    }
}

function setBookingLoading(isLoading) {
    if (confirmBookingButton) {
        confirmBookingButton.disabled = isLoading;
        confirmBookingButton.textContent = isLoading
            ? "Booking..."
            : "Confirm booking →";
    }
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
                ...(options.body
                    ? { "Content-Type": "application/json" }
                    : {}),
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
                data.error ||
                data.message ||
                `Server error (${response.status})`
            );
        }

        return data;
    } catch (error) {
        if (error.name === "AbortError") {
            throw new Error(
                "Request timed out. Check whether Flask is running."
            );
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

if (resetPreferencesButton) {
    resetPreferencesButton.addEventListener("click", resetPreferences);
}

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

    top.appendChild(
        makeElement("span", "train-fare", formatMoney(train.fare))
    );

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
            makeElement(
                "strong",
                "recommendation-value",
                `${score.toFixed(2)} / 100`
            )
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
    source.appendChild(
        makeElement("strong", "route-city", train.source || "—")
    );

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

    // Duration, departure time, seats
    const details = makeElement("div", "train-details");

    const duration = Number(train.duration_minutes);

    if (Number.isFinite(duration)) {
        const hours = Math.floor(duration / 60);
        const minutes = duration % 60;

        details.appendChild(
            makeElement(
                "span",
                "train-detail",
                `Journey: ${hours}h ${minutes}m`
            )
        );
    }

    if (train.departure_time) {
        details.appendChild(
            makeElement(
                "span",
                "train-detail",
                `Departure: ${train.departure_time}`
            )
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

    // Optional score explanation
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

    // Booking button
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

        // Note: journey-date is not sent as a filter because
        // the current Flask backend does not implement date filtering.
        const data = await apiRequest(`/api/trains?${query.toString()}`);

        // Ignore outdated responses from earlier searches.
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

            trainList.appendChild(
                makeElement(
                    "div",
                    "empty-state",
                    "Try a different route or increase your budget."
                )
            );

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
            : `Showing ${currentTrains.length} train(s). The backend has not returned recommendation scores yet.`;

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

if (swapButton) {
    swapButton.addEventListener("click", () => {
        const oldSource = sourceInput.value;

        sourceInput.value = destinationInput.value;
        destinationInput.value = oldSource;

        showToast("Stations swapped.", "info");
    });
}

// ---------- Booking dialog ----------

function openBookingDialog(train) {
    selectedTrain = train;

    if (selectedTrainName) {
        selectedTrainName.textContent =
            `${train.number ?? ""} ${train.name || "Train"}`.trim();
    }

    if (selectedTrainRoute) {
        selectedTrainRoute.textContent =
            `${train.source} → ${train.destination}`;
    }

    if (selectedTrainFare) {
        selectedTrainFare.textContent = formatMoney(train.fare);
    }

    if (selectedTrainSummary) {
        selectedTrainSummary.hidden = false;
    }

    if (selectedTrainPreview) {
        selectedTrainPreview.hidden = false;
    }

    if (passengerNameInput) {
        passengerNameInput.value = "";
    }

    if (bookingDialog && typeof bookingDialog.showModal === "function") {
        bookingDialog.showModal();
        passengerNameInput?.focus();
    } else {
        const passengerName = window.prompt(
            `Book ${train.name || "this train"}\nEnter passenger name:`
        );

        if (passengerName && passengerName.trim()) {
            submitBooking(passengerName.trim());
        }
    }
}

function closeBookingDialog() {
    if (bookingDialog && bookingDialog.open) {
        bookingDialog.close();
    }

    selectedTrain = null;
}

if (closeBookingButton) {
    closeBookingButton.addEventListener("click", closeBookingDialog);
}

if (bookingDialog) {
    bookingDialog.addEventListener("click", event => {
        if (event.target === bookingDialog) {
            closeBookingDialog();
        }
    });
}

if (passengerForm) {
    passengerForm.addEventListener("submit", async event => {
        event.preventDefault();

        const passengerName = passengerNameInput.value.trim();

        if (passengerName.length < 2) {
            passengerNameInput.setCustomValidity(
                "Please enter at least two characters for the passenger name."
            );
            passengerNameInput.reportValidity();
            return;
        }

        passengerNameInput.setCustomValidity("");
        await submitBooking(passengerName);
    });

    passengerNameInput?.addEventListener("input", () => {
        passengerNameInput.setCustomValidity("");
    });
}

async function submitBooking(passengerName) {
    if (!selectedTrain) {
        showToast("Please select a train first.", "error");
        return;
    }

    setBookingLoading(true);

    try {
        const data = await apiRequest("/api/bookings", {
            method: "POST",
            body: JSON.stringify({
                passenger_name: passengerName,
                train_id: selectedTrain.id
            })
        });

        closeBookingDialog();

        showToast(
            data.message || "Booking completed successfully.",
            "success"
        );

        // Refresh train seats and booking history.
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
        makeElement(
            "span",
            "booking-status",
            booking.status || "Unknown"
        )
    );

    card.appendChild(heading);

    card.appendChild(
        makeElement(
            "h3",
            "booking-passenger",
            booking.passenger_name || "Passenger"
        )
    );

    card.appendChild(
        makeElement(
            "p",
            "booking-train",
            booking.train_name || "Train details unavailable"
        )
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

    card.appendChild(
        makeElement(
            "p",
            "booking-fare",
            `Fare: ${formatMoney(booking.fare)}`
        )
    );

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

            bookingList.appendChild(
                makeElement(
                    "div",
                    "empty-state",
                    "Your bookings will appear here after you book a ticket."
                )
            );

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
        bookingMessage.textContent =
            `Could not load bookings: ${error.message}`;

        setConnectionStatus(false, "Backend unavailable");
    } finally {
        if (refreshBookingsButton) {
            refreshBookingsButton.disabled = false;
        }
    }
}

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

if (searchForm) {
    searchForm.addEventListener("submit", searchTrains);
}

if (refreshBookingsButton) {
    refreshBookingsButton.addEventListener("click", loadBookings);
}

// ---------- Initial page load ----------

setConnectionStatus(false, "Connecting to backend...");
searchTrains();
loadBookings();
