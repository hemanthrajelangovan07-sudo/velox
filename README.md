# 🚗 VeloxTelemetry

> A real-time vehicle operational data platform with AI-powered anomaly detection, time-range reporting, and CSV export.

Built for hackathon — backend in **FastAPI**, AI via **OpenRouter**, live dashboard in pure **HTML/JS**.

---

## 📁 Project Structure

```
vehicle-telemetry/
├── backend/
│   ├── main.py               ← FastAPI server (all API endpoints)
│   └── requirements.txt      ← Python dependencies
├── simulator/
│   ├── simulator.py          ← Simulates 5 live vehicles sending data
│   └── requirements.txt
├── dashboard/
│   └── index.html            ← Real-time web dashboard (open in browser)
└── README.md
```

---

## ⚙️ Features

| Feature | Description |
|---|---|
| 📡 Telemetry Ingestion | Accept speed, temperature, battery, fuel, RPM, GPS per vehicle |
| 🚘 Fleet Overview | See all vehicles with live latest snapshot |
| 📊 Time Range Reports | Reports for last 10 min, 30 min, 1h, 6h, 24h, 7 days |
| 📈 Live Charts | Real-time speed & temperature sparklines |
| 📡 Live Feed | Auto-updating feed with proper units (km/h, °C, %, L, rpm) |
| 🤖 AI Anomaly Detection | OpenRouter AI analyzes last 20 readings and flags issues |
| ⬇️ CSV Export | Download telemetry data for any vehicle and time range |
| 📝 Auto API Docs | Swagger UI auto-generated at `/docs` |

---

## 🚀 Setup & Run

### Prerequisites
- Python 3.10 or higher → https://python.org
- An OpenRouter API key → https://openrouter.ai

---

### Step 1 — Install backend dependencies
**PowerShell (Windows):**
```powershell
cd backend
pip install -r requirements.txt
```
**Bash/zsh (Linux/Mac):**
```zsh
cd backend 
python -m venv .venv
source .venv/bin/activate 
pip install -r requirements.txt 
```
>  ⚠️ Incase of errors while installing the requirements.txt packages, try installing it seperately i.e. using "sudo pacman -S python-'packagename'" or your preferred package manager 

>  ⚠️ Some Operating systems like Arch-linux, etc. might need to install httpx to run the program. 

---

### Step 2 — Set your OpenRouter API key

**PowerShell (Windows):**
```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-your-key-here"
```

**Mac/Linux:**
```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
```

> ⚠️ Do this in the **same terminal** where you start the server. Don't close it.

---

### Step 3 — Start the backend server

```powershell
cd backend
uvicorn main:app --reload
```

Server runs at: `http://localhost:8000`

---

### Step 4 — Run the vehicle simulator

Open a **new terminal** and run:

```powershell
cd simulator
pip install -r requirements.txt
python simulator.py
```
>  ⚠️ Incase of errors while installing the requirements.txt packages, try installing it seperately i.e. using "sudo pacman -S python-'packagename'" or your preferred package manager 



This simulates **5 vehicles** sending live telemetry every 2 seconds:
- VH-001 Tesla Model 3 (EV)
- VH-002 Toyota Camry (Petrol)
- VH-003 Ford Transit Van (Diesel)
- VH-004 Tata Nexon EV
- VH-005 Honda City Hybrid

The simulator also randomly injects anomalies (overheat, overspeed, low battery) to make AI alerts interesting.

---

### Step 5 — Open the Dashboard

Just double-click `dashboard/index.html` or open it in your browser.

Click **CONNECT** → vehicles appear → click any vehicle to see detail, charts, reports, and AI alerts.

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/telemetry` | Send vehicle telemetry data |
| `GET` | `/telemetry/{vehicle_id}` | Recent readings for a vehicle |
| `GET` | `/vehicles` | All vehicles (latest snapshot each) |
| `GET` | `/stats/{vehicle_id}` | Aggregated stats (avg/max/min) |
| `GET` | `/report/{vehicle_id}?range=1h` | Detailed time-range report |
| `GET` | `/export/{vehicle_id}/csv?range=1h` | Download CSV file |
| `GET` | `/alerts/{vehicle_id}` | AI anomaly detection |
| `DELETE` | `/telemetry/{vehicle_id}` | Clear all data for a vehicle |

### Time range options
`10m` · `30m` · `1h` · `6h` · `24h` · `7d`

---

## 📬 Example API Usage

### Send telemetry data

**PowerShell:**
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/telemetry" `
  -ContentType "application/json" `
  -Body '{"vehicle_id":"VH-TEST","speed":95.0,"temperature":82.0,"battery_pct":65.0,"fuel_level":30.0,"engine_rpm":3200}'
```

