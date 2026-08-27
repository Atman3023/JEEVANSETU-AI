"""
JeevanSetu AI - Circuit Breaker Integration Test Suite (Training Yard)

Run against the live FastAPI backend:
    Terminal 1:  uvicorn main:app --reload
    Terminal 2:  python training_yard.py

Tests the complete Circuit Breaker workflow:
    RED -> Alert -> PENDING_ASHA_REVIEW -> VALIDATED -> FARMER_CONTACTED -> RESOLVED
    RED -> Alert -> PENDING_ASHA_REVIEW -> REJECTED  (terminal)
    Invalid transitions -> HTTP 409
    Unknown alerts       -> HTTP 404

Thresholds reference (from rule_engine.py -- NOT duplicated here):
    pre_existing profile ceiling = 32.0 C
    pesticide_spraying wind drift limit = 15.0 km/h
"""

import sys
import requests

BASE = "http://127.0.0.1:8000"

passed = 0
failed = 0
skipped = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f" -- {detail}" if detail else ""))


def skip(name, reason=""):
    global skipped
    skipped += 1
    print(f"  [SKIP] {name}" + (f" -- {reason}" if reason else ""))


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# -- Preflight: check server is running --
print("\n[*] Connecting to JeevanSetu backend...")
try:
    r = requests.get(f"{BASE}/", timeout=5)
    assert r.status_code == 200
    print(f"    Connected: {r.json()}")
except Exception:
    print(f"    [ERROR] Cannot connect to {BASE}. Is the server running?")
    print(f"    Start with:  uvicorn main:app --reload")
    sys.exit(1)


# ==============================================================
# TEST 0A: DEMO RED triggers RED + PENDING_ASHA_REVIEW
# ==============================================================
section("TEST 0A: DEMO RED -> RED + PENDING_ASHA_REVIEW")

r = requests.get(f"{BASE}/api/safe-window", params={
    "lat": 20.2961, "lon": 85.8245,
    "profile": "healthy_adult",
    "activity": "general_work",
    "farmer_name": "Demo Farmer",
    "demo_red": "true",
})
test("DEMO RED returns 200", r.status_code == 200)
data = r.json()
test("demo_mode flag is True", data.get("demo_mode") is True)
test("All hours are RED",
     all(h["zone"] == "RED" for h in data["hourly"]))
test("Reason mentions DEMO RED",
     "DEMO RED" in data["hourly"][0]["reason"])
test("No safe window hours", data["safe_window_hours"] == [])
test("first_red_hour is 05:00", data["first_red_hour"] == "05:00")

cb = data.get("circuit_breaker", {})
test("Circuit breaker triggered", cb.get("triggered") is True)
demo_alert_id = cb.get("alert_id")
test("Alert ID returned", demo_alert_id is not None)
test("Status = PENDING_ASHA_REVIEW", cb.get("status") == "PENDING_ASHA_REVIEW")

# Verify the alert exists in the store
if demo_alert_id:
    ar = requests.get(f"{BASE}/api/alerts/{demo_alert_id}")
    test("Demo alert retrievable by ID", ar.status_code == 200)
    a = ar.json()["alert"]
    test("Alert status = PENDING_ASHA_REVIEW", a["status"] == "PENDING_ASHA_REVIEW")
    test("Alert risk_level = RED", a["risk_level"] == "RED")
    test("Alert reason mentions DEMO RED", "DEMO RED" in a["reason"])
    test("Alert has status_history", len(a["status_history"]) >= 1)


# ==============================================================
# TEST 0B: DEMO RED Duplicate Protection
# ==============================================================
section("TEST 0B: DEMO RED Duplicate Protection")

r2 = requests.get(f"{BASE}/api/safe-window", params={
    "lat": 20.2961, "lon": 85.8245,
    "profile": "healthy_adult",
    "activity": "general_work",
    "farmer_name": "Demo Farmer",
    "demo_red": "true",
})
test("Second DEMO RED returns 200", r2.status_code == 200)
cb2 = r2.json().get("circuit_breaker", {})
test("Duplicate alert NOT created (triggered=False)",
     cb2.get("triggered") is False)
test("Message mentions active alert exists",
     "already exists" in cb2.get("message", "").lower())


# ==============================================================
# TEST 0C: DEMO RED → Full Lifecycle (validate → contact → resolve)
# ==============================================================
section("TEST 0C: DEMO RED Full Lifecycle")

