import os
import uuid
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database
from database import get_connection
import geo_utils
from confidence_engine import calculate_confidence, determine_status
import routing_engine

app = FastAPI(title="RoadEye API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# Background decay task
async def periodic_decay_checker():
    while True:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hazards WHERE status IN ('ACTIVE', 'LOW_CONFIDENCE')")
            rows = cursor.fetchall()
            updated_any = False
            for row in rows:
                new_conf = calculate_confidence(
                    base_confidence=50,
                    confirm_count=row["confirm_count"],
                    reject_count=row["reject_count"],
                    created_at_iso=row["created_at"],
                    has_photo=bool(row["image_url"])
                )
                new_status = determine_status(new_conf, row["reject_count"], row["confirm_count"])
                if new_conf != row["confidence_score"] or new_status != row["status"]:
                    cursor.execute("""
                        UPDATE hazards SET confidence_score = ?, status = ?, updated_at = ?
                        WHERE id = ?
                    """, (new_conf, new_status, datetime.now(timezone.utc).isoformat(), row["id"]))
                    updated_any = True
            conn.commit()
            conn.close()

            if updated_any:
                await manager.broadcast({"type": "HAZARDS_REFRESHED"})
        except Exception as e:
            print(f"[Decay Error] {e}")

        await asyncio.sleep(60) # Check every 60 seconds

@app.on_event("startup")
async def startup_event():
    database.init_db()
    database.seed_sample_data()
    asyncio.create_task(periodic_decay_checker())

# Pydantic Schemas
class RouteRequest(BaseModel):
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float

class VerificationRequest(BaseModel):
    voter_id: str
    is_still_there: bool

# API Endpoints

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>RoadEye Core Server Running. Missing index.html</h1>")

@app.get("/api/hazards")
async def get_all_hazards(include_expired: bool = False):
    conn = get_connection()
    cursor = conn.cursor()
    if include_expired:
        cursor.execute("SELECT * FROM hazards ORDER BY created_at DESC")
    else:
        cursor.execute("SELECT * FROM hazards WHERE status IN ('ACTIVE', 'LOW_CONFIDENCE') ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/hazards/nearby")
async def get_nearby_hazards(lat: float, lon: float, radius: float = 2000.0):
    """Returns hazards within radius (meters), calculating precise haversine distance."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hazards WHERE status IN ('ACTIVE', 'LOW_CONFIDENCE')")
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        h = dict(r)
        d = geo_utils.haversine_distance(lat, lon, h["latitude"], h["longitude"])
        if d <= radius:
            h["distance_meters"] = round(d, 1)
            results.append(h)

    results.sort(key=lambda x: x["distance_meters"])
    return results

@app.post("/api/hazards")
async def create_hazard(
    latitude: float = Form(...),
    longitude: float = Form(...),
    category: str = Form(...),
    severity: str = Form(...),
    description: str = Form(""),
    reporter_id: str = Form("anonymous-user"),
    photo: Optional[UploadFile] = File(None)
):
    now = datetime.now(timezone.utc)
    hazard_id = str(uuid.uuid4())
    image_url = ""

    if photo and photo.filename:
        filename = f"{hazard_id}_{photo.filename}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(await photo.read())
        image_url = f"/uploads/{filename}"

    base_conf = 45 if severity == "Moderate" else (65 if severity == "Critical" else 35)
    expires_at = (now + timedelta(hours=24)).isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    # Check reporter reputation
    cursor.execute("SELECT reputation_score FROM users WHERE id = ?", (reporter_id,))
    u = cursor.fetchone()
    rep = u["reputation_score"] if u else 50

    conf_score = calculate_confidence(
        base_confidence=base_conf,
        confirm_count=1,
        reject_count=0,
        created_at_iso=now.isoformat(),
        reporter_reputation=rep,
        has_photo=bool(image_url)
    )

    status = determine_status(conf_score, 0, 1)

    cursor.execute("""
        INSERT INTO hazards (id, reporter_id, latitude, longitude, category, severity, description,
                             image_url, confidence_score, status, created_at, updated_at, expires_at,
                             confirm_count, reject_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
    """, (hazard_id, reporter_id, latitude, longitude, category, severity, description,
          image_url, conf_score, status, now.isoformat(), now.isoformat(), expires_at))

    # Update user report count
    cursor.execute("""
        INSERT INTO users (id, username, reputation_score, reports_count, helpful_votes, created_at)
        VALUES (?, ?, 50, 1, 0, ?)
        ON CONFLICT(id) DO UPDATE SET reports_count = reports_count + 1
    """, (reporter_id, f"User_{reporter_id[:6]}", now.isoformat()))

    conn.commit()
    conn.close()

    hazard_data = {
        "id": hazard_id,
        "reporter_id": reporter_id,
        "latitude": latitude,
        "longitude": longitude,
        "category": category,
        "severity": severity,
        "description": description,
        "image_url": image_url,
        "confidence_score": conf_score,
        "status": status,
        "created_at": now.isoformat(),
        "confirm_count": 1,
        "reject_count": 0
    }

    # Broadcast real-time hazard notification
    await manager.broadcast({
        "type": "NEW_HAZARD",
        "hazard": hazard_data
    })

    return hazard_data

@app.post("/api/hazards/{hazard_id}/verify")
async def verify_hazard(hazard_id: str, payload: VerificationRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hazards WHERE id = ?", (hazard_id,))
    hazard = cursor.fetchone()
    if not hazard:
        conn.close()
        raise HTTPException(status_code=404, detail="Hazard not found")

    now = datetime.now(timezone.utc)
    v_id = str(uuid.uuid4())

    try:
        cursor.execute("""
            INSERT INTO hazard_verifications (id, hazard_id, voter_id, is_still_there, voted_at)
            VALUES (?, ?, ?, ?, ?)
        """, (v_id, hazard_id, payload.voter_id, 1 if payload.is_still_there else 0, now.isoformat()))
    except Exception:
        # User already voted, update vote
        cursor.execute("""
            UPDATE hazard_verifications SET is_still_there = ?, voted_at = ?
            WHERE hazard_id = ? AND voter_id = ?
        """, (1 if payload.is_still_there else 0, now.isoformat(), hazard_id, payload.voter_id))

    # Recalculate confirm / reject count
    cursor.execute("SELECT COUNT(*) as confirms FROM hazard_verifications WHERE hazard_id = ? AND is_still_there = 1", (hazard_id,))
    confirms = cursor.fetchone()["confirms"] + 1 # +1 initial author
    cursor.execute("SELECT COUNT(*) as rejects FROM hazard_verifications WHERE hazard_id = ? AND is_still_there = 0", (hazard_id,))
    rejects = cursor.fetchone()["rejects"]

    # Compute new confidence
    new_conf = calculate_confidence(
        base_confidence=50,
        confirm_count=confirms,
        reject_count=rejects,
        created_at_iso=hazard["created_at"],
        has_photo=bool(hazard["image_url"])
    )
    new_status = determine_status(new_conf, rejects, confirms)

    cursor.execute("""
        UPDATE hazards SET confidence_score = ?, status = ?, confirm_count = ?, reject_count = ?, updated_at = ?
        WHERE id = ?
    """, (new_conf, new_status, confirms, rejects, now.isoformat(), hazard_id))

    conn.commit()
    conn.close()

    update_payload = {
        "id": hazard_id,
        "confidence_score": new_conf,
        "status": new_status,
        "confirm_count": confirms,
        "reject_count": rejects
    }

    await manager.broadcast({
        "type": "HAZARD_VERIFIED",
        "update": update_payload
    })

    return update_payload

@app.get("/api/geocode")
async def geocode_address(query: str):
    """Geocode search query to lat/lon coordinates using OpenStreetMap Nominatim with robust fallback."""
    if not query or len(query.strip()) < 2:
        return []

    # Quick pre-mapped Indian localities for instantaneous autocomplete
    KNOWN_PLACES = {
        "virar": {"lat": 19.4564, "lon": 72.8105, "name": "Virar, Palghar, Maharashtra"},
        "dadar": {"lat": 19.0178, "lon": 72.8478, "name": "Dadar, Mumbai, Maharashtra"},
        "mira road": {"lat": 19.2812, "lon": 72.8560, "name": "Mira Road, Thane, Maharashtra"},
        "andheri": {"lat": 19.1136, "lon": 72.8697, "name": "Andheri East, Mumbai, Maharashtra"},
        "borivali": {"lat": 19.2307, "lon": 72.8567, "name": "Borivali West, Mumbai, Maharashtra"},
        "bandra": {"lat": 19.0596, "lon": 72.8295, "name": "Bandra West, Mumbai, Maharashtra"},
        "thane": {"lat": 19.2183, "lon": 72.9781, "name": "Thane City, Maharashtra"},
        "connaught place": {"lat": 28.6289, "lon": 77.2065, "name": "Connaught Place, New Delhi"},
        "india gate": {"lat": 28.6129, "lon": 77.2295, "name": "India Gate, New Delhi"}
    }

    q_lower = query.strip().lower()
    local_matches = []
    for k, v in KNOWN_PLACES.items():
        if k in q_lower or q_lower in k:
            local_matches.append({
                "display_name": v["name"],
                "lat": v["lat"],
                "lon": v["lon"]
            })

    try:
        import urllib.request, urllib.parse, json
        encoded = urllib.parse.quote(query.strip())
        url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=5"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RoadEyeApp/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            results = [
                {
                    "display_name": item["display_name"],
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"])
                }
                for item in data
            ]
            if results:
                return results
    except Exception as e:
        print(f"[Geocode Error] {e}")

    return local_matches

@app.post("/api/routes/calculate")
async def calculate_route(payload: RouteRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hazards WHERE status IN ('ACTIVE', 'LOW_CONFIDENCE')")
    hazards = [dict(r) for r in cursor.fetchall()]
    conn.close()

    result = await routing_engine.calculate_safe_navigation(
        start_lat=payload.start_lat,
        start_lon=payload.start_lon,
        end_lat=payload.end_lat,
        end_lon=payload.end_lon,
        hazards=hazards
    )
    return result

@app.get("/api/stats")
async def get_system_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM hazards")
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as active FROM hazards WHERE status = 'ACTIVE'")
    active = cursor.fetchone()["active"]

    cursor.execute("SELECT COUNT(*) as critical FROM hazards WHERE severity = 'Critical' AND status = 'ACTIVE'")
    critical = cursor.fetchone()["critical"]

    cursor.execute("SELECT COUNT(*) as resolved FROM hazards WHERE status = 'RESOLVED'")
    resolved = cursor.fetchone()["resolved"]

    cursor.execute("SELECT COUNT(*) as expired FROM hazards WHERE status = 'EXPIRED'")
    expired = cursor.fetchone()["expired"]

    conn.close()

    return {
        "total_hazards": total,
        "active_hazards": active,
        "critical_hazards": critical,
        "resolved_hazards": resolved,
        "expired_hazards": expired
    }

@app.websocket("/api/ws/hazards")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or ping/pong keepalive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
