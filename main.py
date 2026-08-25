from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import Literal

from rule_engine import compute_safe_window
from weather_client import get_morning_readings

app = FastAPI(title="JeevanSetu AI - Core Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory alert store (swap for a real DB later - see docs/NEXT_STEPS.md) ---
ALERTS: list[dict] = []


@app.get("/api/safe-window")
async def safe_window(
    lat: float,
    lon: float,
    profile: Literal["healthy_adult", "pregnant", "elderly", "pre_existing"] = "healthy_adult",
    activity: Literal["general_work", "pesticide_spraying"] = "general_work",
    farmer_name: str = "Farmer",
):
    readings = await get_morning_readings(lat, lon)
    if not readings:
        raise HTTPException(status_code=502, detail="No weather data available for this location")

    result = compute_safe_window(readings, profile, activity)
    result["farmer_name"] = farmer_name
    result["location"] = {"lat": lat, "lon": lon}
    return result


class AlertIn(BaseModel):
    farmer_name: str
    lat: float
    lon: float
    reason: str
    profile: str
    activity: str


@app.post("/api/alert")
async def create_alert(alert: AlertIn):
    """
    Called by the app when a farmer attempts work in the RED zone.
    This is the "circuit breaker" from Slide 8 - AI drafts the alert,
    ASHA worker validates before any call is made.
    """
    record = alert.model_dump()
    record["timestamp"] = datetime.utcnow().isoformat()
    record["status"] = "PENDING_ASHA_REVIEW"
    ALERTS.insert(0, record)
    return {"ok": True, "alert": record}


@app.get("/api/alerts")
async def list_alerts():
    """ASHA worker dashboard feed."""
    return {"alerts": ALERTS}


@app.get("/")
async def root():
    return {"status": "JeevanSetu AI backend running"}