
from pathlib import Path
import os
import calendar
import math
import sqlite3
import secrets
import socket
from datetime import date as date_type, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from contextlib import ExitStack, contextmanager
from itertools import permutations

from flask import Flask, jsonify, request
from flask_cors import CORS
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash

from recommendation import calculate_recommendations


def six_month_booking_limit(today=None):
    """Return the calendar date exactly six months after today, clamping month-end days."""
    today = today or date_type.today()
    month_index = today.month - 1 + 6
    year = today.year + month_index // 12
    month = month_index % 12 + 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date_type(year, month, day)


app = Flask(__name__)


@app.before_request
def enforce_six_month_booking_window_globally():
    """Central hard stop for every public journey-date operation."""
    if request.path == "/api/trains":
        candidate = request.args.get("journey_date", "").strip()
    elif request.path.startswith("/api/trains/") and request.path.endswith("/seats"):
        candidate = request.args.get("journey_date", "").strip()
    elif request.path == "/api/bookings" and request.method == "POST":
        payload = request.get_json(silent=True) or {}
        candidate = str(payload.get("journey_date", "")).strip()
    else:
        return None

    if not candidate:
        return None
    try:
        requested = date_type.fromisoformat(candidate)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid journey date. Use YYYY-MM-DD."}), 400

    today = date_type.today()
    last_allowed = six_month_booking_limit(today)
    if requested < today or requested > last_allowed:
        return jsonify({
            "error": (
                f"Booking is allowed only from {today.isoformat()} "
                f"through {last_allowed.isoformat()} (maximum six months ahead)."
            ),
            "booking_window_start": today.isoformat(),
            "booking_window_end": last_allowed.isoformat(),
        }), 400
    return None

# Development-only CORS: frontend can be opened from the laptop or a phone
# using the laptop's current LAN/hotspot IP. Do not use this open policy in production.
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Seat-specific synchronization: requests for the same train/date/seat wait
# for one another, while different seats use different locks. SQLite transactions
# below still provide database-level write coordination and cross-process safety.
_seat_lock_registry = {}
_seat_lock_registry_guard = Lock()


@contextmanager
def lock_selected_seats(train_id, journey_date, seat_numbers):
    """Acquire deterministic per-seat locks for one booking operation."""
    keys = sorted({(int(train_id), str(journey_date), str(number)) for number in seat_numbers})
    with _seat_lock_registry_guard:
        locks = [
            _seat_lock_registry.setdefault(key, Lock())
            for key in keys
        ]
    with ExitStack() as stack:
        for lock in locks:
            stack.enter_context(lock)
        yield

DATABASE = Path(__file__).resolve().parent / "railway_users.db"

SECRET_KEY = os.environ.get(
    "RAILWAY_SECRET_KEY",
    "development-only-change-this-secret-before-deployment",
)

TOKEN_SALT = "railway-login-token-v1"
TOKEN_MAX_AGE = 60 * 60 * 24 * 7
MAX_PASSENGERS = 10

VALID_GENDERS = {
    "Male",
    "Female",
    "Other",
    "Prefer not to say",
}

serializer = URLSafeTimedSerializer(SECRET_KEY, salt=TOKEN_SALT)


# --------------------------------------------------
# ORIGINAL SAMPLE TRAINS
# --------------------------------------------------

SAMPLE_TRAINS = [
    (1, "12001", "Shatabdi Express (Demo)", "Delhi", "Dehradun", 650, 360, "06:45", 45),
    (2, "12017", "Dehradun Shatabdi (Demo)", "Delhi", "Dehradun", 720, 345, "07:00", 30),
    (3, "14041", "Mussoorie Express (Demo)", "Delhi", "Dehradun", 350, 480, "22:25", 60),
    (4, "14631", "Uttar Sampark Kranti (Demo)", "Delhi", "Dehradun", 420, 420, "15:20", 25),
    (5, "12002", "Shatabdi Express (Demo)", "Dehradun", "Delhi", 650, 360, "17:00", 40),
    (6, "14042", "Mussoorie Express (Demo)", "Dehradun", "Delhi", 350, 480, "21:10", 55),
    (7, "D001", "Doon Intercity (Demo)", "Dehradun", "Haridwar", 180, 90, "08:15", 50),
    (8, "D002", "Doon Intercity (Demo)", "Haridwar", "Dehradun", 180, 95, "18:10", 48),
    (9, "D003", "Ganga Express (Demo)", "Haridwar", "Delhi", 390, 300, "07:30", 55),
    (10, "D004", "Ganga Express (Demo)", "Delhi", "Haridwar", 390, 305, "16:20", 52),
    (11, "D005", "Pink City Express (Demo)", "Delhi", "Jaipur", 480, 300, "06:10", 40),
    (12, "D006", "Pink City Express (Demo)", "Jaipur", "Delhi", 480, 305, "17:40", 42),
    (13, "D007", "Taj Intercity (Demo)", "Delhi", "Agra", 320, 135, "08:00", 65),
    (14, "D008", "Taj Intercity (Demo)", "Agra", "Delhi", 320, 140, "18:00", 60),
    (15, "D009", "Awadh Express (Demo)", "Delhi", "Lucknow", 550, 420, "20:15", 70),
    (16, "D010", "Awadh Express (Demo)", "Lucknow", "Delhi", 550, 425, "19:30", 68),
    (17, "D011", "Chandigarh Express (Demo)", "Delhi", "Chandigarh", 420, 210, "07:20", 45),
    (18, "D012", "Chandigarh Express (Demo)", "Chandigarh", "Delhi", 420, 215, "17:15", 43),
    (19, "D013", "Amritsar Mail (Demo)", "Delhi", "Amritsar", 600, 480, "19:00", 50),
    (20, "D014", "Amritsar Mail (Demo)", "Amritsar", "Delhi", 600, 485, "18:45", 47),
    (21, "D015", "Lake City Express (Demo)", "Jaipur", "Agra", 350, 240, "09:30", 35),
    (22, "D016", "Lake City Express (Demo)", "Agra", "Jaipur", 350, 245, "15:00", 38),
    (23, "D017", "Ganga Doon Link (Demo)", "Haridwar", "Lucknow", 500, 390, "06:40", 30),
    (24, "D018", "Ganga Doon Link (Demo)", "Lucknow", "Haridwar", 500, 395, "17:50", 32),
    (25, "D019", "Himalayan Connector (Demo)", "Dehradun", "Chandigarh", 430, 270, "07:45", 28),
    (26, "D020", "Himalayan Connector (Demo)", "Chandigarh", "Dehradun", 430, 275, "16:40", 29),
    (27, "D021", "Western Gateway Demo", "Delhi", "Mumbai", 1250, 960, "16:00", 35),
    (28, "D022", "Western Gateway Demo", "Mumbai", "Delhi", 1250, 970, "17:30", 33),
    (29, "D023", "Deccan Link Demo", "Mumbai", "Pune", 350, 210, "08:10", 42),
    (30, "D024", "Deccan Link Demo", "Pune", "Mumbai", 350, 215, "18:15", 40),
    (31, "D025", "Sabarmati Demo Express", "Delhi", "Ahmedabad", 950, 780, "19:20", 32),
    (32, "D026", "Sabarmati Demo Express", "Ahmedabad", "Delhi", 950, 790, "18:50", 30),
    (33, "D027", "Central India Demo", "Bhopal", "Indore", 280, 240, "07:40", 36),
    (34, "D028", "Central India Demo", "Indore", "Bhopal", 280, 245, "17:00", 34),
    (35, "D029", "Eastern Mail Demo", "Kolkata", "Varanasi", 620, 600, "20:10", 38),
    (36, "D030", "Eastern Mail Demo", "Varanasi", "Kolkata", 620, 610, "19:15", 35),
    (37, "D031", "Prayag Connector Demo", "Lucknow", "Prayagraj", 280, 210, "08:40", 40),
    (38, "D032", "Prayag Connector Demo", "Prayagraj", "Lucknow", 280, 215, "17:50", 38),
    (39, "D033", "Rishikesh Valley Demo", "Dehradun", "Rishikesh", 100, 75, "09:15", 35),
    (40, "D034", "Rishikesh Valley Demo", "Rishikesh", "Dehradun", 100, 80, "16:30", 33),
    (41, "D035", "Bareilly Connector Demo", "Delhi", "Bareilly", 320, 270, "10:00", 35),
    (42, "D036", "Bareilly Connector Demo", "Bareilly", "Delhi", 320, 275, "18:20", 32),
    (43, "D037", "Punjab City Demo", "Delhi", "Ludhiana", 400, 300, "09:00", 40),
    (44, "D038", "Punjab City Demo", "Ludhiana", "Delhi", 400, 305, "17:10", 37),
]