# Validate
r = requests.patch(f"{BASE}/api/alerts/{demo_alert_id}/validate", json={
    "notes": "DEMO: ASHA verified alert"
})
test("Validate returns 200", r.status_code == 200)
alert = r.json()["alert"]
test("Status = VALIDATED", alert["status"] == "VALIDATED")
test("status_history has 2 entries", len(alert["status_history"]) == 2)

# Contact
r = requests.patch(f"{BASE}/api/alerts/{demo_alert_id}/contact", json={
    "notes": "DEMO: Called farmer"
})
test("Contact returns 200", r.status_code == 200)
alert = r.json()["alert"]
test("Status = FARMER_CONTACTED", alert["status"] == "FARMER_CONTACTED")
test("status_history has 3 entries", len(alert["status_history"]) == 3)

# Resolve
r = requests.patch(f"{BASE}/api/alerts/{demo_alert_id}/resolve", json={
    "notes": "DEMO: Situation resolved"
})
test("Resolve returns 200", r.status_code == 200)
alert = r.json()["alert"]
test("Status = RESOLVED", alert["status"] == "RESOLVED")
test("status_history has 4 entries", len(alert["status_history"]) == 4)
test("Full lifecycle in status_history",
     [h["new_status"] for h in alert["status_history"]]
     == ["PENDING_ASHA_REVIEW", "VALIDATED", "FARMER_CONTACTED", "RESOLVED"])


# ==============================================================
# TEST 0D: DEMO RED → Rejection flow
# ==============================================================
section("TEST 0D: DEMO RED Rejection Flow")

# Create a new demo alert (previous one is RESOLVED, so new one allowed)
r = requests.get(f"{BASE}/api/safe-window", params={
    "lat": 21.0, "lon": 86.0,
    "profile": "elderly",
    "activity": "general_work",
    "farmer_name": "Demo Reject Farmer",
    "demo_red": "true",
})
reject_demo_id = r.json()["circuit_breaker"]["alert_id"]

# Reject
r = requests.patch(f"{BASE}/api/alerts/{reject_demo_id}/reject", json={
    "notes": "DEMO: False alarm"
})
test("Reject returns 200", r.status_code == 200)
alert = r.json()["alert"]
test("Status = REJECTED", alert["status"] == "REJECTED")


# ==============================================================
# TEST 0E: DEMO RED — Rejected → Contact returns 409
# ==============================================================
section("TEST 0E: DEMO RED Rejected Is Terminal")

r = requests.patch(f"{BASE}/api/alerts/{reject_demo_id}/contact", json={})
test("REJECTED → FARMER_CONTACTED blocked (409)", r.status_code == 409)

r = requests.patch(f"{BASE}/api/alerts/{reject_demo_id}/validate", json={})
test("REJECTED → VALIDATED blocked (409)", r.status_code == 409)

r = requests.patch(f"{BASE}/api/alerts/{reject_demo_id}/resolve", json={})
test("REJECTED → RESOLVED blocked (409)", r.status_code == 409)


# ==============================================================
# TEST 0F: demo_red=false uses real weather (not DEMO)
# ==============================================================
section("TEST 0F: demo_red=false Uses Real Weather")

r = requests.get(f"{BASE}/api/safe-window", params={
    "lat": 20.2961, "lon": 85.8245,
    "profile": "healthy_adult",
    "activity": "general_work",
    "farmer_name": "Normal Farmer",
    "demo_red": "false",
})
if r.status_code == 200:
    data = r.json()
    test("No demo_mode flag when demo_red=false",
         data.get("demo_mode") is None)
elif r.status_code == 502:
    skip("demo_red=false real-weather test", "Weather API unavailable (502)")
else:
    test("demo_red=false endpoint responds", False, f"HTTP {r.status_code}")


# ==============================================================
# TEST 1: RED -> Automatic Alert via /api/safe-window (LIVE WEATHER)
# ==============================================================
section("TEST 1: RED -> Automatic Alert (Circuit Breaker Trigger) [LIVE WEATHER]")

