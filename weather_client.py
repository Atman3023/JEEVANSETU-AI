"""
Live weather data client.

For the demo we use Open-Meteo (https://open-meteo.com) - it's free, requires
NO API key, and gives real hourly temperature/humidity/wind data anywhere in
India. This stands in for the IMD Gridded Data feed referenced in the deck.
When you get IMD API access later, only this file needs to change -
rule_engine.py and main.py don't care where the numbers come from.
"""

import httpx
from datetime import datetime
from rule_engine import HourReading

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

#real code
async def get_morning_readings(lat: float, lon: float) -> list[HourReading]:
    """Fetch today's early-morning (05:00-10:00) hourly forecast."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": "Asia/Kolkata",
        "forecast_days": 1,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    hourly = data["hourly"]
    times = hourly["time"]
    temps = hourly["temperature_2m"]
    hums = hourly["relative_humidity_2m"]
    winds = hourly["wind_speed_10m"]

    readings = []
    for i, t in enumerate(times):
        hour = datetime.fromisoformat(t).hour
        if 5 <= hour <= 10:  # farmer's working morning window
            label = datetime.fromisoformat(t).strftime("%H:%M")
            readings.append(HourReading(
                hour_label=label,
                temp_c=temps[i],
                humidity_pct=hums[i],
                wind_kmh=winds[i],
            ))
    return readings