# --------------------------------------------------
# EXPANDED DEMO ROUTES
# Three options for every city pair in both directions
# --------------------------------------------------

MORE_CITIES = [
    "Delhi",
    "Dehradun",
    "Haridwar",
    "Rishikesh",
    "Chandigarh",
    "Jaipur",
    "Agra",
    "Lucknow",
    "Prayagraj",
    "Varanasi",
    "Bareilly",
    "Ludhiana",
    "Amritsar",
    "Mumbai",
    "Pune",
    "Ahmedabad",
    "Bhopal",
    "Indore",
    "Kolkata",
    "Patna",
    "Ranchi",
    "Bengaluru",
    "Chennai",
    "Hyderabad",
    "Visakhapatnam",
    "Bhubaneswar",
    "Nagpur",
    "Surat",
    "Jodhpur",
    "Udaipur",
]

DEMO_VARIANTS = [
    {
        "name": "Express",
        "fare_factor": 1.00,
        "duration_factor": 1.00,
        "departure": "06:30",
        "seats": 45,
    },
    {
        "name": "Superfast",
        "fare_factor": 1.35,
        "duration_factor": 0.82,
        "departure": "12:15",
        "seats": 30,
    },
    {
        "name": "Intercity",
        "fare_factor": 0.75,
        "duration_factor": 1.15,
        "departure": "18:40",
        "seats": 60,
    },
]


def generate_more_demo_trains():
    generated = []
    train_id = 1000

    for route_number, (source, destination) in enumerate(
        permutations(MORE_CITIES, 2), start=1
    ):
        # Reproducible demo values for each route.
        base_fare = 150 + (route_number * 37) % 1000
        base_duration = 90 + (route_number * 29) % 900

        for variant in DEMO_VARIANTS:
            fare = round(base_fare * variant["fare_factor"], 2)
            duration = max(
                30,
                int(base_duration * variant["duration_factor"]),
            )

            generated.append((
                train_id,
                f"DM{train_id}",
                f"{source}-{destination} {variant['name']} (Demo)",
                source,
                destination,
                fare,
                duration,
                variant["departure"],
                variant["seats"],
            ))

            train_id += 1

    return generated


