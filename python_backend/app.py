from recommendation import calculate_recommendations
from flask import Flask, request, jsonify
from flask_cors import CORS
from threading import Lock

app = Flask(__name__)

# Allows a separately running frontend to call this API.
# For local development only; restrict allowed origins for deployment.
CORS(app)

# Temporary sample data.
# We will connect MySQL later.
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
        "endpoints": {
            "search_trains": "GET /api/trains",
            "create_booking": "POST /api/bookings",
            "booking_history": "GET /api/bookings"
        }
    })


# API 1: Search trains
# Example:
# GET /api/trains?source=Dehradun&destination=Delhi
@app.route("/api/trains", methods=["GET"])

@app.route("/api/trains", methods=["GET"])
def search_trains():
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()
    budget_text = request.args.get("budget")

    # Step 1: Validate budget
    try:
        budget = float(budget_text) if budget_text else None

        if budget is not None and budget < 0:
            return jsonify({"error": "Budget cannot be negative"}), 400

    except ValueError:
        return jsonify({"error": "Invalid budget"}), 400

    # Step 2: Filter trains by source, destination and budget
    results = [
        train for train in trains
        if (not source or train["source"].casefold() == source.casefold())
        and (
            not destination
            or train["destination"].casefold() == destination.casefold()
        )
        and (budget is None or train["fare"] <= budget)
    ]

    # Step 3: Read preference weights from the frontend
    try:
        weights = {
            "price": int(request.args.get("price_weight", 5)),
            "duration": int(request.args.get("duration_weight", 4)),
            "availability": int(request.args.get("availability_weight", 3)),
            "timing": int(request.args.get("timing_weight", 2))
        }

        preferred_time = request.args.get("preferred_time")

        if preferred_time:
            from datetime import datetime
            datetime.strptime(preferred_time, "%H:%M")

        # Step 4: Calculate scores and rank trains
        ranked_trains = calculate_recommendations(
            results,
            weights=weights,
            preferred_time=preferred_time
        )

    except (ValueError, TypeError, KeyError) as error:
        return jsonify({"error": str(error)}), 400

    # Step 5: Return ranked trains to the frontend
    return jsonify({
        "count": len(ranked_trains),
        "trains": ranked_trains
    })



# API 2: Book a seat
# POST /api/bookings
# JSON body:
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

    if not isinstance(passenger_name, str) or not passenger_name.strip():
        return jsonify({
            "error": "Passenger name is required"
        }), 400

    # Reject booleans, non-integer IDs and invalid IDs.
    if isinstance(train_id, bool) or not isinstance(train_id, int):
        return jsonify({
            "error": "train_id must be an integer"
        }), 400

    with booking_lock:
        train = next(
            (item for item in trains if item["id"] == train_id),
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

        # Reserve one seat and record the booking
        # together while holding the lock.
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


# API 3: View booking history
@app.route("/api/bookings", methods=["GET"])
def get_bookings():
    with booking_lock:
        return jsonify({
            "count": len(bookings),
            "bookings": bookings
        })


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
