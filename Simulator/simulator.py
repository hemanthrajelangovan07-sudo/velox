"""
Vehicle Telemetry Simulator
----------------------------
Simulates 5 vehicles sending live data to your API.
Run this AFTER starting the backend server.

Usage:
    python simulator.py
    python simulator.py --url http://localhost:8000 --interval 2
"""

import requests
import random
import time
import math
import argparse
from datetime import datetime

VEHICLES = [
    {"id": "VH-001", "type": "EV",      "name": "Tesla Model 3"},
    {"id": "VH-002", "type": "Petrol",  "name": "Toyota Camry"},
    {"id": "VH-003", "type": "Diesel",  "name": "Ford Transit Van"},
    {"id": "VH-004", "type": "EV",      "name": "Tata Nexon EV"},
    {"id": "VH-005", "type": "Hybrid",  "name": "Honda City Hybrid"},
]

# Base state per vehicle (persists between ticks)
state = {
    v["id"]: {
        "speed":       random.uniform(30, 80),
        "temperature": random.uniform(70, 85),
        "battery_pct": random.uniform(50, 90),
        "fuel_level":  random.uniform(20, 60),
        "engine_rpm":  random.uniform(1500, 3000),
        "lat":         12.9716 + random.uniform(-0.05, 0.05),
        "lon":         80.2709 + random.uniform(-0.05, 0.05),
        "tick":        0,
        "anomaly_countdown": random.randint(20, 60),
    }
    for v in VEHICLES
}


def next_reading(vehicle):
    vid = vehicle["id"]
    s = state[vid]
    s["tick"] += 1

    # Natural drift
    s["speed"]       = max(0,   min(160, s["speed"]       + random.uniform(-5, 5)))
    s["temperature"] = max(60,  min(105, s["temperature"] + random.uniform(-1, 1.5)))
    s["engine_rpm"]  = max(800, min(7000, s["speed"] * 38 + random.uniform(-200, 200)))
    s["lat"]        += random.uniform(-0.0005, 0.0005)
    s["lon"]        += random.uniform(-0.0005, 0.0005)

    if vehicle["type"] == "EV":
        drain = s["speed"] * 0.0003
        s["battery_pct"] = max(5, s["battery_pct"] - drain + random.uniform(-0.1, 0.2))
        s["fuel_level"]  = None
    else:
        s["fuel_level"]  = max(0, s["fuel_level"] - random.uniform(0.01, 0.05))
        s["battery_pct"] = None

    # Occasional anomaly injection for drama in the demo
    s["anomaly_countdown"] -= 1
    if s["anomaly_countdown"] <= 0:
        anomaly = random.choice(["overheat", "overspeed", "low_battery"])
        if anomaly == "overheat":
            s["temperature"] = random.uniform(102, 110)
            print(f"  🔴 ANOMALY injected for {vid}: overheating ({s['temperature']:.1f}°C)")
        elif anomaly == "overspeed":
            s["speed"] = random.uniform(135, 155)
            print(f"  🔴 ANOMALY injected for {vid}: overspeed ({s['speed']:.1f} km/h)")
        elif anomaly == "low_battery" and vehicle["type"] == "EV":
            s["battery_pct"] = random.uniform(5, 12)
            print(f"  🔴 ANOMALY injected for {vid}: low battery ({s['battery_pct']:.1f}%)")
        s["anomaly_countdown"] = random.randint(30, 80)

    return {
        "vehicle_id":  vid,
        "speed":       round(s["speed"], 1),
        "temperature": round(s["temperature"], 1),
        "battery_pct": round(s["battery_pct"], 1) if s["battery_pct"] else None,
        "fuel_level":  round(s["fuel_level"], 2)  if s["fuel_level"] else None,
        "engine_rpm":  round(s["engine_rpm"], 0),
        "latitude":    round(s["lat"], 6),
        "longitude":   round(s["lon"], 6),
        "extra":       {"vehicle_type": vehicle["type"], "vehicle_name": vehicle["name"]},
    }


def run(api_url: str, interval: float):
    print(f"\n🚗  Vehicle Telemetry Simulator")
    print(f"📡  Sending to: {api_url}")
    print(f"⏱   Interval: {interval}s\n")

    tick = 0
    while True:
        tick += 1
        print(f"── Tick {tick} @ {datetime.now().strftime('%H:%M:%S')} ──")
        for vehicle in VEHICLES:
            reading = next_reading(vehicle)
            try:
                r = requests.post(f"{api_url}/telemetry", json=reading, timeout=5)
                status = "✅" if r.status_code == 201 else "❌"
                print(f"  {status} {vehicle['id']} ({vehicle['name']}) "
                      f"spd={reading['speed']} km/h  "
                      f"temp={reading['temperature']}°C  "
                      f"rpm={reading['engine_rpm']}")
            except requests.exceptions.ConnectionError:
                print(f"  ❌ Cannot connect to {api_url}. Is the server running?")
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",      default="http://localhost:8000")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    run(args.url, args.interval)