SAMPLE_TRAINS.extend(generate_more_demo_trains())


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_connection():
    conn = sqlite3.connect(DATABASE, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def utc_now():
    return datetime.now(timezone.utc)


def cleanup_expired_holds(conn):
    """Expire unpaid reservations and return their temporarily held seats."""
    now_text = utc_now().isoformat(timespec="seconds")
    expired = conn.execute("""
        SELECT group_id, train_id, passenger_count
        FROM booking_groups
        WHERE status = 'Pending Payment'
          AND payment_status = 'Pending'
          AND hold_expires_at IS NOT NULL
          AND hold_expires_at <= ?
    """, (now_text,)).fetchall()

    for hold in expired:
        conn.execute("""
            UPDATE train_seats
            SET status = 'Available', booking_group_id = NULL, lock_expires_at = NULL
            WHERE booking_group_id = ? AND status = 'Locked'
        """, (hold["group_id"],))
        conn.execute("""
            UPDATE trains
            SET seats = seats + ?
            WHERE id = ?
        """, (hold["passenger_count"], hold["train_id"]))
        used = conn.execute("SELECT user_id, wallet_used FROM booking_groups WHERE group_id = ?", (hold["group_id"],)).fetchone()
        if used and float(used["wallet_used"] or 0) > 0:
            conn.execute("INSERT OR IGNORE INTO wallet_accounts (user_id, balance) VALUES (?, 0)", (used["user_id"],))
            conn.execute("UPDATE wallet_accounts SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", (used["wallet_used"], used["user_id"]))
            conn.execute("INSERT INTO wallet_transactions (user_id, booking_id, transaction_type, amount, description) VALUES (?, ?, 'CREDIT', ?, ?)", (used["user_id"], hold["group_id"], used["wallet_used"], f"Wallet restored after expired booking #{hold['group_id']}"))
        conn.execute("""
            UPDATE booking_groups
            SET status = 'Expired', payment_status = 'Expired'
            WHERE group_id = ? AND status = 'Pending Payment'
              AND payment_status = 'Pending'
        """, (hold["group_id"],))


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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                passenger_name TEXT NOT NULL,
                train_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Confirmed',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (train_id) REFERENCES trains(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS booking_groups (
                group_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                train_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Confirmed',
                passenger_count INTEGER NOT NULL,
                total_fare REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                journey_date TEXT,
                priority_level TEXT NOT NULL DEFAULT 'Medium',
                payment_status TEXT NOT NULL DEFAULT 'Pending',
                hold_expires_at TEXT,
                payment_token TEXT UNIQUE,
                FOREIGN KEY (user_id) REFERENCES users(id),
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
                seat_number TEXT,
                FOREIGN KEY (group_id)
                    REFERENCES booking_groups(group_id)
                    ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                payment_status TEXT NOT NULL,
                payment_reference TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (booking_id)
                    REFERENCES booking_groups(group_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_accounts (
                user_id INTEGER PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                booking_id INTEGER,
                transaction_type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (booking_id) REFERENCES booking_groups(group_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS train_seats (
                seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                train_id INTEGER NOT NULL,
                journey_date TEXT NOT NULL,
                seat_number TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Available'
                    CHECK(status IN ('Available','Locked','Booked')),
                booking_group_id INTEGER,
                lock_expires_at TEXT,
                UNIQUE(train_id, journey_date, seat_number),
                FOREIGN KEY (train_id) REFERENCES trains(id),
                FOREIGN KEY (booking_group_id) REFERENCES booking_groups(group_id)
            )
        """)

        group_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(booking_groups)"
            ).fetchall()
        }

        if "priority_level" not in group_columns:
            conn.execute(
                "ALTER TABLE booking_groups ADD COLUMN priority_level TEXT NOT NULL DEFAULT 'Medium'"
            )

        if "payment_status" not in group_columns:
            conn.execute(
                "ALTER TABLE booking_groups ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'Paid'"
            )

        if "hold_expires_at" not in group_columns:
            conn.execute(
                "ALTER TABLE booking_groups ADD COLUMN hold_expires_at TEXT"
            )
        if "payment_token" not in group_columns:
            conn.execute("ALTER TABLE booking_groups ADD COLUMN payment_token TEXT")

        if "refund_amount" not in group_columns:
            conn.execute("ALTER TABLE booking_groups ADD COLUMN refund_amount REAL NOT NULL DEFAULT 0")
        if "cancelled_at" not in group_columns:
            conn.execute("ALTER TABLE booking_groups ADD COLUMN cancelled_at TEXT")
        if "wallet_used" not in group_columns:
            conn.execute("ALTER TABLE booking_groups ADD COLUMN wallet_used REAL NOT NULL DEFAULT 0")
        if "amount_due" not in group_columns:
            conn.execute("ALTER TABLE booking_groups ADD COLUMN amount_due REAL NOT NULL DEFAULT 0")
        conn.execute("UPDATE booking_groups SET amount_due = total_fare WHERE amount_due = 0 AND payment_status IN ('Pending','Successful','Paid')")

        passenger_columns = {row["name"] for row in conn.execute("PRAGMA table_info(booking_passengers)").fetchall()}
        if "seat_number" not in passenger_columns:
            conn.execute("ALTER TABLE booking_passengers ADD COLUMN seat_number TEXT")

        if "journey_date" not in group_columns:
            conn.execute(
                "ALTER TABLE booking_groups ADD COLUMN journey_date TEXT"
            )
            conn.execute("""
                UPDATE booking_groups
                SET journey_date = substr(created_at, 1, 10)
                WHERE journey_date IS NULL OR journey_date = ''
            """)

        # Adds new train IDs but does not overwrite existing seat counts.
        conn.executemany("""
            INSERT OR IGNORE INTO trains (
                id, number, name, source, destination, fare,
                duration_minutes, departure_time, seats
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, SAMPLE_TRAINS)

        conn.execute("""
            INSERT OR IGNORE INTO schema_meta(key, value)
            VALUES ('account_bookings_v2', 'non_destructive')
        """)

        conn.commit()


# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

def issue_token(user):
    return serializer.dumps({
        "user_id": int(user["id"]),
        "email": user["email"],
    })


def require_user():
    header = request.headers.get("Authorization", "")

    if not header.startswith("Bearer "):
        return None

    token = header[7:].strip()

    if not token:
        return None

    try:
        payload = serializer.loads(token, max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None

    user_id = payload.get("user_id")

    if not isinstance(user_id, int):
        return None

    with get_connection() as conn:
        user = conn.execute("""
            SELECT id, name, email
            FROM users
            WHERE id = ?
        """, (user_id,)).fetchone()

    return dict(user) if user else None


def auth_error():
    return jsonify({
        "error": "Please log in again to continue."
    }), 401


@app.get("/")
def home():
    return jsonify({
        "message": "Railway Reservation backend is running",
        "demo_data": True,
    })


@app.post("/api/signup")
def signup():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if (
        not name
        or len(name) > 100
        or not email
        or len(email) > 254
        or not isinstance(password, str)
    ):
        return jsonify({
            "error": "Enter a valid name, email and password."
        }), 400

    if len(password) < 6 or len(password) > 1024:
        return jsonify({
            "error": "Password must contain 6 to 1024 characters."
        }), 400

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return jsonify({
            "error": "Enter a valid email address."
        }), 400

    try:
        with get_connection() as conn:
            cur = conn.execute("""
                INSERT INTO users(name, email, password_hash)
                VALUES (?, ?, ?)
            """, (
                name,
                email,
                generate_password_hash(password),
            ))

            conn.commit()

            user = {
                "id": cur.lastrowid,
                "name": name,
                "email": email,
            }

        return jsonify({
            "message": "Account created successfully. You can now log in.",
            "user": user,
        }), 201

    except sqlite3.IntegrityError:
        return jsonify({
            "error": "This email already exists. Please log in instead."
        }), 409

    except sqlite3.Error:
        app.logger.exception("Signup failed")
        return jsonify({
            "error": "Database error during signup."
        }), 500


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}

    identifier = str(
        data.get("email", data.get("identifier", ""))
    ).strip().lower()

    password = data.get("password", "")

    if not identifier or not isinstance(password, str) or not password:
        return jsonify({
            "error": "Please enter your email and password."
        }), 400

    try:
        with get_connection() as conn:
            user = conn.execute("""
                SELECT id, name, email, password_hash
                FROM users
                WHERE email = ? COLLATE NOCASE
            """, (identifier,)).fetchone()

    except sqlite3.Error:
        app.logger.exception("Login failed")
        return jsonify({
            "error": "Database error during login."
        }), 500

    if user is None or not check_password_hash(
        user["password_hash"], password
    ):
        return jsonify({
            "error": "Invalid email or password."
        }), 401

    public_user = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
    }

    return jsonify({
        "message": "Login successful!",
        "user": public_user,
        "token": issue_token(user),
    })


@app.get("/api/me")
def current_user():
    user = require_user()

    if not user:
        return auth_error()

    return jsonify({"user": user})


# --------------------------------------------------
# CITIES
# --------------------------------------------------

@app.get("/api/cities")
def get_cities():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT source AS city FROM trains
            UNION
            SELECT destination AS city FROM trains
            ORDER BY city COLLATE NOCASE
        """).fetchall()

    return jsonify({
        "cities": [row["city"] for row in rows]
    })


# --------------------------------------------------
# TRAIN SEARCH AND RECOMMENDATIONS
# --------------------------------------------------

@app.get("/api/trains/<int:train_id>/seats")
def get_train_seats(train_id):
    journey_date = request.args.get("journey_date", "").strip()
    try:
        parsed_journey_date = date_type.fromisoformat(journey_date)
        today = date_type.today()
        if parsed_journey_date < today or parsed_journey_date > six_month_booking_limit(today):
            return jsonify({"error": "Journey date must be within the next 6 months."}), 400
    except ValueError:
        return jsonify({"error": "A valid journey_date is required."}), 400

    try:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cleanup_expired_holds(conn)
            train = conn.execute("SELECT id, seats FROM trains WHERE id = ?", (train_id,)).fetchone()
            if not train:
                conn.rollback()
                return jsonify({"error": "Train not found."}), 404

            existing = conn.execute(
                "SELECT COUNT(*) AS n FROM train_seats WHERE train_id = ? AND journey_date = ?",
                (train_id, journey_date)
            ).fetchone()["n"]

            if existing == 0:
                active_count = conn.execute("""
                    SELECT COALESCE(SUM(passenger_count), 0) AS n
                    FROM booking_groups
                    WHERE train_id = ? AND journey_date = ?
                      AND status IN ('Confirmed','Pending Payment')
                """, (train_id, journey_date)).fetchone()["n"]
                capacity = max(int(train["seats"]) + int(active_count), 1)
                for i in range(1, capacity + 1):
                    coach = (i - 1) // 72 + 1
                    berth = (i - 1) % 72 + 1
                    conn.execute("""
                        INSERT OR IGNORE INTO train_seats
                        (train_id, journey_date, seat_number, status)
                        VALUES (?, ?, ?, 'Available')
                    """, (train_id, journey_date, f"S{coach}-{berth}"))

            rows = conn.execute("""
                SELECT seat_number, status
                FROM train_seats
                WHERE train_id = ? AND journey_date = ?
                ORDER BY seat_id
            """, (train_id, journey_date)).fetchall()
            conn.commit()

        counts = {"Available": 0, "Booked": 0, "Locked": 0}
        seats = []
        for row in rows:
            counts[row["status"]] += 1
            seats.append({"seat_number": row["seat_number"], "status": row["status"]})
        return jsonify({"train_id": train_id, "journey_date": journey_date,
                        "seats": seats, "counts": counts})
    except sqlite3.Error:
        app.logger.exception("Seat map could not be loaded")
        return jsonify({"error": "Could not load seat availability."}), 500


@app.get("/api/trains")
def search_trains():
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()

    # Enforce the booking window during train search as well as at booking time.
    journey_date = request.args.get("journey_date", "").strip()
    if journey_date:
        try:
            requested_date = date_type.fromisoformat(journey_date)
        except ValueError:
            return jsonify({"error": "Please select a valid journey date (YYYY-MM-DD)."}), 400
        today = date_type.today()
        if requested_date < today or requested_date > six_month_booking_limit(today):
            return jsonify({"error": f"Journey date must be between {today.isoformat()} and {six_month_booking_limit(today).isoformat()} (maximum 6 months ahead)."}), 400

    try:
        budget_text = request.args.get("budget", "").strip()
        budget = float(budget_text) if budget_text else None

        if budget is not None and (
            not math.isfinite(budget) or budget < 0
        ):
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
            not math.isfinite(value) or not 1 <= value <= 5
            for value in weights.values()
        ):
            raise ValueError

    except (ValueError, TypeError):
        return jsonify({
            "error": "Check your budget and recommendation weights (1–5)."
        }), 400

    try:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cleanup_expired_holds(conn)
            trains = conn.execute("""
                SELECT *
                FROM trains
                WHERE (? = '' OR lower(source) = lower(?))
                  AND (? = '' OR lower(destination) = lower(?))
                  AND (? IS NULL OR fare <= ?)
                ORDER BY departure_time
            """, (
                source,
                source,
                destination,
                destination,
                budget,
                budget,
            )).fetchall()
            conn.commit()

    except sqlite3.Error:
        app.logger.exception("Train search failed")
        return jsonify({
            "error": "Could not search trains."
        }), 500

    preferred_time = (
        request.args.get("preferred_time", "").strip() or None
    )

    try:
        recommended = calculate_recommendations(
            [dict(train) for train in trains],
            weights,
            preferred_time,
        )

    except Exception:
        app.logger.exception("Recommendation calculation failed")
        return jsonify({
            "error": (
                "Could not calculate train recommendations. "
                "Check the Flask terminal."
            )
        }), 500

    return jsonify({"trains": recommended})


# --------------------------------------------------
# SINGLE AND FAMILY BOOKINGS
# --------------------------------------------------

@app.post("/api/bookings")
def create_booking():
    user = require_user()

    if not user:
        return auth_error()

    data = request.get_json(silent=True) or {}

    try:
        train_id = int(data.get("train_id"))
    except (TypeError, ValueError):
        return jsonify({
            "error": "A valid train ID is required."
        }), 400

    raw_passengers = data.get("passengers")

    if raw_passengers is None:
        raw_passengers = [{
            "name": str(data.get("passenger_name", "")).strip(),
            "age": 20,
            "gender": "Prefer not to say",
        }]

    if (
        not isinstance(raw_passengers, list)
        or not 1 <= len(raw_passengers) <= MAX_PASSENGERS
    ):
        return jsonify({
            "error": f"Choose between 1 and {MAX_PASSENGERS} passengers."
        }), 400

    passengers = []

    for index, person in enumerate(raw_passengers, start=1):
        if not isinstance(person, dict):
            return jsonify({
                "error": f"Passenger {index} details are invalid."
            }), 400

        name = str(
            person.get("name", person.get("passenger_name", ""))
        ).strip()

        try:
            age = int(person.get("age", 20))
        except (ValueError, TypeError):
            return jsonify({
                "error": f"Enter a valid age for passenger {index}."
            }), 400

        gender = str(
            person.get("gender", "Prefer not to say")
        ).strip()

        if not 2 <= len(name) <= 100:
            return jsonify({
                "error": f"Enter a valid name for passenger {index}."
            }), 400

        if not 0 <= age <= 120:
            return jsonify({
                "error": f"Passenger {index} age must be 0–120."
            }), 400

        if gender not in VALID_GENDERS:
            return jsonify({
                "error": f"Select a valid gender for passenger {index}."
            }), 400

        passengers.append({
            "name": name,
            "age": age,
            "gender": gender,
        })

    # Priority is intentionally not selected by passengers in the booking UI.
    priority_level = "Medium"

    selected_seats = data.get("selected_seats")
    if not isinstance(selected_seats, list) or len(selected_seats) != len(passengers):
        return jsonify({"error": "Please select exactly one available seat for each passenger."}), 400
    selected_seats = [str(value).strip() for value in selected_seats]
    if len(set(selected_seats)) != len(selected_seats) or any(not value for value in selected_seats):
        return jsonify({"error": "Seat selection is invalid. Please select different seats."}), 400

    journey_date = str(
        data.get("journey_date", date_type.today().isoformat())
    ).strip()

    try:
        parsed_journey_date = date_type.fromisoformat(journey_date)
        today = date_type.today()
        if parsed_journey_date < today or parsed_journey_date > six_month_booking_limit(today):
            return jsonify({"error": "Journey date must be within the next 6 months."}), 400
        journey_date = parsed_journey_date.isoformat()
    except (ValueError, TypeError):
        return jsonify({"error": "Please select a valid journey date (YYYY-MM-DD)."}), 400

    def normalize_person_name(value):
        return " ".join(value.casefold().split())

    seen_people = set()

    for person in passengers:
        person_key = (
            normalize_person_name(person["name"]),
            person["age"],
        )

        if person_key in seen_people:
            return jsonify({
                "error": (
                    f"{person['name']} (age {person['age']}) appears "
                    "more than once in this booking."
                )
            }), 409

        seen_people.add(person_key)

    use_wallet = bool(data.get("use_wallet", False))

    try:
        with lock_selected_seats(train_id, journey_date, selected_seats), get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cleanup_expired_holds(conn)

            existing_people = conn.execute("""
                SELECT p.name, p.age
                FROM booking_passengers AS p
                JOIN booking_groups AS g
                    ON g.group_id = p.group_id
                WHERE g.user_id = ?
                  AND g.journey_date = ?
                  AND g.status = 'Confirmed'
            """, (
                user["id"],
                journey_date,
            )).fetchall()

            already_booked = {
                (
                    normalize_person_name(row["name"]),
                    int(row["age"]),
                )
                for row in existing_people
            }

            duplicates = [
                person for person in passengers
                if (
                    normalize_person_name(person["name"]),
                    person["age"],
                ) in already_booked
            ]

            if duplicates:
                names = ", ".join(sorted({
                    person["name"] for person in duplicates
                }))

                conn.rollback()

                return jsonify({
                    "error": (
                        f"{names} already has a confirmed booking for "
                        f"{journey_date} under this account."
                    )
                }), 409

            train = conn.execute("""
                SELECT *
                FROM trains
                WHERE id = ?
            """, (train_id,)).fetchone()

            if not train:
                conn.rollback()
                return jsonify({"error": "Train not found."}), 404

            passenger_count = len(passengers)

            if train["seats"] < passenger_count:
                available = train["seats"]
                conn.rollback()

                return jsonify({
                    "error": (
                        f"Only {available} seats are available; "
                        f"{passenger_count} required."
                    )
                }), 409

            update = conn.execute("""
                UPDATE trains
                SET seats = seats - ?
                WHERE id = ? AND seats >= ?
            """, (
                passenger_count,
                train_id,
                passenger_count,
            ))

            if update.rowcount != 1:
                conn.rollback()
                return jsonify({
                    "error": "Not enough seats remain. Search again."
                }), 409

            total_fare = round(float(train["fare"]) * passenger_count, 2)
            conn.execute("INSERT OR IGNORE INTO wallet_accounts (user_id, balance) VALUES (?, 0)", (user["id"],))
            wallet_row = conn.execute("SELECT balance FROM wallet_accounts WHERE user_id = ?", (user["id"],)).fetchone()
            wallet_used = min(total_fare, float(wallet_row["balance"] or 0)) if use_wallet else 0.0
            amount_due = round(total_fare - wallet_used, 2)
            if wallet_used > 0:
                debit = conn.execute("UPDATE wallet_accounts SET balance = balance - ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND balance >= ?", (wallet_used, user["id"], wallet_used))
                if debit.rowcount != 1:
                    conn.rollback()
                    return jsonify({"error": "Wallet balance changed. Refresh your wallet and try again."}), 409
            hold_expires_at = (utc_now() + timedelta(minutes=2)).isoformat(timespec="seconds")

            cursor = conn.execute("""
                INSERT INTO booking_groups (
                    user_id, train_id, passenger_count,
                    total_fare, journey_date, priority_level,
                    status, payment_status, hold_expires_at, wallet_used, amount_due
                )
                VALUES (?, ?, ?, ?, ?, ?, 'Pending Payment', 'Pending', ?, ?, ?)
            """, (
                user["id"],
                train_id,
                passenger_count,
                total_fare,
                journey_date,
                priority_level,
                hold_expires_at,
                wallet_used,
                amount_due,
            ))

            group_id = cursor.lastrowid
            payment_token = secrets.token_urlsafe(32)
            conn.execute("UPDATE booking_groups SET payment_token = ? WHERE group_id = ?", (payment_token, group_id))

            # Ensure a date-specific seat map exists before validating passenger choices.
            existing_map_count = conn.execute(
                "SELECT COUNT(*) AS n FROM train_seats WHERE train_id = ? AND journey_date = ?",
                (train_id, journey_date)
            ).fetchone()["n"]
            if existing_map_count == 0:
                capacity = max(int(train["seats"]), passenger_count)
                for i in range(1, capacity + 1):
                    coach = (i - 1) // 72 + 1
                    berth = (i - 1) % 72 + 1
                    conn.execute("""
                        INSERT OR IGNORE INTO train_seats
                        (train_id, journey_date, seat_number, status)
                        VALUES (?, ?, ?, 'Available')
                    """, (train_id, journey_date, f"S{coach}-{berth}"))

            placeholders = ",".join("?" for _ in selected_seats)
            chosen_rows = conn.execute(f"""
                SELECT seat_id, seat_number, status FROM train_seats
                WHERE train_id = ? AND journey_date = ?
                  AND seat_number IN ({placeholders})
            """, [train_id, journey_date, *selected_seats]).fetchall()
            chosen_by_number = {row["seat_number"]: row for row in chosen_rows}
            if len(chosen_by_number) != passenger_count:
                conn.rollback()
                return jsonify({"error": "One or more selected seats do not exist. Refresh the seat map."}), 409
            unavailable = [number for number in selected_seats if chosen_by_number[number]["status"] != "Available"]
            if unavailable:
                conn.rollback()
                return jsonify({"error": "One or more selected seats are currently being booked by another user or have just been booked. Please refresh the seat map and choose different seats."}), 409

            available_seats = [chosen_by_number[number] for number in selected_seats]
            for seat in available_seats:
                changed = conn.execute("""
                    UPDATE train_seats
                    SET status = 'Locked', booking_group_id = ?, lock_expires_at = ?
                    WHERE seat_id = ? AND status = 'Available'
                """, (group_id, hold_expires_at, seat["seat_id"]))
                if changed.rowcount != 1:
                    conn.rollback()
                    return jsonify({"error": "A selected seat is currently being booked by another user or has just been booked. Please refresh the map and choose another seat."}), 409

            conn.executemany("""
                INSERT INTO booking_passengers (
                    group_id, name, age, gender, seat_number
                )
                VALUES (?, ?, ?, ?, ?)
            """, [
                (
                    group_id,
                    person["name"],
                    person["age"],
                    person["gender"],
                )
                for person, seat in zip(passengers, available_seats)
            ] if False else [
                (group_id, person["name"], person["age"], person["gender"], seat["seat_number"])
                for person, seat in zip(passengers, available_seats)
            ])
            if wallet_used > 0:
                conn.execute("INSERT INTO wallet_transactions (user_id, booking_id, transaction_type, amount, description) VALUES (?, ?, 'DEBIT', ?, ?)", (user["id"], group_id, wallet_used, f"Wallet used for booking #{group_id}"))

            conn.commit()

        return jsonify({
            "message": "Seats temporarily reserved. Complete the demo payment to confirm your booking.",
            "booking_id": group_id,
            "passenger_count": passenger_count,
            "passengers": passengers,
            "train_name": train["name"],
            "fare_per_passenger": float(train["fare"]),
            "total_fare": total_fare,
            "wallet_used": wallet_used,
            "amount_due": amount_due,
            "priority_level": priority_level,
            "payment_status": "Pending",
            "hold_expires_at": hold_expires_at,
            "seat_numbers": [seat["seat_number"] for seat in available_seats],
            "payment_window_seconds": 120,
        }), 201

    except sqlite3.Error:
        app.logger.exception("Booking failed")
        return jsonify({
            "error": "Could not complete booking."
        }), 500


# --------------------------------------------------
# SIMULATED PAYMENT
# --------------------------------------------------

@app.post("/api/bookings/<int:booking_id>/cancel-pending")
def cancel_pending_booking(booking_id):
    """Cancel an unpaid booking and immediately release its temporary seat holds."""
    user = require_user()
    if not user:
        return auth_error()
    try:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cleanup_expired_holds(conn)
            booking = conn.execute("""
                SELECT group_id, train_id, passenger_count, wallet_used, status, payment_status
                FROM booking_groups
                WHERE group_id = ? AND user_id = ?
            """, (booking_id, user["id"])).fetchone()
            if not booking:
                conn.rollback()
                return jsonify({"error": "Booking not found."}), 404
            if booking["payment_status"] != "Pending" or booking["status"] != "Pending Payment":
                conn.rollback()
                return jsonify({"error": "This booking is no longer awaiting payment and cannot be cancelled here."}), 409

            conn.execute("""
                UPDATE train_seats
                SET status = 'Available', booking_group_id = NULL, lock_expires_at = NULL
                WHERE booking_group_id = ? AND status = 'Locked'
            """, (booking_id,))
            conn.execute("UPDATE trains SET seats = seats + ? WHERE id = ?", (booking["passenger_count"], booking["train_id"]))
            conn.execute("""
                UPDATE booking_groups
                SET status = 'Cancelled', payment_status = 'Cancelled', hold_expires_at = NULL
                WHERE group_id = ? AND user_id = ?
            """, (booking_id, user["id"]))

            wallet_returned = float(booking["wallet_used"] or 0)
            if wallet_returned > 0:
                conn.execute("INSERT OR IGNORE INTO wallet_accounts (user_id, balance) VALUES (?, 0)", (user["id"],))
                conn.execute("UPDATE wallet_accounts SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", (wallet_returned, user["id"]))
                conn.execute("""
                    INSERT INTO wallet_transactions (user_id, booking_id, transaction_type, amount, description)
                    VALUES (?, ?, 'CREDIT', ?, ?)
                """, (user["id"], booking_id, wallet_returned, f"Wallet restored after cancelling pending booking #{booking_id}"))
            conn.commit()
        return jsonify({
            "message": "Pending booking cancelled. Your temporary seats have been released and wallet funds restored.",
            "booking_id": booking_id,
            "wallet_returned": round(wallet_returned, 2)
        })
    except sqlite3.Error:
        app.logger.exception("Pending booking cancellation failed")
        return jsonify({"error": "Could not cancel the pending booking."}), 500


@app.post("/api/bookings/confirm-payment")
def confirm_payment():
    user = require_user()
    if not user:
        return auth_error()

    data = request.get_json(silent=True) or {}
    try:
        booking_id = int(data.get("booking_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "A valid booking ID is required."}), 400

    method = str(data.get("payment_method", "UPI")).upper()
    outcome = str(data.get("outcome", "success")).lower()
    if method not in {"UPI", "CARD", "CASH", "WALLET"}:
        return jsonify({"error": "Choose UPI, Card, Cash or Wallet payment."}), 400
    if outcome not in {"success", "failure"}:
        return jsonify({"error": "Invalid demo payment outcome."}), 400

    try:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cleanup_expired_holds(conn)
            booking = conn.execute("""
                SELECT group_id, train_id, passenger_count, total_fare, amount_due, wallet_used,
                       status, payment_status, hold_expires_at
                FROM booking_groups
                WHERE group_id = ? AND user_id = ?
            """, (booking_id, user["id"])).fetchone()

            if not booking:
                conn.rollback()
                return jsonify({"error": "Booking not found."}), 404

            if booking["payment_status"] == "Expired" or booking["status"] == "Expired":
                conn.commit()
                return jsonify({"error": "The 2-minute payment window expired. The seat lock has been released; please search and book again."}), 410

            if booking["payment_status"] != "Pending":
                conn.rollback()
                return jsonify({"error": "This booking payment has already been processed."}), 409
            if method == "WALLET" and float(booking["amount_due"] or 0) > 0:
                conn.rollback()
                return jsonify({"error": "Wallet balance does not cover the full fare. Complete the remaining QR payment."}), 400

            if outcome == "success":
                conn.execute("""
                    UPDATE train_seats SET status = 'Booked', lock_expires_at = NULL
                    WHERE booking_group_id = ? AND status = 'Locked'
                """, (booking_id,))
                payment_status = "Successful"
                booking_status = "Confirmed"
                reference = f"DEMO-{booking_id}-{int(__import__('time').time())}"
            else:
                conn.execute("""
                    UPDATE train_seats SET status = 'Available',
                        booking_group_id = NULL, lock_expires_at = NULL
                    WHERE booking_group_id = ? AND status = 'Locked'
                """, (booking_id,))
                payment_status = "Failed"
                booking_status = "Cancelled"
                reference = None

            conn.execute("""
                UPDATE booking_groups
                SET status = ?, payment_status = ?
                WHERE group_id = ? AND user_id = ?
            """, (booking_status, payment_status, booking_id, user["id"]))

            conn.execute("""
                INSERT INTO payments (
                    booking_id, amount, payment_method,
                    payment_status, payment_reference
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                booking_id, booking["amount_due"], method,
                payment_status, reference
            ))

            if outcome == "failure":
                conn.execute("""
                    UPDATE trains
                    SET seats = seats + ?
                    WHERE id = ?
                """, (booking["passenger_count"], booking["train_id"]))
                if float(booking["wallet_used"] or 0) > 0:
                    conn.execute("UPDATE wallet_accounts SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", (booking["wallet_used"], user["id"]))
                    conn.execute("INSERT INTO wallet_transactions (user_id, booking_id, transaction_type, amount, description) VALUES (?, ?, 'CREDIT', ?, ?)", (user["id"], booking_id, booking["wallet_used"], f"Wallet restored after failed payment for booking #{booking_id}"))

            conn.commit()

        return jsonify({
            "message": (
                "Demo payment successful. Booking confirmed."
                if outcome == "success"
                else "Demo payment failed. Reserved seats have been released."
            ),
            "booking_id": booking_id,
            "booking_status": booking_status,
            "payment_status": payment_status,
            "payment_reference": reference,
        })
    except sqlite3.Error:
        app.logger.exception("Payment processing failed")
        return jsonify({"error": "Could not process demo payment."}), 500


# --------------------------------------------------
# PHONE-SCANNED DEMO QR PAYMENT (NO REAL MONEY)
# --------------------------------------------------

@app.get("/api/bookings/<int:booking_id>/demo-qr")
def create_demo_qr(booking_id):
    user = require_user()
    if not user:
        return auth_error()
    with get_connection() as conn:
        row = conn.execute("SELECT payment_token, amount_due, payment_status FROM booking_groups WHERE group_id=? AND user_id=?", (booking_id, user["id"])).fetchone()
    if not row or row["payment_status"] != "Pending":
        return jsonify({"error": "This booking is not awaiting payment."}), 404
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80)); lan_ip = probe.getsockname()[0]; probe.close()
    except OSError:
        lan_ip = request.host.split(":")[0]
    return jsonify({"phone_url": f"http://{lan_ip}:5000/demo-pay/{row['payment_token']}", "amount": row["amount_due"]})