# pre_existing profile has a 32 C ceiling (rule_engine.py line 23).
# Jaisalmer, Rajasthan is one of the hottest places in India;
# at least one hour between 05:00-10:00 is very likely >= 32 C
# during Indian summer.  The test gracefully skips if weather is mild.
auto_alert_id = None
r = requests.get(f"{BASE}/api/safe-window", params={
    "lat": 26.9,
    "lon": 70.9,
    "profile": "pre_existing",
    "activity": "general_work",
    "farmer_name": "Test_AutoRed_Farmer",
})

if r.status_code == 200:
    data = r.json()
    red_hours = [h for h in data["hourly"] if h["zone"] == "RED"]

    if red_hours:
        test("Live weather produced RED hours", True)
        cb = data.get("circuit_breaker", {})
        test("Circuit breaker triggered", cb.get("triggered") is True)

        if cb.get("alert_id"):
            auto_alert_id = cb["alert_id"]
            ar = requests.get(f"{BASE}/api/alerts/{auto_alert_id}")
            test("Auto-alert retrievable by ID", ar.status_code == 200)
            if ar.status_code == 200:
                a = ar.json()["alert"]
                test("Auto-alert status = PENDING_ASHA_REVIEW",
                     a["status"] == "PENDING_ASHA_REVIEW")
                test("Auto-alert farmer_name matches",
                     a["farmer_name"] == "Test_AutoRed_Farmer")
                test("Auto-alert risk_level = RED",
                     a["risk_level"] == "RED")
    else:
        skip("Live weather RED test",
             "Weather at Jaisalmer returned no RED hours for pre_existing "
             "profile right now (temp < 32 C).  Weather-dependent test.")
elif r.status_code == 502:
    skip("Live weather RED test", "Weather API unavailable (502)")
else:
    test("Safe-window endpoint responds", False, f"HTTP {r.status_code}")


# ==============================================================
# TEST 2: Duplicate Alert Protection
# ==============================================================
section("TEST 2: Duplicate Alert Protection")

if auto_alert_id:
    r2 = requests.get(f"{BASE}/api/safe-window", params={
        "lat": 26.9, "lon": 70.9,
        "profile": "pre_existing",
        "activity": "general_work",
        "farmer_name": "Test_AutoRed_Farmer",
    })
    if r2.status_code == 200:
        data2 = r2.json()
        cb2 = data2.get("circuit_breaker", {})
        if cb2:
            test("Duplicate alert NOT created",
                 cb2.get("triggered") is False,
                 f"triggered={cb2.get('triggered')}")
        else:
            skip("Duplicate protection",
                 "No circuit_breaker key (weather may have changed)")
    else:
        skip("Duplicate protection", f"Endpoint returned {r2.status_code}")
else:
    skip("Duplicate protection",
         "No auto-alert was created in Test 1 (weather-dependent)")


# ==============================================================
# TEST 3: Manual Alert Creation
# ==============================================================
section("TEST 3: Manual Alert Creation")

r = requests.post(f"{BASE}/api/alert", json={
    "farmer_name": "Rajesh Kumar",
    "farmer_id": "rajesh_kumar",
    "lat": 25.4,
    "lon": 81.8,
    "reason": "Temperature 40.2C exceeds 32C ceiling for pre_existing",
    "profile": "pre_existing",
    "activity": "general_work",
    "risk_level": "RED",
})
test("Alert created (HTTP 201)", r.status_code == 201)
alert = r.json()["alert"]
alert_id = alert["alert_id"]
test("Has UUID alert_id", len(alert_id) == 36 and "-" in alert_id)
test("Status = PENDING_ASHA_REVIEW", alert["status"] == "PENDING_ASHA_REVIEW")
test("farmer_name stored", alert["farmer_name"] == "Rajesh Kumar")
test("farmer_id stored", alert["farmer_id"] == "rajesh_kumar")
test("location stored", alert["location"] == {"lat": 25.4, "lon": 81.8})
test("profile stored", alert["profile"] == "pre_existing")
test("activity stored", alert["activity"] == "general_work")
test("risk_level stored", alert["risk_level"] == "RED")
test("reason stored", "40.2" in alert["reason"])
test("timestamp present", alert.get("timestamp") is not None)
test("status_history has 1 entry", len(alert["status_history"]) == 1)
test("Initial history: None -> PENDING",
     alert["status_history"][0]["old_status"] is None
     and alert["status_history"][0]["new_status"] == "PENDING_ASHA_REVIEW")


# ==============================================================
# TEST 4: ASHA Validates Alert
# ==============================================================
section("TEST 4: ASHA Validates Alert")

