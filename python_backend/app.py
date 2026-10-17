
from pathlib import Path
import sqlite3
from threading import Lock, Barrier
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from recommendation import calculate_recommendations

app = Flask(__name__)
CORS(app)

DATABASE = Path(__file__).resolve().parent / "railway_users.db"


def get_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
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
                seats INTEGER NOT NULL DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                passenger_name TEXT NOT NULL,
                train_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Confirmed',
                FOREIGN KEY (train_id) REFERENCES trains(id)
            )
        """)

        # Stores every passenger in a single-person or family booking.
        # Existing bookings are preserved.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS booking_passengers (
                passenger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                age INTEGER NOT NULL CHECK (age BETWEEN 0 AND 120),
                gender TEXT NOT NULL,
                FOREIGN KEY (booking_id)
                    REFERENCES bookings(booking_id)
                    ON DELETE CASCADE
            )
        """)

        count = conn.execute(
            "SELECT COUNT(*) FROM trains"
        ).fetchone()[0]

        if count == 0:
            sample_trains = [
                (1, "12001", "Shatabdi Express", "Delhi", "Dehradun",
                 650, 360, "06:45", 45),
                (2, "12017", "Dehradun Shatabdi", "Delhi", "Dehradun",
                 720, 345, "07:00", 30),
                (3, "14041", "Mussoorie Express", "Delhi", "Dehradun",
                 350, 480, "22:25", 60),
                (4, "14631", "Uttar Sampark Kranti", "Delhi", "Dehradun",
                 420, 420, "15:20", 25),
                (5, "12002", "Shatabdi Express", "Dehradun", "Delhi",
                 650, 360, "17:00", 40),
                (6, "14042", "Mussoorie Express", "Dehradun", "Delhi",
                 350, 480, "21:10", 55),
            ]

            conn.executemany("""
                INSERT INTO trains
                (id, number, name, source, destination, fare,
                 duration_minutes, departure_time, seats)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, sample_trains)

        conn.commit()


# ---------------- HOME ----------------

@app.get("/")
def home():
    return jsonify({
        "message": "Railway Reservation backend is running",
        "features": [
            "User signup and login",
            "Train search",
            "Weighted recommendations",
            "Single and family bookings",
            "Passenger name, age and gender",
            "Atomic seat reservation",
            "OS synchronization demonstration",
            "Booking history"
        ],
        "endpoints": {
            "signup": "POST /api/signup",
            "login": "POST /api/login",
            "search_trains": "GET /api/trains",
            "create_booking": "POST /api/bookings",
            "booking_history": "GET /api/bookings",
            "concurrency_demo": "GET /api/demo/concurrency"
        }
    })


# ---------------- AUTHENTICATION ----------------

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
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (?, ?, ?)
                """,
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
                """
                SELECT id, name, email, password_hash
                FROM users
                WHERE email = ? COLLATE NOCASE
                """,
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
            raise ValueError

        weights = {
            "price": float(request.args.get("price_weight", 5)),
            "duration": float(request.args.get("duration_weight", 4)),
            "availability": float(
                request.args.get("availability_weight", 3)
            ),
            "timing": float(request.args.get("timing_weight", 2)),
        }

        if any(
            not 1 <= value <= 5
            for value in weights.values()
        ):
            raise ValueError

        with get_connection() as conn:
            rows = conn.execute("""
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

        eligible = [dict(train) for train in rows]
        preferred_time = (
            request.args.get("preferred_time", "").strip() or None
        )

        recommended = calculate_recommendations(
            eligible,
            weights,
            preferred_time
        )

        return jsonify({
            "count": len(recommended),
            "trains": recommended
        })

    except (ValueError, TypeError):
        return jsonify({
            "error": "Please check your budget, weights and preferred time."
        }), 400

    except sqlite3.Error:
        app.logger.exception("Train search database error")
        return jsonify({"error": "Could not search trains."}), 500


# ---------------- SINGLE / FAMILY BOOKINGS ----------------

@app.post("/api/bookings")
def create_booking():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Send booking details as JSON."
        }), 400

    train_id = data.get("train_id")

    if (
        isinstance(train_id, bool)
        or not isinstance(train_id, int)
    ):
        return jsonify({
            "error": "Train ID must be an integer."
        }), 400

    # New format: passengers is a list of passenger objects.
    passengers = data.get("passengers")

    # Backward compatibility with the old frontend.
    if passengers is None and "passenger_name" in data:
        passengers = [{
            "name": data.get("passenger_name"),
            "age": data.get("age", 20),
            "gender": data.get("gender", "Prefer not to say")
        }]

    if (
        not isinstance(passengers, list)
        or not 1 <= len(passengers) <= 10
    ):
        return jsonify({
            "error": "Enter details for 1 to 10 passengers."
        }), 400

    allowed_genders = {
        "Male",
        "Female",
        "Other",
        "Prefer not to say"
    }

    validated_passengers = []

    for index, passenger in enumerate(passengers, start=1):
        if not isinstance(passenger, dict):
            return jsonify({
                "error": f"Passenger {index} details are invalid."
            }), 400

        name = passenger.get("name")
        age = passenger.get("age")
        gender = passenger.get("gender")

        if not isinstance(name, str) or not name.strip():
            return jsonify({
                "error": f"Enter the name of passenger {index}."
            }), 400

        if (
            isinstance(age, bool)
            or not isinstance(age, int)
            or not 0 <= age <= 120
        ):
            return jsonify({
                "error": f"Passenger {index} age must be between 0 and 120."
            }), 400

        if not isinstance(gender, str) or gender not in allowed_genders:
            return jsonify({
                "error": f"Select a valid gender for passenger {index}."
            }), 400

        validated_passengers.append({
            "name": name.strip(),
            "age": age,
            "gender": gender
        })

    passenger_count = len(validated_passengers)

    try:
        # BEGIN IMMEDIATE obtains SQLite's write reservation before
        # checking seats. Competing booking transactions must wait.
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")

            train = conn.execute(
                """
                SELECT id, number, name, fare, seats
                FROM trains
                WHERE id = ?
                """,
                (train_id,)
            ).fetchone()

            if train is None:
                conn.rollback()
                return jsonify({"error": "Train not found."}), 404

            if train["seats"] < passenger_count:
                available = train["seats"]
                conn.rollback()

                return jsonify({
                    "error": "Not enough seats for all passengers.",
                    "requested_seats": passenger_count,
                    "available_seats": available
                }), 409

            # Atomic conditional update: never reduce seats below zero.
            update = conn.execute(
                """
                UPDATE trains
                SET seats = seats - ?
                WHERE id = ? AND seats >= ?
                """,
                (passenger_count, train_id, passenger_count)
            )

            if update.rowcount != 1:
                conn.rollback()
                return jsonify({
                    "error": "Seats are no longer available. Please search again."
                }), 409

            # One booking record represents the entire group.
            cursor = conn.execute(
                """
                INSERT INTO bookings (passenger_name, train_id, status)
                VALUES (?, ?, 'Confirmed')
                """,
                (validated_passengers[0]["name"], train_id)
            )

            booking_id = cursor.lastrowid

            # Store every passenger against the group booking.
            conn.executemany(
                """
                INSERT INTO booking_passengers
                    (booking_id, name, age, gender)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        booking_id,
                        passenger["name"],
                        passenger["age"],
                        passenger["gender"]
                    )
                    for passenger in validated_passengers
                ]
            )

            conn.commit()

            remaining_seats = train["seats"] - passenger_count
            total_fare = train["fare"] * passenger_count

        return jsonify({
            "message": "Booking successful!",
            "booking": {
                "booking_id": booking_id,
                "train_id": train_id,
                "train_number": train["number"],
                "train_name": train["name"],
                "passenger_count": passenger_count,
                "passengers": validated_passengers,
                "fare_per_passenger": train["fare"],
                "total_fare": total_fare,
                "status": "Confirmed"
            },
            "seats_remaining": remaining_seats
        }), 201

    except sqlite3.Error:
        app.logger.exception("Booking database error")
        return jsonify({
            "error": "Could not complete booking. Please try again."
        }), 500