@app.get("/demo-pay/<token>")
def demo_phone_payment_page(token):
    with get_connection() as conn:
        booking = conn.execute("SELECT group_id,amount_due,payment_status FROM booking_groups WHERE payment_token=?", (token,)).fetchone()
    if not booking or booking["payment_status"] != "Pending":
        return "<h2>This demo payment link is invalid, already used, or expired.</h2>", 410
    amount = f"{float(booking['amount_due']):,.2f}"
    return ("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>RailEase Demo Pay</title>"
      "<style>body{font-family:Arial;background:#f2f5fb;padding:24px}main{max-width:420px;margin:8vh auto;background:white;padding:28px;border-radius:18px;box-shadow:0 8px 30px #0001}button{width:100%;padding:15px;border:0;border-radius:10px;background:#1457d9;color:white;font-size:17px}</style></head><body><main>"
      f"<h2>RailEase · Demo UPI</h2><p>Booking #{booking['group_id']}</p><h1>₹{amount}</h1><p>Classroom simulation only. No money will be transferred.</p>"
      f"<button id='approve'>Approve Demo Payment</button><p id='msg'></p></main><script>document.getElementById('approve').onclick=async()=>{{let b=document.getElementById('approve');b.disabled=true;try{{let r=await fetch('/api/demo-pay/{token}',{{method:'POST'}});let d=await r.json();document.getElementById('msg').textContent=d.message||d.error;b.textContent=r.ok?'Payment approved':'Try again';b.disabled=!r.ok;}}catch(e){{document.getElementById('msg').textContent='Cannot reach laptop. Connect both devices to the same Wi-Fi.';b.disabled=false;}}}};</script></body></html>")


