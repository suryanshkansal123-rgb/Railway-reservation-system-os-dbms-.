
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from recommendation import calculate_recommendations

app = Flask(__name__)
CORS(app)

DATABASE = Path(__file__).resolve().parent / "railway_users.db"
MAX_PASSENGERS = 10
VALID_GENDERS = {"Male", "Female", "Other", "Prefer not to say"}


def get_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS trains (
                id INTEGER PRIMARY KEY,
                number TEXT NOT NULL,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                destination TEXT NOT NULL,
                fare REAL NOT NULL,
                duration_minutes INTEGER NOT NULL,
                departure_time TEXT NOT NULL,
                seats INTEGER NOT NULL DEFAULT 0 CHECK (seats >= 0)
            )
        """)

        # Existing single-passenger booking table is preserved.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                passenger_name TEXT NOT NULL,
                train_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Confirmed',
                FOREIGN KEY (train_id) REFERENCES trains(id)
            )
        """)

        # New tables for family bookings.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS booking_groups (
                group_id INTEGER PRIMARY KEY AUTOINCREMENT,
                train_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Confirmed',
                passenger_count INTEGER NOT NULL,
                total_fare REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (train_id) REFERENCES trains(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS booking_passengers (
                passenger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL,
                FOREIGN KEY (group_id)
                    REFERENCES booking_groups(group_id)
                    ON DELETE CASCADE
            )
        """)

        count = conn.execute(
            "SELECT COUNT(*) FROM trains"
        ).fetchone()[0]

        if count == 0:
            sample_trains = [
                (1, "12001", "Shatabdi Express", "Delhi", "Dehradun", 650, 360, "06:45", 45),
                (2, "12017", "Dehradun Shatabdi", "Delhi", "Dehradun", 720, 345, "07:00", 30),
                (3, "14041", "Mussoorie Express", "Delhi", "Dehradun", 350, 480, "22:25", 60),
                (4, "14631", "Uttar Sampark Kranti", "Delhi", "Dehradun", 420, 420, "15:20", 25),
                (5, "12002", "Shatabdi Express", "Dehradun", "Delhi", 650, 360, "17:00", 40),
                (6, "14042", "Mussoorie Express", "Dehradun", "Delhi", 350, 480, "21:10", 55),
            ]

            conn.executemany("""
                INSERT INTO trains
                (id, number, name, source, destination, fare,
                 duration_minutes, departure_time, seats)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, sample_trains)

        conn.commit()


# ---------------- AUTHENTICATION ----------------

@app.get("/")
def home():
    return jsonify({
        "message": "Railway Reservation backend is running",
        "database": str(DATABASE)
    })


