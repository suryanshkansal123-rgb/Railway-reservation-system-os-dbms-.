
from datetime import datetime


def normalize_lower_is_better(values):
    """Higher score for lower fares or shorter durations."""
    low = min(values)
    high = max(values)

    if high == low:
        return [100.0] * len(values)

    return [
        ((high - value) / (high - low)) * 100
        for value in values
    ]


def normalize_higher_is_better(values):
    """Higher score for greater seat availability."""
    low = min(values)
    high = max(values)

    if high == low:
        return [100.0] * len(values)

    return [
        ((value - low) / (high - low)) * 100
        for value in values
    ]


def calculate_recommendations(
    eligible_trains,
    weights=None,
    preferred_time=None
):
    if not eligible_trains:
        return []

    weights = weights or {
        "price": 5,
        "duration": 4,
        "availability": 3,
        "timing": 2
    }

    factors = ["price", "duration", "availability", "timing"]

    for factor in factors:
        value = weights.get(factor, 0)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Weights must be numeric.")
        if not 1 <= value <= 5:
            raise ValueError("Each weight must be between 1 and 5.")

    total_weight = sum(weights[factor] for factor in factors)
    if total_weight <= 0:
        raise ValueError("Total weight must be positive.")

    price_scores = normalize_lower_is_better(
        [t["fare"] for t in eligible_trains]
    )
    duration_scores = normalize_lower_is_better(
        [t["duration_minutes"] for t in eligible_trains]
    )
    availability_scores = normalize_higher_is_better(
        [t["seats"] for t in eligible_trains]
    )

    def timing_score(train):
        if not preferred_time:
            return 100.0

        train_minutes = (
            datetime.strptime(train["departure_time"], "%H:%M")
            .hour * 60
            + datetime.strptime(train["departure_time"], "%H:%M")
            .minute
        )
        preferred_minutes = (
            datetime.strptime(preferred_time, "%H:%M").hour * 60
            + datetime.strptime(preferred_time, "%H:%M").minute
        )

        difference = abs(train_minutes - preferred_minutes)
        difference = min(difference, 1440 - difference)

        return max(0.0, 100.0 * (1 - difference / 720))

    results = []

    for i, train in enumerate(eligible_trains):
        scores = {
            "price": price_scores[i],
            "duration": duration_scores[i],
            "availability": availability_scores[i],
            "timing": timing_score(train)
        }

        final_score = sum(
            weights[factor] * scores[factor]
            for factor in factors
        ) / total_weight

        results.append({
            **train,
            "component_scores": {
                factor: round(score, 2)
                for factor, score in scores.items()
            },
            "recommendation_score": round(final_score, 2)
        })

    return sorted(
        results,
        key=lambda train: train["recommendation_score"],
        reverse=True
    )
