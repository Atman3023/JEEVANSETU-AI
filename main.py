from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from datetime import datetime
from typing import Literal, Optional

from rule_engine import compute_safe_window
from weather_client import get_morning_readings
from alert_store import (
    AlertStatus,
    create_alert,
    get_alert,
    list_alerts,
    list_by_status,
    transition_alert,
    has_active_alert,
    AlertNotFoundError,
    InvalidTransitionError,
)
from history_store import init_db as init_history_db, add_history, get_history

app = FastAPI(title="JeevanSetu AI - Core Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Serve frontend static files ────────────────────────────
_frontend_dir = Path(__file__).resolve().parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/frontend", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


# ─── Initialize history database on startup ─────────────────
@app.on_event("startup")
async def startup():
    init_history_db()


# ─────────────────────────────────────────────────────────────
# Existing endpoints (preserved)
# ─────────────────────────────────────────────────────────────

@app.get("/api/safe-window")
async def safe_window(
    lat: float,
    lon: float,
    profile: Literal["healthy_adult", "pregnant", "elderly", "pre_existing"] = "healthy_adult",
    activity: Literal["general_work", "pesticide_spraying"] = "general_work",
    farmer_name: str = "Farmer",
    demo_red: bool = False,
):
    # ─── DEMO MODE: deterministic RED for Circuit Breaker testing ───
    if demo_red:
        demo_reason = (
            "DEMO RED: simulated unsafe conditions for Circuit Breaker testing."
        )
        result = {
            "demo_mode": True,
            "profile": profile,
            "activity": activity,
            "farmer_name": farmer_name,
            "location": {"lat": lat, "lon": lon},
            "hourly": [
                {
                    "hour_label": f"{h:02d}:00",
                    "zone": "RED",
                    "reason": demo_reason,
                }
                for h in range(5, 11)
            ],
            "safe_window_hours": [],
            "window_summary": "No safe window - DEMO RED active",
            "first_red_hour": "05:00",
        }

        # Circuit Breaker: auto-create alert (with duplicate protection)
        if not has_active_alert(farmer_name, activity, lat, lon):
            alert = create_alert(
                farmer_name=farmer_name,
                farmer_id=farmer_name.lower().replace(" ", "_"),
                lat=lat,
                lon=lon,
                profile=profile,
                activity=activity,
                risk_level="RED",
                reason=demo_reason,
            )
            result["circuit_breaker"] = {
                "triggered": True,
                "alert_id": alert["alert_id"],
                "status": alert["status"],
                "message": "DEMO RED risk detected. Alert created for ASHA review.",
            }
        else:
            result["circuit_breaker"] = {
                "triggered": False,
                "message": "Active alert already exists for this farmer/activity/location.",
            }

        return result

    # ─── REAL MODE: live weather → rule engine (unchanged) ──────────
    try:
        readings = await get_morning_readings(lat, lon)
    except Exception:
        raise HTTPException(status_code=502, detail="Weather service unavailable")
    if not readings:
        raise HTTPException(status_code=502, detail="No weather data available for this location")

    result = compute_safe_window(readings, profile, activity)
    result["farmer_name"] = farmer_name
    result["location"] = {"lat": lat, "lon": lon}

    # --- Circuit Breaker: auto-create alert on RED ---
    red_hours = [h for h in result["hourly"] if h["zone"] == "RED"]
    if red_hours:
        if not has_active_alert(farmer_name, activity, lat, lon):
            first_red = red_hours[0]
            alert = create_alert(
                farmer_name=farmer_name,
                farmer_id=farmer_name.lower().replace(" ", "_"),
                lat=lat,
                lon=lon,
                profile=profile,
                activity=activity,
                risk_level="RED",
                reason=first_red["reason"],
            )
            result["circuit_breaker"] = {
                "triggered": True,
                "alert_id": alert["alert_id"],
                "status": alert["status"],
                "message": "RED risk detected. Alert created for ASHA review.",
            }
        else:
            result["circuit_breaker"] = {
                "triggered": False,
                "message": "Active alert already exists for this farmer/activity/location.",
            }

    return result


class AlertIn(BaseModel):
    farmer_name: str
    farmer_id: str = ""
    lat: float
    lon: float
    reason: str
    profile: str
    activity: str
    risk_level: str = "RED"


@app.post("/api/alert", status_code=201)
async def create_alert_endpoint(alert: AlertIn):
    """
    Called by the app when a farmer attempts work in the RED zone.
    This is the "circuit breaker" from Slide 8 — AI drafts the alert,
    ASHA worker validates before any call is made.
    """
    farmer_id = alert.farmer_id or alert.farmer_name.lower().replace(" ", "_")
    record = create_alert(
        farmer_name=alert.farmer_name,
        farmer_id=farmer_id,
        lat=alert.lat,
        lon=alert.lon,
        profile=alert.profile,
        activity=alert.activity,
        risk_level=alert.risk_level,
        reason=alert.reason,
    )
    return {"ok": True, "alert": record}


@app.get("/api/alerts")
async def list_alerts_endpoint(status: Optional[str] = None):
    """ASHA worker dashboard feed.  Optional ?status= filter."""
    alerts = list_alerts(status=status)
    return {"alerts": alerts, "count": len(alerts)}


# ─────────────────────────────────────────────────────────────
# Circuit Breaker endpoints (new)
# ─────────────────────────────────────────────────────────────

@app.get("/api/alerts/pending")
async def list_pending_alerts():
    """ASHA worker dashboard: only PENDING_ASHA_REVIEW alerts."""
    alerts = list_by_status(AlertStatus.PENDING_ASHA_REVIEW.value)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/api/alerts/{alert_id}")
async def get_alert_endpoint(alert_id: str):
    """Get a single alert by ID."""
    try:
        alert = get_alert(alert_id)
    except AlertNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return {"alert": alert}


class TransitionIn(BaseModel):
    notes: Optional[str] = None


@app.patch("/api/alerts/{alert_id}/validate")
async def validate_alert(alert_id: str, body: Optional[TransitionIn] = None):
    """ASHA validates the alert: PENDING_ASHA_REVIEW → VALIDATED"""
    notes = body.notes if body else None
    try:
        alert = transition_alert(alert_id, AlertStatus.VALIDATED, notes=notes)
    except AlertNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "alert": alert}


