from datetime import date, timedelta
from statistics import median


def predict_next_release(
    actual_release_dates: list[str],
    max_intervals: int = 5,
    minimum_intervals: int = 3,
) -> dict:
    """Estimate a release date from recent comparable release intervals."""
    dates = sorted({
        date.fromisoformat(value[:10])
        for value in actual_release_dates
        if value
    })
    intervals = [
        (later - earlier).days
        for earlier, later in zip(dates, dates[1:])
        if (later - earlier).days > 0
    ]
    selected = intervals[-max_intervals:]
    if len(selected) < minimum_intervals:
        return {
            "predicted_date": None,
            "window_start": None,
            "window_end": None,
            "data_points": len(selected),
            "notice": "Insufficient historical release intervals for a prediction.",
        }

    last_release = dates[-1]
    predicted_days = round(median(selected))
    return {
        "predicted_date": (last_release + timedelta(days=predicted_days)).isoformat(),
        "window_start": (last_release + timedelta(days=min(selected))).isoformat(),
        "window_end": (last_release + timedelta(days=max(selected))).isoformat(),
        "data_points": len(selected),
        "intervals_days": selected,
        "notice": "Historical estimate only; not an official release date.",
    }
