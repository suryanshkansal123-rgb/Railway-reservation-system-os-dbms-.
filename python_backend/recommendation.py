
"""Train recommendations based on the user's selected preferences."""

from datetime import datetime
import math


CATEGORIES = ("price", "duration", "availability", "timing")


def safe_number(train, key, default=0):
    try:
        value = float(train.get(key, default))
        return value if math.isfinite(value) else float(default)
    except (TypeError, ValueError, AttributeError):
        return float(default)


def normalize_weights(weights=None):
    """Accept either short names or frontend-style names."""
    weights = weights or {}

    aliases = {
        "price": ("price", "price_weight"),
        "duration": ("duration", "duration_weight"),
        "availability": ("availability", "availability_weight"),
        "timing": ("timing", "timing_weight"),
    }

    result = {}

    for category, names in aliases.items():
        value = 1

        for name in names:
            if name in weights:
                try:
                    value = float(weights[name])
                except (TypeError, ValueError):
                    value = 1
                break

        if not math.isfinite(value):
            value = 1

        result[category] = min(5.0, max(1.0, value))

    return result


def minmax_scores(values, lower_is_better=False):
    """Normalize a list of values to scores between 0 and 100."""
    if not values:
        return []

    low = min(values)
    high = max(values)

    if high == low:
        return [50.0] * len(values)

    scores = []

    for value in values:
        score = 100.0 * (value - low) / (high - low)

        if lower_is_better:
            score = 100.0 - score

        scores.append(score)

    return scores


def departure_time_score(departure_time, preferred_time):
    """Score how close a train's departure is to the preferred time."""
    if not preferred_time:
        return 50.0

    try:
        departure = datetime.strptime(
            str(departure_time), "%H:%M"
        )
        preferred = datetime.strptime(
            str(preferred_time), "%H:%M"
        )

        departure_minutes = departure.hour * 60 + departure.minute
        preferred_minutes = preferred.hour * 60 + preferred.minute

        difference = abs(departure_minutes - preferred_minutes)
        difference = min(difference, 1440 - difference)

        return round(100.0 * (1.0 - difference / 720.0), 2)

    except (TypeError, ValueError):
        return 50.0


def calculate_recommendations(trains, weights=None, preferred_time=None):
    """
    Return trains sorted by their weighted recommendation score.

    Expected train fields:
        fare, duration_minutes, seats, departure_time

    Each train receives:
        recommendation_score
        component_scores
        score_breakdown
        applied_weights
    """
    if not trains:
        return []

    weights = normalize_weights(weights)

    fares = [safe_number(t, "fare") for t in trains]
    durations = [safe_number(t, "duration_minutes") for t in trains]
    seats = [safe_number(t, "seats") for t in trains]

    # Lower fare and shorter duration are better.
    price_scores = minmax_scores(fares, lower_is_better=True)
    duration_scores = minmax_scores(durations, lower_is_better=True)

    # More available seats are better.
    availability_scores = minmax_scores(seats)

    total_weight = sum(weights.values())
    ranked = []

    for index, original in enumerate(trains):
        train = dict(original)

        scores = {
            "price": round(price_scores[index], 2),
            "duration": round(duration_scores[index], 2),
            "availability": round(availability_scores[index], 2),
            "timing": departure_time_score(
                train.get("departure_time"), preferred_time
            ),
        }

        final_score = sum(
            scores[category] * weights[category]
            for category in CATEGORIES
        ) / total_weight

        # The frontend currently reads component_scores.
        # Keep score_breakdown too for compatibility.
        train["recommendation_score"] = round(final_score, 2)
        train["component_scores"] = scores
        train["score_breakdown"] = scores.copy()
        train["applied_weights"] = weights.copy()

        ranked.append(train)

    ranked.sort(
        key=lambda t: (
            -t["recommendation_score"],
            safe_number(t, "fare"),
            safe_number(t, "duration_minutes"),
        )
    )

    return ranked


def get_best_train(trains, weights=None, preferred_time=None):
    ranked = calculate_recommendations(
        trains,
        weights=weights,
        preferred_time=preferred_time,
    )
    return ranked[0] if ranked else None