@app.patch("/api/alerts/{alert_id}/reject")
async def reject_alert(alert_id: str, body: Optional[TransitionIn] = None):
    """ASHA rejects the alert: PENDING_ASHA_REVIEW → REJECTED"""
    notes = body.notes if body else None
    try:
        alert = transition_alert(alert_id, AlertStatus.REJECTED, notes=notes)
    except AlertNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "alert": alert}


@app.patch("/api/alerts/{alert_id}/contact")
async def contact_farmer(alert_id: str, body: Optional[TransitionIn] = None):
    """Mark farmer as contacted: VALIDATED → FARMER_CONTACTED"""
    notes = body.notes if body else None
    try:
        alert = transition_alert(alert_id, AlertStatus.FARMER_CONTACTED, notes=notes)
    except AlertNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "alert": alert}


@app.patch("/api/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, body: Optional[TransitionIn] = None):
    """Resolve the alert: FARMER_CONTACTED → RESOLVED"""
    notes = body.notes if body else None
    try:
        alert = transition_alert(alert_id, AlertStatus.RESOLVED, notes=notes)
    except AlertNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "alert": alert}


@app.get("/api/current-weather")
async def current_weather(lat: float, lon: float):
    """Proxy current weather from Open-Meteo for frontend display cards."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                    "timezone": "Asia/Kolkata",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        current = data.get("current", {})
        return {
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
        }
    except Exception:
        raise HTTPException(status_code=502, detail="Weather service unavailable")


@app.get("/api/demo-scenarios")
async def demo_scenarios():
    """Returns pre-configured demo scenarios for the frontend demo mode."""
    return {
        "scenarios": [
            {
                "id": "safe",
                "label": "Safe conditions",
                "label_hi": "सुरक्षित स्थिति",
                "icon": "🟢",
                "lat": 20.2961,
                "lon": 85.8245,
                "profile": "healthy_adult",
                "activity": "general_work",
                "farmer_name": "Ramesh Kumar",
                "demo_red": False,
                "description": "Normal weather, healthy adult, general work",
            },
            {
                "id": "caution",
                "label": "Approaching threshold",
                "label_hi": "सावधानी सीमा",
                "icon": "🟡",
                "lat": 26.9124,
                "lon": 70.9120,
                "profile": "elderly",
                "activity": "general_work",
                "farmer_name": "Suresh Patel",
                "demo_red": False,
                "description": "Hot location, elderly profile (lower threshold)",
            },
            {
                "id": "extreme_heat",
                "label": "Extreme heat",
                "label_hi": "अत्यधिक गर्मी",
                "icon": "🔴",
                "lat": 26.9124,
                "lon": 70.9120,
                "profile": "pre_existing",
                "activity": "general_work",
                "farmer_name": "Rajesh Kumar",
                "demo_red": True,
                "description": "Simulated extreme heat for pre-existing condition",
            },
            {
                "id": "pesticide_wind",
                "label": "Pesticide + high wind",
                "label_hi": "कीटनाशक + तेज़ हवा",
                "icon": "🔴",
                "lat": 21.1458,
                "lon": 79.0882,
                "profile": "healthy_adult",
                "activity": "pesticide_spraying",
                "farmer_name": "Sita Devi",
                "demo_red": True,
                "description": "Simulated high wind during pesticide spraying",
            },
            {
                "id": "circuit_breaker",
                "label": "Full ASHA workflow",
                "label_hi": "पूर्ण ASHA कार्यप्रवाह",
                "icon": "🔴→👩‍⚕️",
                "lat": 25.3176,
                "lon": 82.9739,
                "profile": "pregnant",
                "activity": "general_work",
                "farmer_name": "Priya Sharma",
                "demo_red": True,
                "description": "RED → Alert → ASHA validates → Contact → Resolve",
            },
        ]
    }


# ─────────────────────────────────────────────────────────────
# History endpoints (new — SQLite-backed persistence)
# ─────────────────────────────────────────────────────────────

class HistoryIn(BaseModel):
    farmer_id: str
    activity: str
    risk_level: str
    safe_window: str = ""
    reason: str = ""
    weather: Optional[dict] = None


@app.post("/api/history", status_code=201)
async def save_history(entry: HistoryIn):
    """Save a recommendation to persistent history."""
    record = add_history(
        farmer_id=entry.farmer_id,
        activity=entry.activity,
        risk_level=entry.risk_level,
        safe_window=entry.safe_window,
        reason=entry.reason,
        weather_data=entry.weather,
    )
    return {"ok": True, "record": record}


@app.get("/api/history/{farmer_id}")
async def get_farmer_history(farmer_id: str):
    """Get recommendation history for a specific farmer."""
    records = get_history(farmer_id)
    return {"history": records, "count": len(records)}


@app.get("/")
async def root():
    return {"status": "JeevanSetu AI backend running"}


@app.get("/api/health")
async def health():
    return {"status": "JeevanSetu AI backend running"}

