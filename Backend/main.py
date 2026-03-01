from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import sqlite3
import json
import csv
import io
import os
import re
import httpx

app = FastAPI(title="Vehicle Telemetry API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "telemetry.db"

# ── Database Setup ────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id  TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            speed       REAL,
            temperature REAL,
            battery_pct REAL,
            fuel_level  REAL,
            latitude    REAL,
            longitude   REAL,
            engine_rpm  REAL,
            extra       TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ── Time Range Helper ─────────────────────────────────────────────────────────

RANGE_MAP = {
    "10m": timedelta(minutes=10),
    "30m": timedelta(minutes=30),
    "1h":  timedelta(hours=1),
    "6h":  timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d":  timedelta(days=7),
}

def get_since(range_str: str) -> str:
    delta = RANGE_MAP.get(range_str)
    if not delta:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid range. Use one of: {list(RANGE_MAP.keys())}"
        )
    return (datetime.utcnow() - delta).isoformat()

# ── Models ────────────────────────────────────────────────────────────────────

class TelemetryInput(BaseModel):
    vehicle_id:  str
    speed:       Optional[float] = None   # km/h
    temperature: Optional[float] = None   # Celsius
    battery_pct: Optional[float] = None   # 0-100 %
    fuel_level:  Optional[float] = None   # litres
    latitude:    Optional[float] = None
    longitude:   Optional[float] = None
    engine_rpm:  Optional[float] = None
    extra:       Optional[dict]  = None

# ── OpenRouter AI Helper ──────────────────────────────────────────────────────

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"

async def call_openrouter(prompt: str) -> str:
    """
    Call OpenRouter API and return the assistant's text response.
    Raises ValueError with a clear message on any failure.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set. Set it in PowerShell and restart the server.")

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "reasoning": {"enabled": True}
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            content=json.dumps(payload),
        )

    if resp.status_code == 401:
        raise ValueError("Invalid OpenRouter API key. Check your OPENROUTER_API_KEY.")
    if resp.status_code == 429:
        raise ValueError("OpenRouter rate limit hit. Wait a moment and try again.")
    if resp.status_code != 200:
        raise ValueError(f"OpenRouter API error {resp.status_code}: {resp.text[:200]}")

    result = resp.json()

    # Extract text from response
    choices = result.get("choices", [])
    if not choices:
        raise ValueError("OpenRouter returned empty choices.")

    message = choices[0].get("message", {})
    text = message.get("content", "")

    if not text:
        raise ValueError("OpenRouter returned empty content.")

    return text.strip()

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "message": "Vehicle Telemetry API v3 is running 🚗",
        "ai_provider": "OpenRouter",
        "model": OPENROUTER_MODEL
    }


# ── Ingest ────────────────────────────────────────────────────────────────────

@app.post("/telemetry", status_code=201)
def ingest_telemetry(data: TelemetryInput):
    """Ingest a telemetry reading from a vehicle."""
    conn = get_db()
    conn.execute("""
        INSERT INTO telemetry
            (vehicle_id, timestamp, speed, temperature, battery_pct,
             fuel_level, latitude, longitude, engine_rpm, extra)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        data.vehicle_id,
        datetime.utcnow().isoformat(),
        data.speed, data.temperature, data.battery_pct,
        data.fuel_level, data.latitude, data.longitude, data.engine_rpm,
        json.dumps(data.extra) if data.extra else None,
    ))
    conn.commit()
    conn.close()
    return {"status": "ok", "vehicle_id": data.vehicle_id}


# ── Recent Telemetry ──────────────────────────────────────────────────────────

@app.get("/telemetry/{vehicle_id}")
def get_recent_telemetry(vehicle_id: str, limit: int = 50):
    """Get the most recent N telemetry readings for a vehicle."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM telemetry WHERE vehicle_id = ?
        ORDER BY timestamp DESC LIMIT ?
    """, (vehicle_id, limit)).fetchall()
    conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for vehicle '{vehicle_id}'")
    return [dict(r) for r in rows]


# ── Fleet Overview ────────────────────────────────────────────────────────────

