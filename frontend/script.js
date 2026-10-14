// Railway Reservation System — Frontend JavaScript
// Backend: Flask running at http://127.0.0.1:5000
const API = "http://127.0.0.1:5000";
const REQUEST_TIMEOUT = 10000;

// ---------- Get HTML elements ----------

const searchForm = document.getElementById("search-form");
const sourceInput = document.getElementById("source");
const destinationInput = document.getElementById("destination");
const dateInput = document.getElementById("journey-date");
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

    // Remove the notification after a few seconds.
    window.setTimeout(() => {
        toast.remove();
    }, 4000);
}

function setConnectionStatus(connected, message) {
    if (!connectionLabel) return;

    connectionLabel.textContent = message;

    const statusContainer =
        connectionLabel.closest(".system-status");

    if (statusContainer) {
        statusContainer.classList.toggle(
            "is-connected",
            connected
        );

        statusContainer.classList.toggle(
            "is-disconnected",
            !connected
        );
    }
}

function setSearchLoading(isLoading) {
    if (!searchButton) return;

    searchButton.disabled = isLoading;

    const buttonText = searchButton.querySelector(
        "[data-button-text]"
    );

    if (buttonText) {
        buttonText.textContent = isLoading
            ? "Searching..."
            : "Search Trains";
    } else {
        searchButton.textContent = isLoading
            ? "Searching..."
            : "Search Trains";
    }
}

function setBookingLoading(isLoading) {
    if (confirmBookingButton) {
        confirmBookingButton.disabled = isLoading;
        confirmBookingButton.textContent = isLoading
            ? "Booking..."
            : "Confirm Booking";
    }
}

// ---------- API requests ----------

async function apiRequest(path, options = {}) {
    const controller = new AbortController();

    const timeoutId = window.setTimeout(() => {
        controller.abort();
    }, REQUEST_TIMEOUT);

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
                    "The server returned an invalid response. Check the Flask backend."
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
                "The request took too long. Check whether the backend is running."
            );
        }

        if (error instanceof TypeError) {
            throw new Error(
                "Cannot connect to the backend. Start your Flask server and check the API address."
            );
        }

        throw error;
    } finally {
        window.clearTimeout(timeoutId);
    }
}

// ---------- Train search ----------

function clearTrainResults(message = "") {
    trainList.replaceChildren();

    if (resultCount) {
        resultCount.textContent = "0 trains";
    }

    if (message) {
        searchMessage.textContent = message;
    }
}

function createTrainCard(train) {
    const card = makeElement("article", "train-card");

    const top = makeElement("div", "train-card-top");
    const identity = makeElement("div", "train-identity");

    identity.appendChild(
        makeElement(
            "span",
            "train-number",
            `Train ${train.number ?? "—"}`
        )
    );

    identity.appendChild(
        makeElement(
            "h3",
            "train-name",
            train.name || "Unnamed train"
        )
    );

    top.appendChild(identity);

    top.appendChild(
        makeElement(
            "span",
            "train-fare",
            formatMoney(train.fare)
        )
    );

    card.appendChild(top);

    const route = makeElement("div", "train-route");

    const source = makeElement("div", "route-station");
    source.appendChild(
        makeElement("span", "route-label", "FROM")
    );
    source.appendChild(
        makeElement("strong", "route-city", train.source || "—")
    );

    const routeLine = makeElement("div", "route-line");
    routeLine.appendChild(makeElement("span", "route-line-dot"));
    routeLine.appendChild(makeElement("span", "route-line-track"));
    routeLine.appendChild(makeElement("span", "route-line-dot"));

    const destination = makeElement("div", "route-station route-end");
    destination.appendChild(
        makeElement("span", "route-label", "TO")
    );
    destination.appendChild(
        makeElement(
            "strong",
            "route-city",
            train.destination || "—"
        )
    );

    route.appendChild(source);
    route.appendChild(routeLine);
    route.appendChild(destination);

    card.appendChild(route);

    const bottom = makeElement("div", "train-card-bottom");

    const seats = Number(train.seats);
    const seatsText = Number.isFinite(seats)
        ? `${seats} seat${seats === 1 ? "" : "s"} available`
        : "Seat count unavailable";

    bottom.appendChild(
        makeElement(
            "span",
            Number.isFinite(seats) && seats > 0
                ? "seat-status"
                : "seat-status seat-unavailable",
            seatsText
        )
    );

    const bookButton = makeElement(
        "button",
        "book-button",
        "Book Ticket"
    );

    bookButton.type = "button";
    bookButton.disabled =
        !Number.isFinite(seats) ||
        seats <= 0 ||
        train.id === undefined ||
        train.id === null;

    bookButton.addEventListener("click", () => {
        openBookingDialog(train);
    });

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

    setSearchLoading(true);
    clearTrainResults();
    searchMessage.textContent = "Finding trains for your route...";

    try {
        const query = new URLSearchParams({
            source,
            destination
        });

        // The current backend endpoint accepts source and destination.
        // The selected date is not sent because the existing API
        // does not currently support date-based filtering.
        const data = await apiRequest(`/api/trains?${query.toString()}`);

        // Ignore old responses if the user searches again.
        if (thisSearch !== searchNumber) return;

        if (!Array.isArray(data.trains)) {
            throw new Error(
                "The trains response has an unexpected format."
            );
        }

        currentTrains = data.trains;

        if (resultCount) {
            resultCount.textContent =
                `${currentTrains.length} train${currentTrains.length === 1 ? "" : "s"}`;
        }

        if (currentTrains.length === 0) {
            searchMessage.textContent =
                "No trains were found for this route in the current database.";

            const empty = makeElement(
                "div",
                "empty-state",
                "Try another route or check the trains stored in your database."
            );

            trainList.appendChild(empty);
            setConnectionStatus(true, "Backend connected");
            return;
        }

        const fragment = document.createDocumentFragment();

        currentTrains.forEach(train => {
            fragment.appendChild(createTrainCard(train));
        });

        trainList.appendChild(fragment);

        searchMessage.textContent =
            `Showing ${currentTrains.length} train${currentTrains.length === 1 ? "" : "s"} for ${source} to ${destination}.`;

        setConnectionStatus(true, "Backend connected");
    } catch (error) {
        if (thisSearch !== searchNumber) return;

        currentTrains = [];
        clearTrainResults(error.message);
        setConnectionStatus(false, "Backend unavailable");
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
        // Close when the user clicks the dark area outside the dialog.
        if (event.target === bookingDialog) {
            closeBookingDialog();
        }
    });
}

if (passengerForm) {
    passengerForm.addEventListener("submit", async event => {
        event.preventDefault();

        const passengerName = passengerNameInput.value.trim();

        if (!passengerName) {
            passengerNameInput.setCustomValidity(
                "Please enter the passenger name."
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

        // Refresh the seat count and booking history after booking.
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
    bookingMessage.textContent = "Loading booking history...";
    bookingList.replaceChildren();

    if (refreshBookingsButton) {
        refreshBookingsButton.disabled = true;
    }

    try {
        const data = await apiRequest("/api/bookings");

        if (!Array.isArray(data.bookings)) {
            throw new Error(
                "The bookings response has an unexpected format."
            );
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

// ---------- Set a default journey date ----------

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

searchForm.addEventListener("submit", searchTrains);

if (refreshBookingsButton) {
    refreshBookingsButton.addEventListener("click", loadBookings);
}

// ---------- Initial page load ----------

setConnectionStatus(false, "Connecting to backend...");
searchTrains();
loadBookings();