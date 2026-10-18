
from pathlib import Path
import os
import math
import sqlite3
from datetime import date as date_type
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from itertools import permutations

from flask import Flask, jsonify, request
from flask_cors import CORS
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash

from recommendation import calculate_recommendations


app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://127.0.0.1:5500",
                "http://localhost:5500",
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "null",
            ]
        }
    },
)

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
                FOREIGN KEY (group_id)
                    REFERENCES booking_groups(group_id)
                    ON DELETE CASCADE
            )
        """)

        group_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(booking_groups)"
            ).fetchall()
        }

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

@app.get("/api/trains")
def search_trains():
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()

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

    journey_date = str(
        data.get("journey_date", date_type.today().isoformat())
    ).strip()

    try:
        journey_date = date_type.fromisoformat(journey_date).isoformat()
    except (ValueError, TypeError):
        return jsonify({
            "error": "Please select a valid journey date (YYYY-MM-DD)."
        }), 400

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

    try:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")

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

            total_fare = float(train["fare"]) * passenger_count

            cursor = conn.execute("""
                INSERT INTO booking_groups (
                    user_id, train_id, passenger_count,
                    total_fare, journey_date
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                user["id"],
                train_id,
                passenger_count,
                total_fare,
                journey_date,
            ))

            group_id = cursor.lastrowid

            conn.executemany("""
                INSERT INTO booking_passengers (
                    group_id, name, age, gender
                )
                VALUES (?, ?, ?, ?)
            """, [
                (
                    group_id,
                    person["name"],
                    person["age"],
                    person["gender"],
                )
                for person in passengers
            ])

            conn.commit()

        return jsonify({
            "message": (
                "Family booking successful!"
                if passenger_count > 1
                else "Booking successful!"
            ),
            "booking_id": group_id,
            "passenger_count": passenger_count,
            "passengers": passengers,
            "train_name": train["name"],
            "fare_per_passenger": float(train["fare"]),
            "total_fare": total_fare,
        }), 201

    except sqlite3.Error:
        app.logger.exception("Booking failed")
        return jsonify({
            "error": "Could not complete booking."
        }), 500


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
    lock = Lock()
    barrier = Barrier(attempts)
    results = []

    def attempt(number):
        barrier.wait()

        with lock:
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
# START SERVER
# --------------------------------------------------

initialize_database()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )
