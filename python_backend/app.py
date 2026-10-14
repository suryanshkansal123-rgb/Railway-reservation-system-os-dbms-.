
from flask import Flask, request, jsonify
from flask_cors import CORS
from threading import Lock

from recommendation import calculate_recommendations

app = Flask(__name__)
CORS(app)

# Temporary sample data.
# MySQL integration can be added later.
trains = [
    {
        "id": 1,
        "number": "12017",
        "name": "Shatabdi Express",
        "source": "Dehradun",
        "destination": "Delhi",
        "fare": 500,
        "seats": 10,
        "duration_minutes": 360,
        "departure_time": "06:00"
    },
    {
        "id": 2,
        "number": "14041",
        "name": "Mussoorie Express",
        "source": "Dehradun",
        "destination": "Delhi",
        "fare": 250,
        "seats": 5,
        "duration_minutes": 360,
        "departure_time": "06:00"
    },
    {
        "id": 3,
        "number": "12018",
        "name": "Jan Shatabdi",
        "source": "Delhi",
        "destination": "Dehradun",
        "fare": 400,
        "seats": 8,
        "duration_minutes": 360,
        "departure_time": "06:00"
    }
]

bookings = []
next_booking_id = 1

# Protects seat allocation and booking creation
# within this single running Python process.
booking_lock = Lock()


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Railway Reservation Backend is running",
        "features": [
            "Train search",
            "Budget filtering",
            "Weighted train recommendations",
            "Seat booking",
            "Booking history"
        ],
        "endpoints": {
            "search_trains": "GET /api/trains",
            "create_booking": "POST /api/bookings",
            "booking_history": "GET /api/bookings"
        }
    })


# API 1: Search and rank trains.
#
# Example:
# /api/trains?source=Dehradun&destination=Delhi
#
# Optional parameters:
# budget=500
# price_weight=5
# duration_weight=4
# availability_weight=3
# timing_weight=2
# preferred_time=06:00

@app.route("/api/trains", methods=["GET"])
def search_trains():
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()

    # Filter by route.
    results = [
        train for train in trains
        if (
            not source
            or train["source"].casefold() == source.casefold()
        )
        and (
            not destination
            or train["destination"].casefold() == destination.casefold()
        )
    ]

    # Optional maximum budget.
    budget_value = request.args.get("budget", "").strip()

    if budget_value:
        try:
            budget = float(budget_value)

            if budget < 0:
                raise ValueError

        except ValueError:
            return jsonify({
                "error": "Budget must be a non-negative number"
            }), 400

        results = [
            train for train in results
            if train["fare"] <= budget
        ]

    # Read passenger preference weights.
    weight_parameters = {
        "price": "price_weight",
        "duration": "duration_weight",
        "availability": "availability_weight",
        "timing": "timing_weight"
    }

    default_weights = {
        "price": 5,
        "duration": 4,
        "availability": 3,
        "timing": 2
    }

    weights = {}

    try:
        for factor, parameter in weight_parameters.items():
            raw_value = request.args.get(parameter)

            if raw_value is None or raw_value.strip() == "":
                weight = default_weights[factor]
            else:
                weight = int(raw_value)

            if not 1 <= weight <= 5:
                raise ValueError

            weights[factor] = weight

    except (ValueError, AttributeError):
        return jsonify({
            "error": "Each recommendation weight must be an integer from 1 to 5"
        }), 400

    preferred_time = request.args.get(
        "preferred_time", ""
    ).strip()

    if preferred_time:
        from datetime import datetime

        try:
            datetime.strptime(preferred_time, "%H:%M")
        except ValueError:
            return jsonify({
                "error": "Preferred time must use HH:MM format"
            }), 400

    # Calculate scores and sort trains from best to worst.
    ranked_trains = calculate_recommendations(
        results,
        weights=weights,
        preferred_time=preferred_time or None
    )

    return jsonify({
        "count": len(ranked_trains),
        "trains": ranked_trains,
        "weights": weights,
        "preferred_time": preferred_time or None
    })


# API 2: Book a seat.
#
# POST /api/bookings
# JSON:
# {
#   "train_id": 1,
#   "passenger_name": "Test Passenger"
# }

@app.route("/api/bookings", methods=["POST"])
def create_booking():
    global next_booking_id

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Send booking details as JSON"
        }), 400

    passenger_name = data.get("passenger_name")
    train_id = data.get("train_id")

    if (
        not isinstance(passenger_name, str)
        or not passenger_name.strip()
    ):
        return jsonify({
            "error": "Passenger name is required"
        }), 400

    if isinstance(train_id, bool) or not isinstance(train_id, int):
        return jsonify({
            "error": "train_id must be an integer"
        }), 400

    with booking_lock:
        train = next(
            (
                item for item in trains
                if item["id"] == train_id
            ),
            None
        )

        if train is None:
            return jsonify({
                "error": "Train not found"
            }), 404

        if train["seats"] <= 0:
            return jsonify({
                "error": "No seats available"
            }), 409

        # Reserve a seat and create the booking atomically
        # within this running Python process.
        train["seats"] -= 1

        booking = {
            "booking_id": next_booking_id,
            "train_id": train["id"],
            "train_number": train["number"],
            "train_name": train["name"],
            "passenger_name": passenger_name.strip(),
            "fare": train["fare"],
            "status": "CONFIRMED"
        }

        bookings.append(booking)
        next_booking_id += 1

        return jsonify({
            "message": "Booking successful",
            "booking": booking,
            "seats_remaining": train["seats"]
        }), 201


# API 3: View booking history.

@app.route("/api/bookings", methods=["GET"])
def get_bookings():
    with booking_lock:
        return jsonify({
            "count": len(bookings),
            "bookings": list(bookings)
        })


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
