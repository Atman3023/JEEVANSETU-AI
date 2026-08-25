# JeevanSetu AI — Smart Farmer Safety System

**AI-powered heat-stress and pesticide-drift risk engine for Indian agricultural workers.**

Built for the IIT Guwahati hackathon. JeevanSetu uses deterministic, research-backed safety rules (WHO, ICMR, ICAR, CPCB thresholds) to compute safe working windows and trigger a **Circuit Breaker** workflow that routes critical alerts through ASHA health workers before reaching farmers.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   JeevanSetu AI Backend                  │
│                                                          │
│  ┌────────────────┐    ┌──────────────────┐              │
│  │ weather_client  │───▶│  rule_engine     │              │
│  │ (Open-Meteo)   │    │  GREEN/YELLOW/RED │              │
│  └────────────────┘    └───────┬──────────┘              │
│                                │                         │
│                          RED detected?                   │
│                                │ yes                     │
│                                ▼                         │
│                     ┌──────────────────┐                 │
│                     │   alert_store    │                  │
│                     │  Circuit Breaker │                  │
│                     └────────┬─────────┘                 │
│                              │                           │
│              ┌───────────────┼───────────────┐           │
│              ▼               ▼               ▼           │
│     PENDING_ASHA_REVIEW → VALIDATED    → REJECTED        │
│                          → FARMER_CONTACTED (terminal)   │
│                          → RESOLVED                      │
└──────────────────────────────────────────────────────────┘
```

### Circuit Breaker State Machine

```
PENDING_ASHA_REVIEW
       │
       ├──── ASHA validates ────▶ VALIDATED
       │                              │
       │                    ASHA contacts farmer
       │                              │
       │                              ▼
       │                      FARMER_CONTACTED
       │                              │
       │                        Situation clear
       │                              │
       │                              ▼
       │                          RESOLVED ■
       │
       └──── ASHA rejects ─────▶ REJECTED ■

■ = terminal state (no further transitions allowed)
```

---

## Setup

```bash
# 1. Install dependencies
pip install fastapi uvicorn httpx pydantic requests

# 2. Start the server
uvicorn main:app --reload

# 3. Run integration tests (in a second terminal)
python training_yard.py
```

---

## Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI backend — all API endpoints |
| `rule_engine.py` | Deterministic safety rules (WHO/ICMR/ICAR thresholds) |
| `weather_client.py` | Live weather data from Open-Meteo |
| `alert_store.py` | Circuit Breaker — alert lifecycle state machine |
| `training_yard.py` | Integration test suite (10 scenarios) |

---

## API Reference

### Core Endpoints

#### `GET /`
Health check.
```bash
curl http://localhost:8000/
```
```json
{"status": "JeevanSetu AI backend running"}
```

#### `GET /api/safe-window`
Compute safe working window for a farmer. **Auto-creates alert if RED detected** (circuit breaker).

| Param | Type | Default | Description |
|---|---|---|---|
| `lat` | float | required | Latitude |
| `lon` | float | required | Longitude |
| `profile` | string | `healthy_adult` | `healthy_adult`, `pregnant`, `elderly`, `pre_existing` |
| `activity` | string | `general_work` | `general_work`, `pesticide_spraying` |
| `farmer_name` | string | `Farmer` | Farmer's name |

```bash
curl "http://localhost:8000/api/safe-window?lat=26.9&lon=70.9&profile=pre_existing&activity=general_work&farmer_name=Rajesh"
```

When RED is detected, the response includes a `circuit_breaker` object:
```json
{
  "circuit_breaker": {
    "triggered": true,
    "alert_id": "abc-123-...",
    "status": "PENDING_ASHA_REVIEW",
    "message": "RED risk detected. Alert created for ASHA review."
  }
}
```

---

### Alert Endpoints

#### `POST /api/alert`
Manually create an alert (status: `PENDING_ASHA_REVIEW`).

```bash
curl -X POST http://localhost:8000/api/alert \
  -H "Content-Type: application/json" \
  -d '{
    "farmer_name": "Rajesh Kumar",
    "farmer_id": "rajesh_kumar",
    "lat": 25.4,
    "lon": 81.8,
    "reason": "Temperature 40.2C exceeds safe threshold",
    "profile": "pre_existing",
    "activity": "general_work",
    "risk_level": "RED"
  }'
```

#### `GET /api/alerts`
List all alerts. Optional `?status=` filter.

```bash
# All alerts
curl http://localhost:8000/api/alerts