@app.post("/api/signup")
def signup():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if not name or not email or not isinstance(password, str):
        return jsonify({
            "error": "Name, email and password are required."
        }), 400

    if len(password) < 6:
        return jsonify({
            "error": "Password must contain at least 6 characters."
        }), 400

    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO users (name, email, password_hash)
                   VALUES (?, ?, ?)""",
                (name, email, generate_password_hash(password))
            )
            conn.commit()

        return jsonify({
            "message": "Signup successful! You can now log in.",
            "user": {
                "id": cursor.lastrowid,
                "name": name,
                "email": email
            }
        }), 201

    except sqlite3.IntegrityError:
        return jsonify({
            "error": "This email already exists. Please log in instead."
        }), 409
    except sqlite3.Error:
        app.logger.exception("Signup database error")
        return jsonify({"error": "Database error during signup."}), 500


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if not email or not isinstance(password, str) or not password:
        return jsonify({
            "error": "Please enter your email and password."
        }), 400

    try:
        with get_connection() as conn:
            user = conn.execute(
                """SELECT id, name, email, password_hash
                   FROM users WHERE email = ? COLLATE NOCASE""",
                (email,)
            ).fetchone()
    except sqlite3.Error:
        app.logger.exception("Login database error")
        return jsonify({"error": "Database error during login."}), 500

    if user is None or not check_password_hash(
        user["password_hash"], password
    ):
        return jsonify({"error": "Invalid email or password."}), 401

    return jsonify({
        "message": "Login successful!",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"]
        }
    })


# ---------------- TRAIN SEARCH ----------------

@app.get("/api/trains")
def search_trains():
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()

    try:
        budget_text = request.args.get("budget", "").strip()
        budget = float(budget_text) if budget_text else None

        if budget is not None and budget < 0:
            raise ValueError("Budget cannot be negative.")

        weights = {
            "price": float(request.args.get("price_weight", 5)),
            "duration": float(request.args.get("duration_weight", 4)),
            "availability": float(request.args.get("availability_weight", 3)),
            "timing": float(request.args.get("timing_weight", 2)),
        }

        if any(not 1 <= value <= 5 for value in weights.values()):
            raise ValueError("Weights must be between 1 and 5.")

        with get_connection() as conn:
            trains = conn.execute("""
                SELECT * FROM trains
                WHERE (? = '' OR source LIKE ?)
                  AND (? = '' OR destination LIKE ?)
                  AND (? IS NULL OR fare <= ?)
                ORDER BY departure_time
            """, (
                source, f"%{source}%",
                destination, f"%{destination}%",
                budget, budget
            )).fetchall()

        eligible = [dict(train) for train in trains]
        preferred_time = (
            request.args.get("preferred_time", "").strip() or None
        )

        recommended = calculate_recommendations(
            eligible, weights, preferred_time
        )

        return jsonify({"trains": recommended})

    except (ValueError, TypeError):
        return jsonify({
            "error": "Please check your budget, weights and preferred time."
        }), 400
    except sqlite3.Error:
        app.logger.exception("Train search database error")
        return jsonify({"error": "Could not search trains."}), 500


# ---------------- SINGLE + FAMILY BOOKINGS ----------------

@app.post("/api/bookings")
def create_booking():
    data = request.get_json(silent=True) or {}
    train_id = data.get("train_id")

    if train_id is None:
        return jsonify({"error": "Train ID is required."}), 400

    # Accept the new family payload, while retaining compatibility
    # with the old frontend's { passenger_name, train_id } payload.
    if "passengers" in data:
        raw_passengers = data.get("passengers")
        if not isinstance(raw_passengers, list):
            return jsonify({"error": "Passengers must be a list."}), 400
    else:
        raw_name = str(data.get("passenger_name", "")).strip()
        if not raw_name:
            return jsonify({"error": "Passenger name is required."}), 400
        raw_passengers = [{
            "name": raw_name,
            "age": 20,
            "gender": "Prefer not to say"
        }]

    if not 1 <= len(raw_passengers) <= MAX_PASSENGERS:
        return jsonify({
            "error": f"Choose between 1 and {MAX_PASSENGERS} passengers."
        }), 400

    passengers = []
    for index, person in enumerate(raw_passengers, start=1):
        if not isinstance(person, dict):
            return jsonify({
                "error": f"Passenger {index} details are invalid."
            }), 400

        name = str(person.get("name", person.get("passenger_name", ""))).strip()
        age = person.get("age")
        gender = str(person.get("gender", "Prefer not to say")).strip()

        if not name or len(name) < 2 or len(name) > 100:
            return jsonify({
                "error": f"Enter a valid name for passenger {index}."
            }), 400

        try:
            age = int(age)
        except (TypeError, ValueError):
            return jsonify({
                "error": f"Enter a valid age for passenger {index}."
            }), 400

        if not 0 <= age <= 120:
            return jsonify({
                "error": f"Passenger {index} age must be from 0 to 120."
            }), 400

        if gender not in VALID_GENDERS:
            return jsonify({
                "error": f"Select a valid gender for passenger {index}."
            }), 400

        passengers.append({
            "name": name,
            "age": age,
            "gender": gender
        })

    try:
        with get_connection() as conn:
            # BEGIN IMMEDIATE acquires SQLite's write reservation before
            # checking seats, serializing competing booking transactions.
            conn.execute("BEGIN IMMEDIATE")

            train = conn.execute(
                "SELECT id, name, fare, seats FROM trains WHERE id = ?",
                (train_id,)
            ).fetchone()

            if train is None:
                conn.rollback()
                return jsonify({"error": "Train not found."}), 404

            passenger_count = len(passengers)

            if train["seats"] < passenger_count:
                conn.rollback()
                return jsonify({
                    "error": (
                        f"Only {train['seats']} seats are available; "
                        f"{passenger_count} are required."
                    )
                }), 409

            # Conditional update provides a second guard against
            # allocating more seats than the train has.
            cursor = conn.execute("""
                UPDATE trains
                SET seats = seats - ?
                WHERE id = ? AND seats >= ?
            """, (passenger_count, train_id, passenger_count))

            if cursor.rowcount != 1:
                conn.rollback()
                return jsonify({
                    "error": "Not enough seats remain. Please search again."
                }), 409

            total_fare = float(train["fare"]) * passenger_count

            group_cursor = conn.execute("""
                INSERT INTO booking_groups
                    (train_id, passenger_count, total_fare)
                VALUES (?, ?, ?)
            """, (train_id, passenger_count, total_fare))

            group_id = group_cursor.lastrowid

            conn.executemany(
                """
                INSERT INTO booking_passengers
                    (booking_id, group_id, name, age, gender)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        None,
                        group_id,
                        person["name"],
                        person["age"],
                        person["gender"],
                    )
                    for person in passengers
                ],
            )

            # Preserve compatibility with older booking history that
            # reads from the original bookings table.
            # New family reservations are stored in the new group tables.
            conn.commit()

        return jsonify({
            "message": (
                "Family booking successful!"
                if len(passengers) > 1 else "Booking successful!"
            ),
            "booking_id": group_id,
            "passenger_count": len(passengers),
            "passengers": passengers,
            "train_name": train["name"],
            "fare_per_passenger": float(train["fare"]),
            "total_fare": total_fare
        }), 201

    except sqlite3.Error:
        app.logger.exception("Booking database error")
        return jsonify({"error": "Could not complete booking."}), 500


