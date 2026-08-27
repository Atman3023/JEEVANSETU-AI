"""
JeevanSetu AI - History Store (SQLite-backed)

Persists recommendation history so that farmer history survives backend restarts.
Uses SQLite for lightweight, zero-dependency storage.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "jeevansetu_history.db"


def init_db():
    """Create the history table if it doesn't exist."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recommendation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_id TEXT NOT NULL,
            activity TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            safe_window TEXT,
            reason TEXT,
            weather_json TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_history_farmer
        ON recommendation_history(farmer_id)
    """)
    conn.commit()
    conn.close()


def add_history(
    farmer_id: str,
    activity: str,
    risk_level: str,
    safe_window: str = "",
    reason: str = "",
    weather_data: dict = None,
) -> dict:
    """
    Save a recommendation to persistent history.
    Returns the saved record as a dict.
    """
    now = datetime.utcnow().isoformat()
    weather_json = json.dumps(weather_data) if weather_data else "{}"

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute(
        """
        INSERT INTO recommendation_history
            (farmer_id, activity, risk_level, safe_window, reason, weather_json, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (farmer_id, activity, risk_level, safe_window, reason, weather_json, now),
    )
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": record_id,
        "farmer_id": farmer_id,
        "activity": activity,
        "risk_level": risk_level,
        "safe_window": safe_window,
        "reason": reason,
        "weather": weather_data or {},
        "timestamp": now,
    }


def get_history(farmer_id: str, limit: int = 50) -> list:
    """
    Retrieve the most recent recommendations for a farmer.
    Returns list of dicts, most recent first.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, farmer_id, activity, risk_level, safe_window,
               reason, weather_json, timestamp
        FROM recommendation_history
        WHERE farmer_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (farmer_id, limit),
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        weather = {}
        try:
            weather = json.loads(row["weather_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            pass

        results.append({
            "id": row["id"],
            "farmer_id": row["farmer_id"],
            "activity": row["activity"],
            "risk_level": row["risk_level"],
            "safe_window": row["safe_window"],
            "reason": row["reason"],
            "weather": weather,
            "timestamp": row["timestamp"],
        })

    return results