# Only resolved alerts
curl "http://localhost:8000/api/alerts?status=RESOLVED"
```

#### `GET /api/alerts/pending`
ASHA dashboard — only `PENDING_ASHA_REVIEW` alerts.

```bash
curl http://localhost:8000/api/alerts/pending
```

#### `GET /api/alerts/{alert_id}`
Get a single alert by ID.

```bash
curl http://localhost:8000/api/alerts/YOUR-ALERT-ID
```

---

### ASHA Workflow Endpoints

All transition endpoints accept an optional JSON body with `notes`:

```json
{"notes": "Your ASHA notes here"}
```

#### `PATCH /api/alerts/{alert_id}/validate`
ASHA validates: `PENDING_ASHA_REVIEW → VALIDATED`

```bash
curl -X PATCH http://localhost:8000/api/alerts/YOUR-ALERT-ID/validate \
  -H "Content-Type: application/json" \
  -d '{"notes": "Verified - farmer at high risk"}'
```

#### `PATCH /api/alerts/{alert_id}/reject`
ASHA rejects: `PENDING_ASHA_REVIEW → REJECTED` (terminal)

```bash
curl -X PATCH http://localhost:8000/api/alerts/YOUR-ALERT-ID/reject \
  -H "Content-Type: application/json" \
  -d '{"notes": "False alarm - farmer is indoors"}'
```

#### `PATCH /api/alerts/{alert_id}/contact`
Mark farmer contacted: `VALIDATED → FARMER_CONTACTED`

```bash
curl -X PATCH http://localhost:8000/api/alerts/YOUR-ALERT-ID/contact \
  -H "Content-Type: application/json" \
  -d '{"notes": "Called farmer, advised to stay indoors"}'
```

#### `PATCH /api/alerts/{alert_id}/resolve`
Resolve alert: `FARMER_CONTACTED → RESOLVED` (terminal)

```bash
curl -X PATCH http://localhost:8000/api/alerts/YOUR-ALERT-ID/resolve \
  -H "Content-Type: application/json" \
  -d '{"notes": "Farmer confirmed he stopped work"}'
```

---

### Error Responses

| Code | Meaning | Example |
|---|---|---|
| `404` | Alert not found | `GET /api/alerts/nonexistent-id` |
| `409` | Invalid state transition | `PATCH /reject` on an already `VALIDATED` alert |
| `422` | Validation error | Missing required fields |
| `502` | Weather API unavailable | Open-Meteo down |

---

## End-to-End Example

```bash
# 1. Create an alert
curl -s -X POST http://localhost:8000/api/alert \
  -H "Content-Type: application/json" \
  -d '{
    "farmer_name": "Rajesh Kumar",
    "farmer_id": "rajesh_kumar",
    "lat": 25.4, "lon": 81.8,
    "reason": "Heat stress: 40.2C",
    "profile": "pre_existing",
    "activity": "general_work"
  }' | python -m json.tool
# → status: PENDING_ASHA_REVIEW, alert_id: abc-123

# 2. ASHA validates
curl -s -X PATCH http://localhost:8000/api/alerts/abc-123/validate \
  -H "Content-Type: application/json" \
  -d '{"notes": "Confirmed - farmer has cardiac history"}' | python -m json.tool
# → status: VALIDATED

# 3. Contact farmer
curl -s -X PATCH http://localhost:8000/api/alerts/abc-123/contact \
  -H "Content-Type: application/json" \
  -d '{"notes": "Called at 9:15 AM, advised rest"}' | python -m json.tool
# → status: FARMER_CONTACTED

# 4. Resolve
curl -s -X PATCH http://localhost:8000/api/alerts/abc-123/resolve \
  -H "Content-Type: application/json" \
  -d '{"notes": "Farmer safe. Case closed."}' | python -m json.tool
# → status: RESOLVED
```

---

## Testing

```bash
# Start server
uvicorn main:app --reload

# Run all 10 test scenarios
python training_yard.py
```

The test suite validates:
1. RED → automatic alert creation
2. Duplicate alert prevention
3. Manual alert creation with full field validation
4. ASHA validation with notes
5. Farmer contacted transition
6. Alert resolution (full lifecycle)
7. ASHA rejection
8. Rejected alert cannot be contacted (409)
9. All invalid state transitions blocked (409)
10. Unknown alert returns 404

---

## Limitations & Assumptions

- **In-memory store**: Alerts are lost on server restart. Swap `alert_store._alerts` for a database in production.
- **No authentication**: ASHA worker identity is not verified. Add auth middleware before deployment.
- **Weather-dependent auto-alert**: The auto-alert in `/api/safe-window` depends on live Open-Meteo data. If weather is mild, no RED is triggered.
- **Single-server**: No distributed locking. Fine for hackathon demo.
- **No frontend yet**: This is the backend-only Circuit Breaker. Frontend comes next.