@app.get("/vehicles")
def list_vehicles():
    """List all vehicles with their latest telemetry snapshot."""
    conn = get_db()
    rows = conn.execute("""
        SELECT t.* FROM telemetry t
        INNER JOIN (
            SELECT vehicle_id, MAX(timestamp) as latest
            FROM telemetry GROUP BY vehicle_id
        ) sub ON t.vehicle_id = sub.vehicle_id AND t.timestamp = sub.latest
        ORDER BY t.vehicle_id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/stats/{vehicle_id}")
def vehicle_stats(vehicle_id: str):
    """Aggregated stats for a vehicle."""
    conn = get_db()
    row = conn.execute("""
        SELECT
            COUNT(*)         AS total_readings,
            AVG(speed)       AS avg_speed,
            MAX(speed)       AS max_speed,
            AVG(temperature) AS avg_temp,
            MAX(temperature) AS max_temp,
            MIN(battery_pct) AS min_battery,
            AVG(battery_pct) AS avg_battery,
            MIN(timestamp)   AS first_seen,
            MAX(timestamp)   AS last_seen
        FROM telemetry WHERE vehicle_id = ?
    """, (vehicle_id,)).fetchone()
    conn.close()
    if not row or row["total_readings"] == 0:
        raise HTTPException(status_code=404, detail=f"No data for vehicle '{vehicle_id}'")
    return dict(row)


# ── Time Range Report ─────────────────────────────────────────────────────────

@app.get("/report/{vehicle_id}")
def vehicle_report(
    vehicle_id: str,
    range: str = Query(default="1h", description="Time range: 10m, 30m, 1h, 6h, 24h, 7d")
):
    """Detailed report for a vehicle over a given time range."""
    since = get_since(range)
    conn  = get_db()

    rows = conn.execute("""
        SELECT * FROM telemetry
        WHERE vehicle_id = ? AND timestamp >= ?
        ORDER BY timestamp ASC
    """, (vehicle_id, since)).fetchall()

    stats = conn.execute("""
        SELECT
            COUNT(*)         AS total_readings,
            AVG(speed)       AS avg_speed,
            MAX(speed)       AS max_speed,
            MIN(speed)       AS min_speed,
            AVG(temperature) AS avg_temp,
            MAX(temperature) AS max_temp,
            MIN(temperature) AS min_temp,
            AVG(battery_pct) AS avg_battery,
            MIN(battery_pct) AS min_battery,
            AVG(fuel_level)  AS avg_fuel,
            MIN(fuel_level)  AS min_fuel,
            AVG(engine_rpm)  AS avg_rpm,
            MAX(engine_rpm)  AS max_rpm,
            MIN(timestamp)   AS period_start,
            MAX(timestamp)   AS period_end
        FROM telemetry
        WHERE vehicle_id = ? AND timestamp >= ?
    """, (vehicle_id, since)).fetchone()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for '{vehicle_id}' in last {range}")

    return {
        "vehicle_id":   vehicle_id,
        "range":        range,
        "period_start": stats["period_start"],
        "period_end":   stats["period_end"],
        "summary": {
            "total_readings": stats["total_readings"],
            "speed_kmh":     {"avg": round(stats["avg_speed"] or 0, 1),   "max": round(stats["max_speed"] or 0, 1),   "min": round(stats["min_speed"] or 0, 1)},
            "temperature_c": {"avg": round(stats["avg_temp"] or 0, 1),    "max": round(stats["max_temp"] or 0, 1),    "min": round(stats["min_temp"] or 0, 1)},
            "battery_pct":   {"avg": round(stats["avg_battery"] or 0, 1), "min": round(stats["min_battery"] or 0, 1)},
            "fuel_litres":   {"avg": round(stats["avg_fuel"] or 0, 2),    "min": round(stats["min_fuel"] or 0, 2)} if stats["avg_fuel"] else None,
            "engine_rpm":    {"avg": round(stats["avg_rpm"] or 0, 0),     "max": round(stats["max_rpm"] or 0, 0)},
        },
        "readings": [dict(r) for r in rows],
    }


# ── CSV Export ────────────────────────────────────────────────────────────────

@app.get("/export/{vehicle_id}/csv")
def export_csv(
    vehicle_id: str,
    range: str = Query(default="1h", description="Time range: 10m, 30m, 1h, 6h, 24h, 7d")
):
    """Export vehicle telemetry as a downloadable CSV file."""
    since = get_since(range)
    conn  = get_db()
    rows  = conn.execute("""
        SELECT id, vehicle_id, timestamp, speed, temperature,
               battery_pct, fuel_level, latitude, longitude, engine_rpm
        FROM telemetry
        WHERE vehicle_id = ? AND timestamp >= ?
        ORDER BY timestamp ASC
    """, (vehicle_id, since)).fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for '{vehicle_id}' in last {range}")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Vehicle ID", "Timestamp (UTC)",
        "Speed (km/h)", "Temperature (°C)", "Battery (%)",
        "Fuel Level (L)", "Latitude", "Longitude", "Engine RPM"
    ])
    for row in rows:
        writer.writerow([
            row["id"], row["vehicle_id"], row["timestamp"],
            row["speed"], row["temperature"], row["battery_pct"],
            row["fuel_level"], row["latitude"], row["longitude"], row["engine_rpm"]
        ])

    output.seek(0)
    filename = f"{vehicle_id}_{range}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── AI Anomaly Alerts (OpenRouter) ────────────────────────────────────────────

@app.get("/alerts/{vehicle_id}")
async def get_ai_alerts(vehicle_id: str):
    """Use OpenRouter AI to detect anomalies in the last 20 readings."""

    # Check key early
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return {
            "risk_level": "UNKNOWN",
            "alerts": [],
            "summary": "❌ OPENROUTER_API_KEY is not set. Set it in PowerShell and restart the server."
        }

    conn = get_db()
    rows = conn.execute("""
        SELECT speed, temperature, battery_pct, fuel_level, engine_rpm, timestamp
        FROM telemetry WHERE vehicle_id = ?
        ORDER BY timestamp DESC LIMIT 20
    """, (vehicle_id,)).fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for vehicle '{vehicle_id}'")

    readings = [dict(r) for r in rows]

    prompt = f"""You are a vehicle diagnostics AI. Analyze this telemetry data for vehicle '{vehicle_id}'.

Data (most recent first):
{json.dumps(readings, indent=2)}

Check these thresholds:
- Speed > 130 km/h = dangerous overspeed
- Temperature > 100 C = engine overheating  
- Battery < 15% = critically low charge
- RPM > 6000 = over-revving engine
- Sudden spikes or drops in any metric = anomaly

You MUST reply with ONLY a valid JSON object. No explanation. No markdown. No code fences. Just raw JSON.

Use this exact format:
{{"risk_level":"LOW","alerts":[{{"metric":"field_name","issue":"describe what is wrong","recommendation":"what the driver should do"}}],"summary":"one sentence overall summary"}}

Rules:
- risk_level must be exactly: LOW, MEDIUM, or HIGH
- alerts is a list (can be empty if everything is fine)
- If no issues found: {{"risk_level":"LOW","alerts":[],"summary":"All vehicle metrics are within safe operating ranges."}}"""

    try:
        text = await call_openrouter(prompt)

        # Strip markdown code fences if AI adds them
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

        # Extract JSON object even if there's extra text around it
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        parsed = json.loads(text)

        # Validate required keys exist
        if "risk_level" not in parsed:
            parsed["risk_level"] = "UNKNOWN"
        if "alerts" not in parsed:
            parsed["alerts"] = []
        if "summary" not in parsed:
            parsed["summary"] = "Analysis complete."

        return parsed

    except json.JSONDecodeError:
        return {
            "risk_level": "UNKNOWN",
            "alerts": [],
            "summary": f"❌ AI returned invalid JSON. Raw response: {text[:150]}"
        }
    except ValueError as e:
        return {
            "risk_level": "UNKNOWN",
            "alerts": [],
            "summary": f"❌ {str(e)}"
        }
    except Exception as e:
        return {
            "risk_level": "UNKNOWN",
            "alerts": [],
            "summary": f"❌ Unexpected error: {str(e)}"
        }


# ── Clear Data ────────────────────────────────────────────────────────────────

@app.delete("/telemetry/{vehicle_id}")
def clear_vehicle_data(vehicle_id: str):
    """Clear all data for a vehicle."""
    conn = get_db()
    conn.execute("DELETE FROM telemetry WHERE vehicle_id = ?", (vehicle_id,))
    conn.commit()
    conn.close()
    return {"status": "cleared", "vehicle_id": vehicle_id}