r = requests.patch(f"{BASE}/api/alerts/{alert_id}/validate", json={
    "notes": "Verified - farmer is at high risk due to cardiac condition"
})
test("Validate returns 200", r.status_code == 200)
alert = r.json()["alert"]
test("Status = VALIDATED", alert["status"] == "VALIDATED")
test("status_history has 2 entries", len(alert["status_history"]) == 2)
test("History: PENDING -> VALIDATED",
     alert["status_history"][-1]["old_status"] == "PENDING_ASHA_REVIEW"
     and alert["status_history"][-1]["new_status"] == "VALIDATED")
test("ASHA notes recorded",
     "cardiac" in (alert["status_history"][-1].get("notes") or ""))


# ==============================================================
# TEST 5: Farmer Contacted
# ==============================================================
section("TEST 5: Farmer Contacted")

r = requests.patch(f"{BASE}/api/alerts/{alert_id}/contact", json={
    "notes": "Called Rajesh at +91-XXXXX. Advised to stay indoors."
})
test("Contact returns 200", r.status_code == 200)
alert = r.json()["alert"]
test("Status = FARMER_CONTACTED", alert["status"] == "FARMER_CONTACTED")
test("status_history has 3 entries", len(alert["status_history"]) == 3)
test("History: VALIDATED -> FARMER_CONTACTED",
     alert["status_history"][-1]["old_status"] == "VALIDATED"
     and alert["status_history"][-1]["new_status"] == "FARMER_CONTACTED")


# ==============================================================
# TEST 6: Resolve Alert
# ==============================================================
section("TEST 6: Resolve Alert")

r = requests.patch(f"{BASE}/api/alerts/{alert_id}/resolve", json={
    "notes": "Farmer confirmed he stopped work. Situation resolved."
})
test("Resolve returns 200", r.status_code == 200)
alert = r.json()["alert"]
test("Status = RESOLVED", alert["status"] == "RESOLVED")
test("status_history has 4 entries", len(alert["status_history"]) == 4)
test("Full lifecycle in status_history",
     [h["new_status"] for h in alert["status_history"]]
     == ["PENDING_ASHA_REVIEW", "VALIDATED", "FARMER_CONTACTED", "RESOLVED"])


# ==============================================================
# TEST 7: ASHA Rejects Alert
# ==============================================================
section("TEST 7: ASHA Rejects Alert")

r = requests.post(f"{BASE}/api/alert", json={
    "farmer_name": "Sita Devi",
    "farmer_id": "sita_devi",
    "lat": 28.6, "lon": 77.2,
    "reason": "Pesticide drift risk - wind 18 km/h",
    "profile": "healthy_adult",
    "activity": "pesticide_spraying",
    "risk_level": "RED",
})
reject_id = r.json()["alert"]["alert_id"]

r = requests.patch(f"{BASE}/api/alerts/{reject_id}/reject", json={
    "notes": "False alarm - farmer is indoors today"
})
test("Reject returns 200", r.status_code == 200)
alert = r.json()["alert"]
test("Status = REJECTED", alert["status"] == "REJECTED")
test("status_history has 2 entries", len(alert["status_history"]) == 2)


# ==============================================================
# TEST 8: Rejected Alert Cannot Be Contacted
# ==============================================================
section("TEST 8: Rejected Alert Cannot Be Contacted")

r = requests.patch(f"{BASE}/api/alerts/{reject_id}/contact", json={})
test("Contact on REJECTED returns 409", r.status_code == 409)
detail = r.json().get("detail", "")
test("Error mentions REJECTED -> FARMER_CONTACTED",
     "REJECTED" in detail and "FARMER_CONTACTED" in detail)


# ==============================================================
# TEST 9: Invalid State Transitions
# ==============================================================
section("TEST 9: Invalid State Transitions")

# Fresh alert for transition tests
r = requests.post(f"{BASE}/api/alert", json={
    "farmer_name": "Transition Test",
    "farmer_id": "transition_test",
    "lat": 20.0, "lon": 80.0,
    "reason": "Testing invalid transitions",
    "profile": "healthy_adult",
    "activity": "general_work",
    "risk_level": "RED",
})
inv_id = r.json()["alert"]["alert_id"]

