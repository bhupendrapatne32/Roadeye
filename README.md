# 👁️ RoadEye — Real-Time Crowdsourced Road Safety & Dynamic Navigation System

> **"RoadEye doesn't just tell you where to go. It helps you avoid where it's unsafe to go."**

RoadEye transforms road safety by treating active community hazards as dynamic cost penalties in route planning. Built for the Hackathon MVP specifications.

---

## 🌟 Key Highlights & PRD Deliverables

1. **Interactive Live Map (MVP-1)**:
   - High-contrast severity markers (🔴 Critical, 🟠 Moderate, 🟡 Low).
   - Real-time pins with confidence scores, category badges, and photo evidence.
2. **Hazard Reporting Engine (MVP-2)**:
   - Sub-10-second reporting flow with auto-GPS coordinates.
   - Severity level, category, description, and photo upload.
3. **Crowdsourced Verification (MVP-3)**:
   - Community verification ("Still There" vs "Clear").
   - Dynamic confidence re-calculation and decay.
4. **Hazard Proximity Detection & Safety Alerts (MVP-4)**:
   - Continuous 300m proximity checks.
   - Spoken audio alerts via Web Speech Synthesis + audio oscillator tone.
   - Floating visual warning banner with quick "Switch to Safe Route" button.
5. **Dynamic Safe Routing Engine (MVP-5)**:
   - Integrates with OSRM (Open Source Routing Machine).
   - Evaluates hazards intersecting road segments.
   - Applies safety penalties (e.g. Critical = 30m detour penalty) and generates hazard-free detours.
6. **Commuter Journey Simulation**:
   - One-click `Start Simulation` drives a vehicle path towards a critical pothole to demonstrate the complete PRD journey live.
7. **Offline-First & PWA**:
   - Service worker caching (`sw.js`).
   - Offline queue with auto-sync when connection restores.
8. **Real-time Synchronization**:
   - WebSockets broadcast live reports across connected clients instantly.

---

## 🚀 How to Run RoadEye

### 1. Requirements
Ensure Python 3.10+ is installed. All required packages (`fastapi`, `uvicorn`, `httpx`, `python-multipart`) are installed.

### 2. Start the Server
Open PowerShell in the `roadeye` folder:
```powershell
cd c:\Users\USER\OneDrive\Desktop\roadeye
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Open the Application
Navigate in your browser to:
[http://localhost:8000](http://localhost:8000)

---

## 🧪 Demonstrating the Complete Hackathon Flow (Success Criteria)

1. Open [http://localhost:8000](http://localhost:8000).
2. Click **"🚗 Start Simulation"** in the top navigation.
3. Observe the vehicle moving toward the Connaught Place hazard zone.
4. When approaching within **300 meters**, an audio warning plays and the **Hazard Proximity Alert** triggers.
5. Click **"Switch to Safe Route"** (or click **"Calculate Safest Route"**).
6. Compare the **Standard Shortest Route** (dotted red line with hazards) against the **RoadEye Safe Route** (solid green detour avoiding the hazard).
7. Tap any marker to verify hazards or click **"Report Hazard"** to submit a new one.