@app.get("/api/bookings")
def get_bookings():
    try:
        with get_connection() as conn:
            # Existing single-passenger bookings remain visible.
            old_rows = conn.execute("""
                SELECT
                    b.booking_id,
                    b.status,
                    b.passenger_name,
                    t.name AS train_name,
                    t.source,
                    t.destination,
                    t.fare
                FROM bookings b
                JOIN trains t ON t.id = b.train_id
                ORDER BY b.booking_id DESC
            """).fetchall()

            legacy_bookings = []
            for row in old_rows:
                item = dict(row)
                item["passengers"] = [{
                    "name": item["passenger_name"],
                    "age": None,
                    "gender": None
                }]
                item["passenger_count"] = 1
                item["total_fare"] = float(item["fare"])
                item["booking_type"] = "single"
                legacy_bookings.append(item)

            # New family bookings.
            groups = conn.execute("""
                SELECT
                    g.group_id AS booking_id,
                    g.status,
                    g.passenger_count,
                    g.total_fare,
                    t.name AS train_name,
                    t.source,
                    t.destination,
                    t.fare
                FROM booking_groups g
                JOIN trains t ON t.id = g.train_id
                ORDER BY g.group_id DESC
            """).fetchall()

            family_bookings = []
            for group in groups:
                item = dict(group)
                passengers = conn.execute("""
                    SELECT name, age, gender
                    FROM booking_passengers
                    WHERE group_id = ?
                    ORDER BY passenger_id
                """, (item["booking_id"],)).fetchall()

                item["passengers"] = [dict(p) for p in passengers]
                item["passenger_name"] = ", ".join(
                    p["name"] for p in item["passengers"]
                )
                item["booking_type"] = "family"
                family_bookings.append(item)

        # A unified response for the current frontend.
        all_bookings = legacy_bookings + family_bookings
        all_bookings.sort(
            key=lambda booking: booking["booking_id"],
            reverse=True
        )

        return jsonify({"bookings": all_bookings})

    except sqlite3.Error:
        app.logger.exception("Loading bookings failed")
        return jsonify({"error": "Could not load bookings."}), 500



# ---------------- SYNCHRONIZATION DEMONSTRATION ----------------

@app.get("/api/demo/concurrency")
def concurrency_demo():
    """
    Simulate concurrent booking requests competing for a fixed number
    of seats. A lock protects the shared seat counter.

    This is an isolated simulation and does not modify the real database.
    """
    try:
        attempts = int(request.args.get("attempts", 10))
        initial_seats = int(request.args.get("seats", 5))

        if not 1 <= attempts <= 50:
            return jsonify({
                "error": "Requests must be between 1 and 50."
            }), 400

        if not 0 <= initial_seats <= 50:
            return jsonify({
                "error": "Seats must be between 0 and 50."
            }), 400

    except (ValueError, TypeError):
        return jsonify({
            "error": "Requests and seats must be whole numbers."
        }), 400

    # Shared state accessed by all worker threads.
    state = {"seats": initial_seats}
    lock = Lock()
    start_barrier = Barrier(attempts)
    results = []

    def attempt_booking(request_number):
        # Make requests start together to demonstrate contention.
        start_barrier.wait()

        # CRITICAL SECTION:
        # Only one thread can check and update seats at a time.
        with lock:
            seats_before = state["seats"]

            if seats_before > 0:
                state["seats"] -= 1
                result_status = "SUCCESS"
            else:
                result_status = "REJECTED"

            # Record the result while still holding the lock.
            # This preserves the actual order in which requests
            # access the shared seat counter.
            results.append({
                "request": request_number,
                "result": result_status,
                "seats_before": seats_before,
                "remaining_seats": state["seats"],
                "execution_order": len(results) + 1
            })

    try:
        with ThreadPoolExecutor(max_workers=attempts) as executor:
            futures = [
                executor.submit(attempt_booking, number)
                for number in range(1, attempts + 1)
            ]

            # Surface any unexpected worker errors.
            for future in futures:
                future.result()

    except Exception:
        app.logger.exception("Synchronization demo failed")
        return jsonify({
            "error": "The synchronization simulation failed."
        }), 500

    successful = sum(
        result["result"] == "SUCCESS"
        for result in results
    )
    rejected = sum(
        result["result"] == "REJECTED"
        for result in results
    )

    return jsonify({
        "demo": "Thread synchronization using a lock",
        "initial_seats": initial_seats,
        "total_requests": attempts,
        "successful_bookings": successful,
        "rejected_requests": rejected,
        "remaining_seats": state["seats"],
        "real_database_changed": False,
        "results": results
    }), 200



if __name__ == "__main__":
    initialize_database()
    print("Database being used:", DATABASE)
    app.run(host="127.0.0.1", port=5000, debug=True)
