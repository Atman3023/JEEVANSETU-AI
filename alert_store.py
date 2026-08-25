"""
JeevanSetu AI - Alert Lifecycle Store (Circuit Breaker)

In-memory alert store with strict state machine for the ASHA review workflow.
This module manages alert LIFECYCLE only — safety rules live in rule_engine.py.

Flow: RED risk → Alert drafted → PENDING_ASHA_REVIEW → ASHA validates/rejects
      → if validated → FARMER_CONTACTED → RESOLVED
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional


class AlertStatus(str, Enum):
    PENDING_ASHA_REVIEW = "PENDING_ASHA_REVIEW"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    FARMER_CONTACTED = "FARMER_CONTACTED"
    RESOLVED = "RESOLVED"


# ── State machine: valid transitions ─────────────────────────
# REJECTED and RESOLVED are terminal states (no outgoing edges).
VALID_TRANSITIONS: dict[AlertStatus, set[AlertStatus]] = {
    AlertStatus.PENDING_ASHA_REVIEW: {AlertStatus.VALIDATED, AlertStatus.REJECTED},
    AlertStatus.VALIDATED:           {AlertStatus.FARMER_CONTACTED},
    AlertStatus.FARMER_CONTACTED:    {AlertStatus.RESOLVED},
    AlertStatus.REJECTED:            set(),   # terminal
    AlertStatus.RESOLVED:            set(),   # terminal
}


class InvalidTransitionError(Exception):
    """Raised when an alert status transition is not allowed."""
    def __init__(self, current: AlertStatus, target: AlertStatus):
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot transition from {current.value} to {target.value}"
        )


class AlertNotFoundError(Exception):
    """Raised when an alert ID does not exist."""
    def __init__(self, alert_id: str):
        self.alert_id = alert_id
        super().__init__(f"Alert {alert_id} not found")


# --- In-memory store (swap for a real DB later) ---
_alerts: dict[str, dict] = {}


def create_alert(
    farmer_name: str,
    farmer_id: str,
    lat: float,
    lon: float,
    profile: str,
    activity: str,
    risk_level: str,
    reason: str,
) -> dict:
    """Create a new alert in PENDING_ASHA_REVIEW status."""
    alert_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    alert = {
        "alert_id": alert_id,
        "farmer_name": farmer_name,
        "farmer_id": farmer_id,
        "location": {"lat": lat, "lon": lon},
        "profile": profile,
        "activity": activity,
        "risk_level": risk_level,
        "reason": reason,
        "timestamp": now,
        "status": AlertStatus.PENDING_ASHA_REVIEW.value,
        "status_history": [
            {
                "timestamp": now,
                "old_status": None,
                "new_status": AlertStatus.PENDING_ASHA_REVIEW.value,
                "notes": "Alert created by circuit breaker",
            }
        ],
    }
    _alerts[alert_id] = alert
    return alert


def get_alert(alert_id: str) -> dict:
    """Get a single alert by ID.  Raises AlertNotFoundError if missing."""
    if alert_id not in _alerts:
        raise AlertNotFoundError(alert_id)
    return _alerts[alert_id]


def list_alerts(status: Optional[str] = None) -> list[dict]:
    """List all alerts, optionally filtered by status.  Most recent first."""
    alerts = list(_alerts.values())
    if status:
        alerts = [a for a in alerts if a["status"] == status]
    alerts.sort(key=lambda a: a["timestamp"], reverse=True)
    return alerts


def list_by_status(status: str) -> list[dict]:
    """Convenience wrapper — list alerts filtered by a specific status."""
    return list_alerts(status=status)


def transition_alert(
    alert_id: str,
    target_status: AlertStatus,
    notes: Optional[str] = None,
) -> dict:
    """
    Transition an alert to a new status.  Enforces the state machine.

    Raises InvalidTransitionError for illegal transitions.
    Raises AlertNotFoundError if the alert doesn't exist.
    """
    alert = get_alert(alert_id)          # may raise AlertNotFoundError
    current = AlertStatus(alert["status"])

    if target_status not in VALID_TRANSITIONS[current]:
        raise InvalidTransitionError(current, target_status)

    now = datetime.utcnow().isoformat()
    alert["status"] = target_status.value
    alert["status_history"].append({
        "timestamp": now,
        "old_status": current.value,
        "new_status": target_status.value,
        "notes": notes,
    })
    return alert


def has_active_alert(farmer_name: str, activity: str, lat: float, lon: float) -> bool:
    """
    Check if there's already an active (non-terminal) alert for this
    farmer + activity + location.  Used for duplicate-alert prevention
    when /api/safe-window triggers the circuit breaker repeatedly.
    """
    active_statuses = {
        AlertStatus.PENDING_ASHA_REVIEW.value,
        AlertStatus.VALIDATED.value,
        AlertStatus.FARMER_CONTACTED.value,
    }
    for alert in _alerts.values():
        if (
            alert["farmer_name"] == farmer_name
            and alert["activity"] == activity
            and alert["location"]["lat"] == lat
            and alert["location"]["lon"] == lon
            and alert["status"] in active_statuses
        ):
            return True
    return False


def clear_all():
    """Clear all alerts.  Used for testing only."""
    _alerts.clear()
