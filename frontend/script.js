
const API = "http://127.0.0.1:5000";

const searchForm = document.getElementById("search-form");
const sourceInput = document.getElementById("source");
const destinationInput = document.getElementById("destination");
const trainList = document.getElementById("train-list");
const searchMessage = document.getElementById("search-message");
const bookingList = document.getElementById("booking-list");
const bookingMessage = document.getElementById("booking-message");

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }

  return data;
}

async function searchTrains(event) {
  if (event) event.preventDefault();

  const source = sourceInput.value;
  const destination = destinationInput.value;

  if (source === destination) {
    searchMessage.textContent = "Choose different source and destination.";
    trainList.replaceChildren();
    return;
  }

  searchMessage.textContent = "Searching...";
  trainList.replaceChildren();

  try {
    const query = new URLSearchParams({ source, destination });
    const data = await apiRequest(`/api/trains?${query}`);

    searchMessage.textContent = `${data.count} train(s) found.`;

    data.trains.forEach(train => {
      const row = document.createElement("tr");

      [
        `${train.number} - ${train.name}`,
        `${train.source} → ${train.destination}`,
        `₹${train.fare}`,
        train.seats
      ].forEach(value => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.appendChild(cell);
      });

      const actionCell = document.createElement("td");
      const bookButton = document.createElement("button");
      bookButton.textContent = "Book";
      bookButton.disabled = train.seats <= 0;

      bookButton.addEventListener("click", () => bookTrain(train));

      actionCell.appendChild(bookButton);
      row.appendChild(actionCell);
      trainList.appendChild(row);
    });
  } catch (error) {
    searchMessage.textContent =
      `Could not load trains: ${error.message}. Is Flask running?`;
  }
}

async function bookTrain(train) {
  const passengerName = prompt("Enter passenger name:");

  if (!passengerName || !passengerName.trim()) return;

  try {
    const data = await apiRequest("/api/bookings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        passenger_name: passengerName.trim(),
        train_id: train.id
      })
    });

    alert(data.message);
    await searchTrains();
    await loadBookings();
  } catch (error) {
    alert(`Booking failed: ${error.message}`);
  }
}

async function loadBookings() {
  bookingMessage.textContent = "Loading bookings...";
  bookingList.replaceChildren();

  try {
    const data = await apiRequest("/api/bookings");

    bookingMessage.textContent = `${data.count} booking(s).`;

    data.bookings.forEach(booking => {
      const item = document.createElement("div");
      item.className = "booking";

      item.textContent =
        `Booking #${booking.booking_id} | ` +
        `${booking.passenger_name} | ${booking.train_name} | ` +
        `₹${booking.fare} | ${booking.status}`;

      bookingList.appendChild(item);
    });
  } catch (error) {
    bookingMessage.textContent =
      `Could not load bookings: ${error.message}`;
  }
}

searchForm.addEventListener("submit", searchTrains);

document.getElementById("refresh-bookings")
  .addEventListener("click", loadBookings);

searchTrains();
loadBookings();