@app.post("/api/demo-pay/<token>")
def approve_phone_demo_payment(token):
    try:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE"); cleanup_expired_holds(conn)
            booking = conn.execute("SELECT group_id,amount_due,payment_status FROM booking_groups WHERE payment_token=?", (token,)).fetchone()
            if not booking or booking["payment_status"] != "Pending":
                conn.rollback(); return jsonify({"error": "Payment link is invalid, already used, or expired."}), 410
            conn.execute("UPDATE train_seats SET status='Booked',lock_expires_at=NULL WHERE booking_group_id=? AND status='Locked'", (booking["group_id"],))
            conn.execute("UPDATE booking_groups SET status='Confirmed',payment_status='Successful' WHERE group_id=?", (booking["group_id"],))
            ref = f"PHONE-DEMO-{booking['group_id']}-{int(datetime.now().timestamp())}"
            conn.execute("INSERT INTO payments (booking_id,amount,payment_method,payment_status,payment_reference) VALUES (?,?,'UPI-DEMO-QR','Successful',?)", (booking["group_id"],booking["amount_due"],ref)); conn.commit()
        return jsonify({"message": "Demo payment approved. Return to RailEase; booking will update automatically."})
    except sqlite3.Error:
        app.logger.exception("Phone demo payment failed"); return jsonify({"error": "Could not confirm demo payment."}), 500


