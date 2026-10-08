import sqlite3
import os
import uuid
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "roadeye.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Users / Reporters Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        reputation_score INTEGER DEFAULT 50,
        reports_count INTEGER DEFAULT 0,
        helpful_votes INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    # Hazards Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hazards (
        id TEXT PRIMARY KEY,
        reporter_id TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT,
        image_url TEXT,
        confidence_score INTEGER DEFAULT 40,
        status TEXT DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        confirm_count INTEGER DEFAULT 1,
        reject_count INTEGER DEFAULT 0,
        FOREIGN KEY (reporter_id) REFERENCES users(id)
    )
    """)

    # Hazard Verifications Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hazard_verifications (
        id TEXT PRIMARY KEY,
        hazard_id TEXT NOT NULL,
        voter_id TEXT NOT NULL,
        is_still_there INTEGER NOT NULL,
        voted_at TEXT NOT NULL,
        UNIQUE(hazard_id, voter_id),
        FOREIGN KEY (hazard_id) REFERENCES hazards(id) ON DELETE CASCADE
    )
    """)

    conn.commit()
    conn.close()

def seed_sample_data():
    """Populates initial realistic demo hazards around Connaught Place / Central Delhi so user can test immediately."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM hazards")
    count = cursor.fetchone()["cnt"]
    if count == 0:
        now = datetime.now(timezone.utc)
        demo_user_id = "user-demo-admin"
        cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, reputation_score, reports_count, helpful_votes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (demo_user_id, "CivicGuardian", 85, 12, 45, now.isoformat()))

        # Base center around 28.6289, 77.2065 (Central Delhi / Connaught Place)
        samples = [
            {
                "id": str(uuid.uuid4()),
                "reporter_id": demo_user_id,
                "latitude": 28.6292,
                "longitude": 77.2085,
                "category": "Pothole",
                "severity": "Critical",
                "description": "Deep trench-like pothole across right lane after rainfall. Severe risk for two-wheelers.",
                "image_url": "https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?w=600&auto=format&fit=crop&q=60",
                "confidence_score": 88,
                "confirm_count": 4,
                "reject_count": 0,
                "hours_old": 2
            },
            {
                "id": str(uuid.uuid4()),
                "reporter_id": demo_user_id,
                "latitude": 28.6315,
                "longitude": 77.2140,
                "category": "Waterlogging",
                "severity": "Moderate",
                "description": "Knee-deep standing water obstructing left bypass underpass.",
                "image_url": "https://images.unsplash.com/photo-1547683905-f686c993aae5?w=600&auto=format&fit=crop&q=60",
                "confidence_score": 75,
                "confirm_count": 3,
                "reject_count": 0,
                "hours_old": 4
            },
            {
                "id": str(uuid.uuid4()),
                "reporter_id": demo_user_id,
                "latitude": 28.6240,
                "longitude": 77.2110,
                "category": "Road Closure",
                "severity": "Critical",
                "description": "Metro construction barricades blocking roundabout exit completely.",
                "image_url": "https://images.unsplash.com/photo-1508873696983-2df57046475a?w=600&auto=format&fit=crop&q=60",
                "confidence_score": 95,
                "confirm_count": 7,
                "reject_count": 0,
                "hours_old": 1
            },
            {
                "id": str(uuid.uuid4()),
                "reporter_id": demo_user_id,
                "latitude": 28.6350,
                "longitude": 77.2050,
                "category": "Road Damage",
                "severity": "Low",
                "description": "Loose gravel and uneven surface on feeder road.",
                "image_url": "",
                "confidence_score": 50,
                "confirm_count": 1,
                "reject_count": 0,
                "hours_old": 6
            },
            # Mumbai / Western Express Highway (Virar -> Dadar corridor) hazards
            {
                "id": str(uuid.uuid4()),
                "reporter_id": demo_user_id,
                "latitude": 19.2812,
                "longitude": 72.8560,
                "category": "Pothole",
                "severity": "Critical",
                "description": "Heavy crater pothole near Mira Road / Dahisar Toll Naka on Southbound WEH.",
                "image_url": "https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?w=600&auto=format&fit=crop&q=60",
                "confidence_score": 90,
                "confirm_count": 6,
                "reject_count": 0,
                "hours_old": 1
            },
            {
                "id": str(uuid.uuid4()),
                "reporter_id": demo_user_id,
                "latitude": 19.1760,
                "longitude": 72.8580,
                "category": "Waterlogging",
                "severity": "Moderate",
                "description": "Water accumulated under Malad subway service lane causing slow vehicle flow.",
                "image_url": "https://images.unsplash.com/photo-1547683905-f686c993aae5?w=600&auto=format&fit=crop&q=60",
                "confidence_score": 78,
                "confirm_count": 3,
                "reject_count": 0,
                "hours_old": 2
            },
            {
                "id": str(uuid.uuid4()),
                "reporter_id": demo_user_id,
                "latitude": 19.1170,
                "longitude": 72.8540,
                "category": "Road Damage",
                "severity": "Critical",
                "description": "Flyover joint damage near Andheri East Gundavali junction.",
                "image_url": "https://images.unsplash.com/photo-1508873696983-2df57046475a?w=600&auto=format&fit=crop&q=60",
                "confidence_score": 85,
                "confirm_count": 5,
                "reject_count": 0,
                "hours_old": 3
            },
            {
                "id": str(uuid.uuid4()),
                "reporter_id": demo_user_id,
                "latitude": 19.0430,
                "longitude": 72.8430,
                "category": "Obstruction",
                "severity": "Moderate",
                "description": "Broken truck blocking center lane near Mahim / Dadar TT flyover entry.",
                "image_url": "",
                "confidence_score": 82,
                "confirm_count": 4,
                "reject_count": 0,
                "hours_old": 1
            }
        ]

        for s in samples:
            created_at = now - timedelta(hours=s["hours_old"])
            expires_at = created_at + timedelta(hours=24)
            cursor.execute("""
                INSERT INTO hazards (id, reporter_id, latitude, longitude, category, severity, description,
                                     image_url, confidence_score, status, created_at, updated_at, expires_at,
                                     confirm_count, reject_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)
            """, (s["id"], s["reporter_id"], s["latitude"], s["longitude"], s["category"], s["severity"],
                  s["description"], s["image_url"], s["confidence_score"],
                  created_at.isoformat(), created_at.isoformat(), expires_at.isoformat(),
                  s["confirm_count"], s["reject_count"]))

        conn.commit()
    conn.close()
