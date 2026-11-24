RAILEASE - UPDATED PROJECT

FEATURES IN THIS VERSION
- Passenger-selectable numbered seats in a coach-style 2+2 layout.
- Window seats are marked W; the two middle aisle positions are marked A/M.
- Live seat statuses: green Available, red Booked, orange Temporarily locked.
- Seat map refreshes every 3 seconds while the booking dialog is open.
- Exactly one seat must be selected per passenger. The backend validates the selection atomically to prevent double booking.
- Unpaid seat holds expire after 2 minutes and are released.
- Passenger journey date is limited to today through exactly six calendar months ahead (frontend calendar, train search API, seat-map API, and booking API validation).
- Passenger booking form no longer asks for booking priority. The separate OS priority scheduling demo remains available.

RUN ON WINDOWS
1. Extract the ZIP.
2. Open the extracted project folder in PyCharm.
3. Terminal 1:
   cd python_backend
   python -m pip install -r requirements.txt
   python app.py
4. Terminal 2:
   cd frontend
   python -m http.server 5500
5. Open http://localhost:5500/index.html

Keep both terminals running. Log in, search for a train and date, click Book, enter passenger details, and select one available seat per passenger from the coach plan.

BOOKING DATE RULE
- The latest permitted journey date is the same calendar day exactly 6 months after today (clamped to the last day of the target month when needed).
- Example: if today is 24 November 2026, the last permitted date is 24 May 2027. 25 May 2027 and later are rejected by both frontend and backend.

NOTES
- Payment is a demonstration only; no real money is processed.
- SQLite databases are included. Back up your database before replacing an existing project.
- The seat layout is a simplified demo coach layout, not an official railway berth chart. Window marking is illustrative.


SIX-MONTH BOOKING LIMIT (IMPORTANT)
-----------------------------------
The backend enforces the date limit centrally for train search, seat availability, and booking submission. When starting python app.py, the terminal prints the active allowed date range. Confirm that message appears and that the displayed app.py path is this extracted project folder. Stop any older backend terminal before starting this one.


PHONE QR DEMO PAYMENT
Install dependencies with python -m pip install -r requirements.txt. Flask listens on 0.0.0.0:5000 so a phone on the same Wi-Fi can open the QR link. Scan the QR from the laptop payment dialog and tap Approve Demo Payment on the phone. This is a classroom simulation only; no real UPI payment or money transfer occurs. Allow Python through Windows Firewall on private networks if prompted.

CANCELLATION AND WALLET UPDATE
- Confirmed, successfully paid bookings now have a Cancel booking button in Booking History.
- Cancelling credits 60% of the booking's total fare to the passenger's RailEase wallet; the remaining 40% is retained as the cancellation fee.
- The cancelled booking's seats are released back to inventory. The backend processes cancellation in a SQLite transaction and prevents a second refund for the same booking.
- The wallet balance is shown in the RailEase wallet section. Wallet credits are demo in-app credits, not a bank/UPI refund and cannot be withdrawn unless a separate payout feature is implemented.
- Existing SQLite databases are migrated automatically when the backend starts; keep your database files.