**curl (Mac/Linux):**
```bash
curl -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{"vehicle_id":"VH-TEST","speed":95.0,"temperature":82.0,"battery_pct":65.0,"fuel_level":30.0,"engine_rpm":3200}'
```

---

### Get recent telemetry

```powershell
Invoke-RestMethod "http://localhost:8000/telemetry/VH-TEST"
```

---

### Get time range report

```powershell
Invoke-RestMethod "http://localhost:8000/report/VH-TEST?range=1h"
```

---

### Download CSV

Open in browser — file downloads automatically:
```
http://localhost:8000/export/VH-TEST/csv?range=24h
```

---

### Trigger AI anomaly detection

```powershell
Invoke-RestMethod "http://localhost:8000/alerts/VH-TEST"
```

**Example response:**
```json
{
  "risk_level": "HIGH",
  "alerts": [
    {
      "metric": "speed",
      "issue": "Speed consistently above 130 km/h, peaking at 148 km/h",
      "recommendation": "Reduce speed immediately to safe limits"
    },
    {
      "metric": "temperature",
      "issue": "Engine temperature critically high at 108.5°C, risk of engine failure",
      "recommendation": "Pull over and allow engine to cool, check coolant"
    },
    {
      "metric": "battery_pct",
      "issue": "Battery dangerously low at 5.9%",
      "recommendation": "Find nearest charging station immediately"
    }
  ],
  "summary": "Vehicle VH-TEST is in critical condition with overspeed, overheating, and near-empty battery."
}
```

---

## 🤖 AI Anomaly Detection — How it works

1. The `/alerts/{vehicle_id}` endpoint fetches the last 20 readings from the database
2. It sends the data to **OpenRouter** using the `nvidia/nemotron-3-nano-30b-a3b:free` model
3. The AI checks for: overspeed (>130 km/h), overheating (>100°C), low battery (<15%), over-revving (>6000 RPM), sudden spikes/drops
4. Returns a structured JSON with `risk_level` (LOW / MEDIUM / HIGH), specific `alerts`, and a `summary`

**To test AI alerts with dangerous data:**
```powershell
# Inject bad readings
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/telemetry" -ContentType "application/json" -Body '{"vehicle_id":"VH-TEST","speed":148.0,"temperature":108.5,"battery_pct":7.0,"engine_rpm":6900}'
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/telemetry" -ContentType "application/json" -Body '{"vehicle_id":"VH-TEST","speed":142.0,"temperature":105.0,"battery_pct":6.0,"engine_rpm":6700}'
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/telemetry" -ContentType "application/json" -Body '{"vehicle_id":"VH-TEST","speed":139.0,"temperature":103.0,"battery_pct":5.5,"engine_rpm":6500}'

# Trigger AI
Invoke-RestMethod "http://localhost:8000/alerts/VH-TEST"
```

---

## 📖 Interactive API Docs

FastAPI auto-generates full Swagger documentation.

Open in browser: **`http://localhost:8000/docs`**

You can test every endpoint directly in the browser — great to show judges.

---

## 🛠️ Telemetry Data Model

```json
{
  "vehicle_id":  "VH-001",
  "speed":       95.3,
  "temperature": 82.1,
  "battery_pct": 64.5,
  "fuel_level":  28.4,
  "latitude":    12.9716,
  "longitude":   80.2709,
  "engine_rpm":  3200.0,
  "extra": {
    "vehicle_name": "Tesla Model 3",
    "vehicle_type": "EV"
  }
}
```

All fields except `vehicle_id` are optional. The `extra` field accepts any custom key-value data.

---

## 🔧 Troubleshooting

**Server won't start**
```powershell
pip install fastapi uvicorn httpx pydantic
```

**AI alerts say "OPENROUTER_API_KEY is not set"**
```powershell
# Stop server (Ctrl+C), then:
$env:OPENROUTER_API_KEY="sk-or-v1-your-key-here"
uvicorn main:app --reload
```

**AI alerts say "Invalid API key"**
→ Go to https://openrouter.ai → Keys → create a new key → use that

**Dashboard shows ERROR**
→ Make sure the backend server is running in another terminal
→ Check the API URL in the dashboard input bar matches your port

**Port already in use**
```powershell
uvicorn main:app --reload --port 8001
```
Then update the URL in the dashboard to `http://localhost:8001`

---

## 🏆 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python + FastAPI |
| Database | SQLite (zero setup) |
| AI Provider | OpenRouter (nvidia/nemotron-3-nano-30b-a3b:free) |
| HTTP Client | httpx (async) |
| Dashboard | HTML + CSS + Chart.js |
| Simulator | Python + requests |

---

*Built for hackathon — VeloxTelemetry v3.0*