@app.get("/api/bookings/<int:booking_id>/payment-status")
def demo_payment_status(booking_id):
    user = require_user()
    if not user: return auth_error()
    with get_connection() as conn:
        row = conn.execute("SELECT status,payment_status FROM booking_groups WHERE group_id=? AND user_id=?", (booking_id,user["id"])).fetchone()
    if not row: return jsonify({"error": "Booking not found."}), 404
    return jsonify({"booking_status": row["status"], "payment_status": row["payment_status"]})


# --------------------------------------------------
# WALLET AND BOOKING CANCELLATION (60% REFUND)
# --------------------------------------------------

@app.get("/api/wallet")
def get_wallet():
    user = require_user()
    if not user:
        return auth_error()
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO wallet_accounts (user_id, balance) VALUES (?, 0)", (user["id"],))
        row = conn.execute("SELECT balance FROM wallet_accounts WHERE user_id = ?", (user["id"],)).fetchone()
        txns = conn.execute("SELECT transaction_id, booking_id, transaction_type, amount, description, created_at FROM wallet_transactions WHERE user_id = ? ORDER BY transaction_id DESC LIMIT 20", (user["id"],)).fetchall()
    return jsonify({"balance": round(float(row["balance"]), 2), "transactions": [dict(x) for x in txns]})


