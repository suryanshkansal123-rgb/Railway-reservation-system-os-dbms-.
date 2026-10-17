
from pathlib import Path
import sqlite3

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from recommendation import calculate_recommendations

app = Flask(__name__)
CORS(app)

DATABASE = Path(__file__).resolve().parent / "railway_users.db"


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
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

        # Add sample trains only when the train table is empty.
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
        return jsonify({"error": "Name, email and password are required."}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must contain at least 6 characters."}), 400

    try:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password))
            )
            conn.commit()

        return jsonify({
            "message": "Signup successful! You can now log in.",
            "user": {"id": cursor.lastrowid, "name": name, "email": email}
        }), 201

    except sqlite3.IntegrityError:
        return jsonify({"error": "This email already exists. Please log in instead."}), 409
    except sqlite3.Error:
        app.logger.exception("Signup database error")
        return jsonify({"error": "Database error during signup."}), 500


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if not email or not isinstance(password, str) or not password:
        return jsonify({"error": "Please enter your email and password."}), 400

    try:
        with get_connection() as conn:
            user = conn.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = ? COLLATE NOCASE",
                (email,)
            ).fetchone()
    except sqlite3.Error:
        app.logger.exception("Login database error")
        return jsonify({"error": "Database error during login."}), 500

    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password."}), 401

    return jsonify({
        "message": "Login successful!",
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]}
    })


# ---------------- TRAIN SEARCH ----------------

@app.get("/api/trains")
def search_trains():
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()

    try:
        budget = request.args.get("budget", "").strip()
        budget = float(budget) if budget else None

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
        preferred_time = request.args.get("preferred_time", "").strip() or None

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


# ---------------- BOOKINGS ----------------

@app.post("/api/bookings")
def create_booking():
    data = request.get_json(silent=True) or {}
    passenger_name = str(data.get("passenger_name", "")).strip()
    train_id = data.get("train_id")

    if not passenger_name or train_id is None:
        return jsonify({
            "error": "Passenger name and train ID are required."
        }), 400

    try:
        with get_connection() as conn:
            train = conn.execute(
                "SELECT id, seats FROM trains WHERE id = ?",
                (train_id,)
            ).fetchone()

            if train is None:
                return jsonify({"error": "Train not found."}), 404

            if train["seats"] <= 0:
                return jsonify({"error": "No seats available on this train."}), 409

            cursor = conn.execute("""
                INSERT INTO bookings (passenger_name, train_id)
                VALUES (?, ?)
            """, (passenger_name, train_id))

            conn.execute(
                "UPDATE trains SET seats = seats - 1 WHERE id = ?",
                (train_id,)
            )
            conn.commit()

            booking_id = cursor.lastrowid

        return jsonify({
            "message": "Booking successful!",
            "booking_id": booking_id
        }), 201

    except (sqlite3.Error, ValueError):
        app.logger.exception("Booking database error")
        return jsonify({"error": "Could not complete booking."}), 500


@app.get("/api/bookings")
def get_bookings():
    try:
        with get_connection() as conn:
            rows = conn.execute("""
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

        return jsonify({"bookings": [dict(row) for row in rows]})

    except sqlite3.Error:
        app.logger.exception("Loading bookings failed")
        return jsonify({"error": "Could not load bookings."}), 500


if __name__ == "__main__":
    initialize_database()
    print("Database being used:", DATABASE)
    app.run(host="127.0.0.1", port=5000, debug=True)
