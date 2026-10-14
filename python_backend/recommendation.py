
from datetime import datetime


def normalize_lower_is_better(values):
    """Convert lower-is-better values to scores between 0 and 100."""
    if not values:
        return []

    minimum = min(values)
    maximum = max(values)

    if minimum == maximum:
        return [100.0] * len(values)

    return [
        ((maximum - value) / (maximum - minimum)) * 100
        for value in values
    ]


def normalize_higher_is_better(values):
    """Convert higher-is-better values to scores between 0 and 100."""
    if not values:
        return []

    minimum = min(values)
    maximum = max(values)

    if minimum == maximum:
        return [100.0] * len(values)

    return [
        ((value - minimum) / (maximum - minimum)) * 100
        for value in values
    ]


def calculate_timing_score(departure_time, preferred_time):
    """Give a higher score to departure times closer to the preference."""
    if not preferred_time:
        return 100.0

    try:
        departure = datetime.strptime(departure_time, "%H:%M")
        preferred = datetime.strptime(preferred_time, "%H:%M")
    except (ValueError, TypeError):
        return 0.0

    departure_minutes = departure.hour * 60 + departure.minute
    preferred_minutes = preferred.hour * 60 + preferred.minute

    difference = abs(departure_minutes - preferred_minutes)
    difference = min(difference, 1440 - difference)

    return round(max(0.0, 100.0 * (1 - difference / 720)), 2)


def calculate_recommendations(
    eligible_trains,
    weights=None,
    preferred_time=None
):
    """
    Rank eligible trains using price, duration, seats and departure time.

    Each weight must be between 1 and 5.
    """
    if not eligible_trains:
        return []

    default_weights = {
        "price": 5,
        "duration": 4,
        "availability": 3,
        "timing": 2
    }

    if weights is None:
        weights = default_weights.copy()
    else:
        weights = {
            key: weights.get(key, default)
            for key, default in default_weights.items()
        }

    for name, weight in weights.items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError(f"{name} weight must be a number from 1 to 5")

        if not 1 <= weight <= 5:
            raise ValueError(f"{name} weight must be between 1 and 5")

    prices = [float(train["fare"]) for train in eligible_trains]
    durations = [
        float(train.get("duration_minutes", 360))
        for train in eligible_trains
    ]
    seats = [float(train["seats"]) for train in eligible_trains]

    price_scores = normalize_lower_is_better(prices)
    duration_scores = normalize_lower_is_better(durations)
    availability_scores = normalize_higher_is_better(seats)

    ranked_trains = []

    for index, train in enumerate(eligible_trains):
        timing_score = calculate_timing_score(
            train.get("departure_time", "06:00"),
            preferred_time
        )

        component_scores = {
            "price": round(price_scores[index], 2),
            "duration": round(duration_scores[index], 2),
            "availability": round(availability_scores[index], 2),
            "timing": round(timing_score, 2)
        }

        total_weight = sum(weights.values())

        final_score = sum(
            component_scores[name] * weights[name]
            for name in weights
        ) / total_weight

        result = dict(train)
        result["component_scores"] = component_scores
        result["recommendation_score"] = round(final_score, 2)

        ranked_trains.append(result)

    ranked_trains.sort(
        key=lambda train: train["recommendation_score"],
        reverse=True
    )

    return ranked_trains