# ---------------- BOOKING HISTORY ----------------

@app.get("/api/bookings")
def get_bookings():
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    b.booking_id,
                    b.status,
                    b.passenger_name,
                    b.train_id,
                    t.number AS train_number,
                    t.name AS train_name,
                    t.source,
                    t.destination,
                    t.fare
                FROM bookings b
                JOIN trains t ON t.id = b.train_id
                ORDER BY b.booking_id DESC
            """).fetchall()

            result = []

            for row in rows:
                booking = dict(row)

                passenger_rows = conn.execute("""
                    SELECT name, age, gender
                    FROM booking_passengers
                    WHERE booking_id = ?
                    ORDER BY passenger_id
                """, (booking["booking_id"],)).fetchall()

                booking["passengers"] = [
                    dict(passenger) for passenger in passenger_rows
                ]

                booking["passenger_count"] = len(passenger_rows)
                booking["total_fare"] = (
                    booking["fare"] * booking["passenger_count"]
                )

                result.append(booking)

        return jsonify({
            "count": len(result),
            "bookings": result
        })

    except sqlite3.Error:
        app.logger.exception("Loading bookings failed")
        return jsonify({
            "error": "Could not load bookings."
        }), 500


# ---------------- OS SYNCHRONIZATION DEMO ----------------

@app.get("/api/demo/concurrency")
def concurrency_demo():
    try:
        attempts = int(request.args.get("attempts", 10))
        initial_seats = int(request.args.get("seats", 5))
    except ValueError:
        return jsonify({
            "error": "Attempts and seats must be integers."
        }), 400

    if not 1 <= attempts <= 50 or not 0 <= initial_seats <= 50:
        return jsonify({
            "error": "Use 1-50 attempts and 0-50 seats."
        }), 400

    # Independent demo state: real train seats are untouched.
    state = {"seats": initial_seats}
    demo_lock = Lock()
    start_together = Barrier(attempts)
    results = []

    def simulated_request(request_id):
        # Make worker threads wait until they can start together.
        start_together.wait()

        # CRITICAL SECTION: shared seat check and decrement.
        with demo_lock:
            if state["seats"] > 0:
                state["seats"] -= 1
                status = "SUCCESS"
            else:
                status = "REJECTED"

            results.append({
                "request_id": request_id,
                "status": status,
                "seats_remaining": state["seats"]
            })

    try:
        with ThreadPoolExecutor(max_workers=attempts) as executor:
            futures = [
                executor.submit(simulated_request, request_id)
                for request_id in range(1, attempts + 1)
            ]

            for future in futures:
                future.result()

    except Exception:
        app.logger.exception("Concurrency demo failed")
        return jsonify({
            "error": "The concurrency simulation failed."
        }), 500

    results.sort(key=lambda item: item["request_id"])

    successful = sum(
        result["status"] == "SUCCESS"
        for result in results
    )

    return jsonify({
        "message": "Concurrent booking simulation completed.",
        "attempts": attempts,
        "initial_seats": initial_seats,
        "successful_bookings": successful,
        "rejected_requests": attempts - successful,
        "seats_remaining": state["seats"],
        "synchronization": (
            "A threading.Lock protects the shared seat counter."
        ),
        "results": results
    })


if __name__ == "__main__":
    initialize_database()
    print("Database being used:", DATABASE)
    app.run(host="127.0.0.1", port=5000, debug=True)
