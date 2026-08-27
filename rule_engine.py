"""
JeevanSetu AI - Core Safe-Working-Window Rule Engine
Deterministic, zero-hallucination. This is the IP from Slide 5 & 6 of the deck.

Thresholds sourced per your deck:
- Heat Stress: 40C / >70% humidity (WHO & ICMR)
- Pesticide Drift: wind speed > 15 km/h (ICAR & CPCB)
- Vulnerable groups: 35C+ (ICMR guidelines)
"""

from dataclasses import dataclass
from typing import List, Literal

Profile = Literal["healthy_adult", "pregnant", "elderly", "pre_existing"]
Activity = Literal["general_work", "pesticide_spraying"]

# Temperature ceiling (deg C) at which each profile is pushed into RED,
# derived from your Slide 6 window durations (5:30 AM start).
PROFILE_HEAT_CEILING = {
    "healthy_adult": 38.0,   # ~2.5 hr window in most Indian summer mornings
    "pregnant": 35.0,        # ~1.5 hr window
    "elderly": 33.5,         # ~1 hr window
    "pre_existing": 32.0,    # ~0.5 hr window
}

HUMIDITY_HEAT_TRIGGER = 70.0     # % - combined with high temp = RED
WIND_DRIFT_LIMIT_KMH = 15.0      # km/h - pesticide spraying only


@dataclass
class HourReading:
    hour_label: str      # e.g. "05:30"
    temp_c: float
    humidity_pct: float
    wind_kmh: float


@dataclass
class HourVerdict:
    hour_label: str
    zone: Literal["GREEN", "YELLOW", "RED"]
    reason: str


def classify_hour(reading: HourReading, profile: Profile, activity: Activity) -> HourVerdict:
    ceiling = PROFILE_HEAT_CEILING[profile]

    # --- Pesticide-specific rule: wind drift risk overrides everything ---
    if activity == "pesticide_spraying" and reading.wind_kmh > WIND_DRIFT_LIMIT_KMH:
        return HourVerdict(reading.hour_label, "RED",
                            f"Wind {reading.wind_kmh:.0f} km/h exceeds {WIND_DRIFT_LIMIT_KMH} km/h drift limit")

    # --- Heat stress rule ---
    if reading.temp_c >= ceiling and reading.humidity_pct >= HUMIDITY_HEAT_TRIGGER:
        return HourVerdict(reading.hour_label, "RED",
                            f"{reading.temp_c:.1f}C + {reading.humidity_pct:.0f}% humidity exceeds safe threshold for {profile}")

    if reading.temp_c >= ceiling:
        return HourVerdict(reading.hour_label, "RED",
                            f"{reading.temp_c:.1f}C exceeds {ceiling}C ceiling for {profile}")

    # --- Yellow: within 2C of ceiling = caution ---
    if reading.temp_c >= ceiling - 2.0:
        return HourVerdict(reading.hour_label, "YELLOW",
                            f"Approaching heat ceiling ({reading.temp_c:.1f}C, ceiling {ceiling}C)")

    if activity == "pesticide_spraying" and reading.wind_kmh >= WIND_DRIFT_LIMIT_KMH - 3:
        return HourVerdict(reading.hour_label, "YELLOW",
                            f"Wind {reading.wind_kmh:.0f} km/h approaching drift limit")

    return HourVerdict(reading.hour_label, "GREEN", "Within safe thresholds")


def compute_safe_window(readings: List[HourReading], profile: Profile, activity: Activity):
    """Returns the ordered list of hourly verdicts + the contiguous safe window from the start."""
    verdicts = [classify_hour(r, profile, activity) for r in readings]

    safe_hours = []
    for v in verdicts:
        if v.zone == "GREEN":
            safe_hours.append(v.hour_label)
        else:
            break  # window ends at first non-green hour

    return {
        "profile": profile,
        "activity": activity,
        "hourly": [v.__dict__ for v in verdicts],
        "safe_window_hours": safe_hours,
        "window_summary": f"{safe_hours[0]} - {safe_hours[-1]}" if safe_hours else "No safe window - stay indoors",
        "first_red_hour": next((v.hour_label for v in verdicts if v.zone == "RED"), None),
    }