# PENDING -> RESOLVED  (skips validate + contact)
r = requests.patch(f"{BASE}/api/alerts/{inv_id}/resolve", json={})
test("PENDING -> RESOLVED blocked (409)", r.status_code == 409)

# PENDING -> FARMER_CONTACTED  (skips validate)
r = requests.patch(f"{BASE}/api/alerts/{inv_id}/contact", json={})
test("PENDING -> FARMER_CONTACTED blocked (409)", r.status_code == 409)

# Move to VALIDATED
requests.patch(f"{BASE}/api/alerts/{inv_id}/validate", json={})

# VALIDATED -> REJECTED
r = requests.patch(f"{BASE}/api/alerts/{inv_id}/reject", json={})
test("VALIDATED -> REJECTED blocked (409)", r.status_code == 409)

# VALIDATED -> RESOLVED  (skips contact)
r = requests.patch(f"{BASE}/api/alerts/{inv_id}/resolve", json={})
test("VALIDATED -> RESOLVED blocked (409)", r.status_code == 409)

# Move to FARMER_CONTACTED
requests.patch(f"{BASE}/api/alerts/{inv_id}/contact", json={})

# FARMER_CONTACTED -> VALIDATED  (backward)
r = requests.patch(f"{BASE}/api/alerts/{inv_id}/validate", json={})
test("FARMER_CONTACTED -> VALIDATED blocked (409)", r.status_code == 409)

# Move to RESOLVED
requests.patch(f"{BASE}/api/alerts/{inv_id}/resolve", json={})

# RESOLVED -> anything
r = requests.patch(f"{BASE}/api/alerts/{inv_id}/validate", json={})
test("RESOLVED -> VALIDATED blocked (409)", r.status_code == 409)

r = requests.patch(f"{BASE}/api/alerts/{inv_id}/contact", json={})
test("RESOLVED -> FARMER_CONTACTED blocked (409)", r.status_code == 409)

r = requests.patch(f"{BASE}/api/alerts/{inv_id}/resolve", json={})
test("RESOLVED -> RESOLVED blocked (409)", r.status_code == 409)


# ==============================================================
# TEST 10: Unknown Alert -> 404
# ==============================================================
section("TEST 10: Unknown Alert Returns 404")

fake_id = "00000000-0000-0000-0000-000000000000"
r = requests.get(f"{BASE}/api/alerts/{fake_id}")
test("GET unknown alert -> 404", r.status_code == 404)

r = requests.patch(f"{BASE}/api/alerts/{fake_id}/validate", json={})
test("PATCH validate unknown -> 404", r.status_code == 404)

r = requests.patch(f"{BASE}/api/alerts/{fake_id}/reject", json={})
test("PATCH reject unknown -> 404", r.status_code == 404)

r = requests.patch(f"{BASE}/api/alerts/{fake_id}/contact", json={})
test("PATCH contact unknown -> 404", r.status_code == 404)

r = requests.patch(f"{BASE}/api/alerts/{fake_id}/resolve", json={})
test("PATCH resolve unknown -> 404", r.status_code == 404)


# ==============================================================
# BONUS: List & Filter Endpoints
# ==============================================================
section("BONUS: List & Filter Endpoints")

r = requests.get(f"{BASE}/api/alerts")
test("GET /api/alerts returns list", r.status_code == 200 and "alerts" in r.json())
test("Response includes count", "count" in r.json())

r = requests.get(f"{BASE}/api/alerts", params={"status": "RESOLVED"})
test("Filter by status=RESOLVED works",
     r.status_code == 200
     and all(a["status"] == "RESOLVED" for a in r.json()["alerts"]))

r = requests.get(f"{BASE}/api/alerts/pending")
test("GET /api/alerts/pending works",
     r.status_code == 200
     and all(a["status"] == "PENDING_ASHA_REVIEW" for a in r.json()["alerts"]))


# ==============================================================
# SUMMARY
# ==============================================================
print(f"\n{'='*60}")
print(f"  RESULTS")
print(f"{'='*60}")
print(f"  Passed:  {passed}")
print(f"  Failed:  {failed}")
print(f"  Skipped: {skipped}")
print(f"  Total:   {passed + failed + skipped}")
print(f"{'='*60}")

if failed == 0:
    print(f"\n  ALL TESTS PASSED!\n")
else:
    print(f"\n  {failed} test(s) failed. Review output above.\n")
    sys.exit(1)