@app.post("/api/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    user = require_user()
    if not user:
        return auth_error()
    try:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cleanup_expired_holds(conn)
            booking = conn.execute("SELECT group_id, train_id, passenger_count, total_fare, status, payment_status, refund_amount FROM booking_groups WHERE group_id = ? AND user_id = ?", (booking_id, user["id"])).fetchone()
            if not booking:
                conn.rollback()
                return jsonify({"error": "Booking not found."}), 404
            if booking["status"] == "Cancelled":
                conn.rollback()
                return jsonify({"error": "This booking has already been cancelled."}), 409
            if booking["status"] != "Confirmed" or booking["payment_status"] not in {"Successful", "Paid"}:
                conn.rollback()
                return jsonify({"error": "Only paid, confirmed bookings can be cancelled."}), 409

            refund = round(float(booking["total_fare"]) * 0.60, 2)
            conn.execute("UPDATE train_seats SET status = 'Available', booking_group_id = NULL, lock_expires_at = NULL WHERE booking_group_id = ? AND status = 'Booked'", (booking_id,))
            conn.execute("UPDATE trains SET seats = seats + ? WHERE id = ?", (booking["passenger_count"], booking["train_id"]))
            conn.execute("UPDATE booking_groups SET status = 'Cancelled', refund_amount = ?, cancelled_at = ? WHERE group_id = ? AND user_id = ?", (refund, utc_now().isoformat(timespec="seconds"), booking_id, user["id"]))
            conn.execute("INSERT OR IGNORE INTO wallet_accounts (user_id, balance) VALUES (?, 0)", (user["id"],))
            conn.execute("UPDATE wallet_accounts SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", (refund, user["id"]))
            conn.execute("INSERT INTO wallet_transactions (user_id, booking_id, transaction_type, amount, description) VALUES (?, ?, 'CREDIT', ?, ?)", (user["id"], booking_id, refund, f"60% cancellation refund for booking #{booking_id}"))
            conn.commit()
        return jsonify({"message": "Booking cancelled. 60% of the fare has been credited to your RailEase wallet.", "booking_id": booking_id, "refund_amount": refund, "wallet_credit": refund})
    except sqlite3.Error:
        app.logger.exception("Booking cancellation failed")
        return jsonify({"error": "Could not cancel this booking."}), 500


# --------------------------------------------------
# ACCOUNT-SPECIFIC BOOKING HISTORY
# --------------------------------------------------

@app.get("/api/bookings")
def get_bookings():
    user = require_user()

    if not user:
        return auth_error()

    try:
        with get_connection() as conn:
            groups = conn.execute("""
                SELECT
                    g.group_id AS booking_id,
                    g.status,
                    g.payment_status,
                    g.refund_amount,
                    g.cancelled_at,
                    g.priority_level,
                    g.passenger_count,
                    g.total_fare,
                    g.created_at,
                    g.journey_date,
                    t.name AS train_name,
                    t.source,
                    t.destination,
                    t.fare
                FROM booking_groups AS g
                JOIN trains AS t
                    ON t.id = g.train_id
                WHERE g.user_id = ?
                ORDER BY g.group_id DESC
            """, (user["id"],)).fetchall()

            bookings = []

            for group in groups:
                item = dict(group)

                people = conn.execute("""
                    SELECT name, age, gender
                    FROM booking_passengers
                    WHERE group_id = ?
                    ORDER BY passenger_id
                """, (item["booking_id"],)).fetchall()

                item["passengers"] = [
                    dict(person) for person in people
                ]

                item["passenger_name"] = ", ".join(
                    person["name"] for person in people
                )

                item["booking_type"] = (
                    "family" if len(people) > 1 else "single"
                )

                bookings.append(item)

        return jsonify({"bookings": bookings})

    except sqlite3.Error:
        app.logger.exception("Loading booking history failed")
        return jsonify({
            "error": "Could not load your booking history."
        }), 500


# --------------------------------------------------
# CONCURRENCY DEMONSTRATION
# --------------------------------------------------

@app.get("/api/demo/concurrency")
def concurrency_demo():
    """
    Simulates simultaneous requests without modifying real train seats.
    """

    try:
        attempts = int(request.args.get("attempts", 10))
        initial_seats = int(request.args.get("seats", 5))

        if (
            not 1 <= attempts <= 50
            or not 0 <= initial_seats <= 50
        ):
            raise ValueError

    except (ValueError, TypeError):
        return jsonify({
            "error": "Requests must be 1–50 and seats must be 0–50."
        }), 400

    state = {"seats": initial_seats}
    inventory_lock = Lock()
    barrier = Barrier(attempts)
    results = []

    def attempt(number):
        barrier.wait()

        with inventory_lock:
            seats_before = state["seats"]

            if seats_before > 0:
                result = "SUCCESS"
                state["seats"] -= 1
            else:
                result = "REJECTED"

            results.append({
                "request": number,
                "result": result,
                "seats_before": seats_before,
                "remaining_seats": state["seats"],
                "execution_order": len(results) + 1,
            })

    try:
        with ThreadPoolExecutor(max_workers=attempts) as pool:
            futures = [
                pool.submit(attempt, number)
                for number in range(1, attempts + 1)
            ]

            for future in futures:
                future.result()

    except Exception:
        app.logger.exception("Concurrency demo failed")
        return jsonify({
            "error": "Concurrency simulation failed."
        }), 500

    return jsonify({
        "total_requests": attempts,
        "successful_bookings": sum(
            result["result"] == "SUCCESS"
            for result in results
        ),
        "rejected_requests": sum(
            result["result"] == "REJECTED"
            for result in results
        ),
        "remaining_seats": state["seats"],
        "real_database_changed": False,
        "results": sorted(
            results,
            key=lambda result: result["execution_order"],
        ),
    })


# --------------------------------------------------
# PRIORITY-BASED SEAT ALLOCATION DEMONSTRATION
# --------------------------------------------------

@app.post("/api/demo/priority-allocation")
def priority_allocation_demo():
    data = request.get_json(silent=True) or {}
    try:
        seats = int(data.get("seats", 5))
        requests_data = data.get("requests", [])
        if not 0 <= seats <= 50:
            raise ValueError
        if not isinstance(requests_data, list) or not 1 <= len(requests_data) <= 50:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Seats must be 0–50 and requests must contain 1–50 items."}), 400

    priority_rank = {"High": 1, "Medium": 2, "Low": 3}
    normalized = []
    for index, item in enumerate(requests_data):
        if not isinstance(item, dict):
            return jsonify({"error": "Each request must be an object."}), 400
        level = str(item.get("priority", "")).title()
        if level not in priority_rank:
            return jsonify({"error": "Priority must be High, Medium or Low."}), 400
        try:
            count = int(item.get("passengers", 1))
        except (TypeError, ValueError):
            return jsonify({"error": "Passenger count must be a number."}), 400
        if not 1 <= count <= MAX_PASSENGERS:
            return jsonify({"error": "Each request must contain 1–10 passengers."}), 400
        normalized.append({
            "request_id": item.get("request_id", index + 1),
            "priority": level,
            "passengers": count,
            "arrival_order": index
        })

    normalized.sort(key=lambda item: (priority_rank[item["priority"]], item["arrival_order"]))
    results = []
    remaining = seats
    for item in normalized:
        accepted = remaining >= item["passengers"]
        if accepted:
            remaining -= item["passengers"]
        results.append({
            "request_id": item["request_id"],
            "priority": item["priority"],
            "passengers": item["passengers"],
            "result": "SUCCESS" if accepted else "REJECTED",
            "remaining_seats": remaining
        })

    return jsonify({
        "total_requests": len(normalized),
        "successful_requests": sum(x["result"] == "SUCCESS" for x in results),
        "rejected_requests": sum(x["result"] == "REJECTED" for x in results),
        "remaining_seats": remaining,
        "processing_rule": "High > Medium > Low; FCFS for equal priority. If everyone is High, all requests are handled in arrival order.",
        "results": results
    })


# --------------------------------------------------
# START SERVER
# --------------------------------------------------

initialize_database()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
    )
