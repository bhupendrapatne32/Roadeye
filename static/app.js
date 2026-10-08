// State Management
let map = null;
let userMarker = null;
let currentCoords = { lat: 19.4564, lon: 72.8105 }; // Default Virar, Maharashtra
let hazardMarkers = {};
let routePolylines = { direct: null, safe: null };
let activeHazards = [];
let offlineQueue = JSON.parse(localStorage.getItem('roadeye_offline_queue') || '[]');
let simulationInterval = null;
let voiceEnabled = true;
let simulatedRoutePoints = [];
let simIndex = 0;
let currentAudioAlarm = null;

// Audio Alerts using Web Speech Synthesis API
function speakAlert(text) {
  if (!voiceEnabled || !('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.05;
  utterance.pitch = 1.0;
  window.speechSynthesis.speak(utterance);
}

// Generate beep tone for safety alert
function playAlertBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.3);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.3);
  } catch (e) {
    console.warn("Audio context not allowed yet", e);
  }
}

// Map Initialization
function initMap() {
  map = L.map('map', {
    zoomControl: false
  }).setView([currentCoords.lat, currentCoords.lon], 14);

  // Free OpenStreetMap Standard Tiles (No API Key Required)
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  L.control.zoom({ position: 'bottomright' }).addTo(map);

  // User position marker
  const userIcon = L.divIcon({
    className: 'user-car-marker',
    iconSize: [24, 24],
    iconAnchor: [12, 12]
  });

  userMarker = L.marker([currentCoords.lat, currentCoords.lon], { icon: userIcon }).addTo(map);

  // Get real user GPS if available
  if ('geolocation' in navigator) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        currentCoords.lat = pos.coords.latitude;
        currentCoords.lon = pos.coords.longitude;
        userMarker.setLatLng([currentCoords.lat, currentCoords.lon]);
        map.setView([currentCoords.lat, currentCoords.lon], 15);
        document.getElementById('report-lat').value = currentCoords.lat.toFixed(6);
        document.getElementById('report-lon').value = currentCoords.lon.toFixed(6);
      },
      (err) => console.log('Geolocation permission denied or timeout, using preset:', err),
      { timeout: 5000 }
    );
  }

  // Map click handler: Either sets coordinates or finishes direct tap-to-pin report
  map.on('click', (e) => {
    if (isPickingLocationOnMap) {
      finalizeReportAtLocation(e.latlng.lat, e.latlng.lng);
    } else {
      document.getElementById('report-lat').value = e.latlng.lat.toFixed(6);
      document.getElementById('report-lon').value = e.latlng.lng.toFixed(6);
    }
  });
}

// Load Hazards from API
async function loadHazards() {
  try {
    const res = await fetch('/api/hazards');
    const hazards = await res.json();
    activeHazards = hazards;
    renderHazardMarkers(hazards);
    updateStatsDisplay();
  } catch (err) {
    console.error('Failed to load hazards:', err);
  }
}

// Render Pins on Map
function renderHazardMarkers(hazards) {
  // Clear existing pins
  Object.values(hazardMarkers).forEach(m => map.removeLayer(m));
  hazardMarkers = {};

  hazards.forEach(h => {
    let colorClass = 'bg-amber-500';
    let iconSymbol = '⚠️';
    let pulseClass = '';

    if (h.severity === 'Critical') {
      colorClass = 'bg-rose-600';
      iconSymbol = '⛔';
      pulseClass = 'ring-4 ring-rose-400 ring-opacity-70 animate-pulse';
    } else if (h.severity === 'Low') {
      colorClass = 'bg-yellow-400 text-slate-900';
      iconSymbol = '⚠️';
    } else {
      colorClass = 'bg-orange-500';
      iconSymbol = '🚧';
    }

    const pinIcon = L.divIcon({
      className: 'custom-hazard-div',
      html: `
        <div class="hazard-marker-pin ${colorClass} ${pulseClass} w-9 h-9 text-base flex items-center justify-center shadow-lg border-2 border-white">
          <span>${iconSymbol}</span>
        </div>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18]
    });

    const marker = L.marker([h.latitude, h.longitude], { icon: pinIcon }).addTo(map);

    // Popup Content with Verification Actions
    const popupContent = `
      <div class="p-3 max-w-xs text-slate-100 font-sans">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded ${colorClass}">
            ${h.severity} • ${h.category}
          </span>
          <span class="text-xs text-slate-400 font-mono">
            ${h.confidence_score}% Conf.
          </span>
        </div>
        ${h.image_url ? `<img src="${h.image_url}" class="w-full h-28 object-cover rounded-md mb-2 border border-slate-700"/>` : ''}
        <p class="text-sm text-slate-300 mb-2 leading-snug">${h.description || 'Reported hazard on this roadway.'}</p>
        
        <div class="border-t border-slate-700/80 pt-2 mt-2">
          <div class="text-xs text-slate-400 mb-1.5 font-medium">Is this hazard still present?</div>
          <div class="flex gap-2">
            <button onclick="verifyHazard('${h.id}', true)" class="flex-1 py-1.5 px-2 bg-emerald-600 hover:bg-emerald-500 text-xs font-semibold rounded text-white flex items-center justify-center gap-1 transition">
              <span>👍</span> Still There (${h.confirm_count || 1})
            </button>
            <button onclick="verifyHazard('${h.id}', false)" class="flex-1 py-1.5 px-2 bg-slate-700 hover:bg-slate-600 text-xs font-semibold rounded text-white flex items-center justify-center gap-1 transition">
              <span>✕</span> Clear (${h.reject_count || 0})
            </button>
          </div>
        </div>
      </div>
    `;

    marker.bindPopup(popupContent, { className: 'custom-popup' });
    hazardMarkers[h.id] = marker;
  });
}

// Verify Hazard
async function verifyHazard(hazardId, isStillThere) {
  try {
    const voterId = localStorage.getItem('roadeye_voter_id') || 'voter-' + Math.random().toString(36).substring(2, 9);
    localStorage.setItem('roadeye_voter_id', voterId);

    const res = await fetch(`/api/hazards/${hazardId}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voter_id: voterId, is_still_there: isStillThere })
    });

    if (res.ok) {
      showToast(isStillThere ? 'Verification logged! Confidence boosted.' : 'Reported as resolved. Confidence adjusted.');
      loadHazards();
    }
  } catch (err) {
    console.error('Verification failed', err);
  }
}

// Proximity Warning Engine
function checkProximity(lat, lon) {
  let closestHazard = null;
  let minDistance = 999999;

  activeHazards.forEach(h => {
    if (h.status !== 'ACTIVE') return;
    const dist = calculateHaversine(lat, lon, h.latitude, h.longitude);
    if (dist <= 300 && dist < minDistance) {
      minDistance = dist;
      closestHazard = h;
    }
  });

  const alertBanner = document.getElementById('hazard-alert-banner');
  if (closestHazard) {
    document.getElementById('alert-hazard-title').innerText = `${closestHazard.severity} ${closestHazard.category} Ahead!`;
    document.getElementById('alert-hazard-dist').innerText = `${Math.round(minDistance)} meters away • ${closestHazard.confidence_score}% Confidence`;
    alertBanner.classList.remove('hidden');

    playAlertBeep();
    if (!alertBanner.dataset.lastSpoken || Date.now() - parseInt(alertBanner.dataset.lastSpoken) > 15000) {
      speakAlert(`Caution! ${closestHazard.severity} ${closestHazard.category} detected within ${Math.round(minDistance)} meters.`);
      alertBanner.dataset.lastSpoken = Date.now().toString();
    }
  } else {
    alertBanner.classList.add('hidden');
  }
}

// Math distance utility
function calculateHaversine(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon/2) * Math.sin(dLon/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}

// Route endpoints state
let routeEndpoints = {
  start: { lat: 19.4564, lon: 72.8105, name: "Virar, Maharashtra" }, // Default Virar
  dest: { lat: 19.0178, lon: 72.8478, name: "Dadar, Mumbai" }        // Default Dadar
};

function useCurrentGpsAsStart() {
  routeEndpoints.start = { lat: currentCoords.lat, lon: currentCoords.lon, name: "Current GPS Location" };
  document.getElementById('start-search-input').value = `GPS (${currentCoords.lat.toFixed(4)}, ${currentCoords.lon.toFixed(4)})`;
  showToast("Starting point set to current GPS location!");
}

function setQuickRoute(presetStart, presetDest) {
  if (presetStart === 'virar' && presetDest === 'dadar') {
    routeEndpoints.start = { lat: 19.4564, lon: 72.8105, name: "Virar, Maharashtra" };
    routeEndpoints.dest = { lat: 19.0178, lon: 72.8478, name: "Dadar, Mumbai" };
    document.getElementById('start-search-input').value = "Virar, Maharashtra";
    document.getElementById('dest-search-input').value = "Dadar, Mumbai";
    map.setView([19.25, 72.84], 10);
    calculateRoutes();
  } else if (presetStart === 'delhi-cp') {
    routeEndpoints.start = { lat: 28.6289, lon: 77.2065, name: "Connaught Place, Delhi" };
    routeEndpoints.dest = { lat: 28.6129, lon: 77.2295, name: "India Gate, Delhi" };
    document.getElementById('start-search-input').value = "Connaught Place, Delhi";
    document.getElementById('dest-search-input').value = "India Gate, Delhi";
    map.setView([28.625, 77.215], 13);
    calculateRoutes();
  }
}

// Search locations using OpenStreetMap Nominatim geocoder API
async function searchLocation(target) {
  const inputEl = document.getElementById(target === 'start' ? 'start-search-input' : 'dest-search-input');
  const suggestionsEl = document.getElementById(target === 'start' ? 'start-suggestions' : 'dest-suggestions');
  const query = inputEl.value.trim();

  if (!query) {
    showToast("Please enter a location name", true);
    return;
  }

  showToast(`Searching for "${query}"...`);
  try {
    const res = await fetch(`/api/geocode?query=${encodeURIComponent(query)}`);
    const results = await res.json();

    if (!results || results.length === 0) {
      showToast("No location found. Please try another name.", true);
      suggestionsEl.classList.add('hidden');
      return;
    }

    // Render suggestions
    suggestionsEl.innerHTML = '';
    results.forEach(r => {
      const item = document.createElement('div');
      item.className = 'p-2 text-xs hover:bg-slate-800 cursor-pointer border-b border-slate-800 text-slate-200 transition';
      item.innerText = r.display_name;
      item.onclick = () => {
        routeEndpoints[target] = { lat: r.lat, lon: r.lon, name: r.display_name };
        inputEl.value = r.display_name.split(',')[0];
        suggestionsEl.classList.add('hidden');
        map.setView([r.lat, r.lon], 13);
      };
      suggestionsEl.appendChild(item);
    });
    suggestionsEl.classList.remove('hidden');

    // Auto select first result
    routeEndpoints[target] = { lat: results[0].lat, lon: results[0].lon, name: results[0].display_name };
  } catch (err) {
    console.error("Geocoding failed", err);
    showToast("Search failed: " + err.message, true);
  }
}

// Close suggestion menus when clicking outside
document.addEventListener('click', (e) => {
  if (!e.target.closest('#start-suggestions') && !e.target.closest('#start-search-input')) {
    const el = document.getElementById('start-suggestions');
    if (el) el.classList.add('hidden');
  }
  if (!e.target.closest('#dest-suggestions') && !e.target.closest('#dest-search-input')) {
    const el = document.getElementById('dest-suggestions');
    if (el) el.classList.add('hidden');
  }
});

// Dynamic Navigation & Route Calculation
async function calculateRoutes() {
  const startLat = routeEndpoints.start.lat;
  const startLon = routeEndpoints.start.lon;
  const endLat = routeEndpoints.dest.lat;
  const endLon = routeEndpoints.dest.lon;

  const btn = document.getElementById('calc-route-btn');
  btn.innerText = 'Calculating Safety Penalties...';
  btn.disabled = true;

  try {
    const res = await fetch('/api/routes/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_lat: startLat,
        start_lon: startLon,
        end_lat: endLat,
        end_lon: endLon
      })
    });

    const data = await res.json();
    displayRouteResults(data);
  } catch (err) {
    showToast('Failed to calculate route: ' + err.message, true);
  } finally {
    btn.innerText = 'Search & Calculate Safest Route';
    btn.disabled = false;
  }
}

// Display Direct vs Safe Routes
function displayRouteResults(data) {
  if (routePolylines.direct) map.removeLayer(routePolylines.direct);
  if (routePolylines.safe) map.removeLayer(routePolylines.safe);

  const direct = data.fastest_route;
  const safe = data.safest_route;

  // Convert coords [lon, lat] -> [lat, lon]
  const directLatLngs = direct.coordinates.map(c => [c[1], c[0]]);
  const safeLatLngs = safe.coordinates.map(c => [c[1], c[0]]);

  // Draw direct in dashed red/amber if hazardous
  const directColor = direct.hazard_count > 0 ? '#ef4444' : '#64748b';
  routePolylines.direct = L.polyline(directLatLngs, {
    color: directColor,
    weight: 5,
    opacity: 0.8,
    dashArray: direct.hazard_count > 0 ? '8, 8' : null
  }).addTo(map);

  // Draw safe route in solid vibrant green/cyan
  routePolylines.safe = L.polyline(safeLatLngs, {
    color: '#10b981',
    weight: 6,
    opacity: 0.95
  }).addTo(map);

  map.fitBounds(routePolylines.safe.getBounds(), { padding: [50, 50] });

  // Update comparison UI
  document.getElementById('route-comparison-card').classList.remove('hidden');
  document.getElementById('direct-time').innerText = `${Math.round(direct.travel_time_seconds / 60)} min`;
  document.getElementById('direct-hazards').innerText = `${direct.hazard_count} hazards (${Math.round(direct.safety_penalty_seconds / 60)}m safety penalty)`;

  document.getElementById('safe-time').innerText = `${Math.round(safe.travel_time_seconds / 60)} min`;
  document.getElementById('safe-hazards').innerText = `${safe.hazard_count} hazards (Zero Critical Risk)`;

  const avoidedCount = data.hazards_avoided || Math.max(0, direct.hazard_count - safe.hazard_count);
  document.getElementById('hazards-avoided-count').innerText = `${avoidedCount} hazards bypassed`;

  speakAlert(`Safe route generated. It avoids ${avoidedCount} hazardous road segments.`);
}

// Commuter Journey Simulator
function startDriveSimulation() {
  if (simulationInterval) {
    clearInterval(simulationInterval);
    simulationInterval = null;
    document.getElementById('sim-btn').innerText = '🚗 Start Drive Simulation';
    return;
  }

  // Check if viewing Mumbai or Delhi, and simulate appropriate danger approach
  if (routeEndpoints.dest.name.includes("Dadar") || routeEndpoints.start.name.includes("Virar")) {
    // Simulating Mira Road -> Dahisar approach towards Critical Pothole at 19.2812, 72.8560
    simulatedRoutePoints = [
      { lat: 19.2900, lon: 72.8590 },
      { lat: 19.2860, lon: 72.8578 },
      { lat: 19.2835, lon: 72.8568 }, // Approaches 300m threshold!
      { lat: 19.2818, lon: 72.8562 }, // Danger zone!
      { lat: 19.2812, lon: 72.8560 }, // Right on pothole
      { lat: 19.2780, lon: 72.8550 },
      { lat: 19.2720, lon: 72.8540 }
    ];
  } else {
    // Delhi Connaught Place crossing into 28.6292, 77.2085
    simulatedRoutePoints = [
      { lat: 28.6250, lon: 77.2040 },
      { lat: 28.6265, lon: 77.2055 },
      { lat: 28.6280, lon: 77.2070 },
      { lat: 28.6288, lon: 77.2080 },
      { lat: 28.6292, lon: 77.2085 },
      { lat: 28.6310, lon: 77.2095 },
      { lat: 28.6330, lon: 77.2110 }
    ];
  }

  simIndex = 0;
  document.getElementById('sim-btn').innerText = '🛑 Stop Simulation';

  simulationInterval = setInterval(() => {
    if (simIndex >= simulatedRoutePoints.length) {
      clearInterval(simulationInterval);
      simulationInterval = null;
      document.getElementById('sim-btn').innerText = '🚗 Start Drive Simulation';
      showToast('Simulation complete.');
      return;
    }

    const pt = simulatedRoutePoints[simIndex];
    currentCoords = { lat: pt.lat, lon: pt.lon };
    userMarker.setLatLng([pt.lat, pt.lon]);
    map.panTo([pt.lat, pt.lon]);
    checkProximity(pt.lat, pt.lon);
    simIndex++;
  }, 2500);
}

// Hazard Form Submission
async function submitHazardReport(event) {
  event.preventDefault();
  const form = event.target;
  const formData = new FormData(form);

  const submitBtn = document.getElementById('report-submit-btn');
  submitBtn.innerText = 'Submitting...';
  submitBtn.disabled = true;

  try {
    if (!navigator.onLine) {
      // Store in offline IndexedDB/LocalStorage queue
      const offlineEntry = {
        latitude: parseFloat(formData.get('latitude')),
        longitude: parseFloat(formData.get('longitude')),
        category: formData.get('category'),
        severity: formData.get('severity'),
        description: formData.get('description'),
        timestamp: new Date().toISOString()
      };
      offlineQueue.push(offlineEntry);
      localStorage.setItem('roadeye_offline_queue', JSON.stringify(offlineQueue));
      updateOfflineQueueBadge();
      showToast('Offline: Report queued and will sync when reconnected!');
      closeReportModal();
      return;
    }

    const res = await fetch('/api/hazards', {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      showToast('Hazard reported successfully! Community verification started.');
      closeReportModal();
      form.reset();
      loadHazards();
    } else {
      showToast('Submission error. Please retry.', true);
    }
  } catch (err) {
    showToast('Network error: Queuing report locally.');
    // Offline queue fallback
    offlineQueue.push({
      latitude: parseFloat(formData.get('latitude')),
      longitude: parseFloat(formData.get('longitude')),
      category: formData.get('category'),
      severity: formData.get('severity'),
      description: formData.get('description'),
      timestamp: new Date().toISOString()
    });
    localStorage.setItem('roadeye_offline_queue', JSON.stringify(offlineQueue));
    updateOfflineQueueBadge();
    closeReportModal();
  } finally {
    submitBtn.innerText = 'Submit Report (10s)';
    submitBtn.disabled = false;
  }
}

// Sync Offline Reports when online
async function syncOfflineQueue() {
  if (!navigator.onLine || offlineQueue.length === 0) return;
  console.log(`Syncing ${offlineQueue.length} offline hazard reports...`);
  const queueToSync = [...offlineQueue];
  offlineQueue = [];
  localStorage.setItem('roadeye_offline_queue', JSON.stringify([]));

  for (const item of queueToSync) {
    const fd = new FormData();
    fd.append('latitude', item.latitude);
    fd.append('longitude', item.longitude);
    fd.append('category', item.category);
    fd.append('severity', item.severity);
    fd.append('description', item.description || '');

    try {
      await fetch('/api/hazards', { method: 'POST', body: fd });
    } catch (e) {
      console.warn("Failed syncing item", e);
    }
  }
  updateOfflineQueueBadge();
  loadHazards();
  showToast('Offline reports synchronized!');
}

window.addEventListener('online', syncOfflineQueue);

function updateOfflineQueueBadge() {
  const badge = document.getElementById('offline-queue-count');
  if (badge) {
    badge.innerText = offlineQueue.length;
    badge.parentElement.classList.toggle('hidden', offlineQueue.length === 0);
  }
}

// WebSocket Live Updates
function setupWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/hazards`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'NEW_HAZARD') {
        showToast(`New ${data.hazard.severity} ${data.hazard.category} reported nearby!`);
        loadHazards();
      } else if (data.type === 'HAZARD_VERIFIED' || data.type === 'HAZARDS_REFRESHED') {
        loadHazards();
      }
    } catch (e) {}
  };

  ws.onclose = () => {
    setTimeout(setupWebSocket, 4000); // Auto-reconnect
  };
}

// State for interactive map hazard placement
let isPickingLocationOnMap = false;
let pendingHazardData = null;

// UI Helpers
function openReportModal() {
  document.getElementById('report-modal').classList.remove('hidden');
}

function closeReportModal() {
  document.getElementById('report-modal').classList.add('hidden');
}

// Step 1: User fills category, severity, description and optional photo -> clicks "Done / Show on Map"
function handleProceedToPickLocation(event) {
  event.preventDefault();
  const category = document.getElementById('report-category').value;
  const severity = document.querySelector('input[name="severity"]:checked')?.value || 'Moderate';
  const description = document.getElementById('report-desc').value.trim();
  const photoInput = document.getElementById('report-photo');
  const photoFile = photoInput && photoInput.files ? photoInput.files[0] : null;

  pendingHazardData = {
    category,
    severity,
    description,
    photoFile
  };

  // Close form modal and activate map tap-to-pin mode
  closeReportModal();
  isPickingLocationOnMap = true;
  document.getElementById('pin-placement-banner').classList.remove('hidden');
  document.getElementById('map').style.cursor = 'crosshair';

  showToast('Now click on the map where the hazard is located!');
}

function cancelPinSelection() {
  isPickingLocationOnMap = false;
  pendingHazardData = null;
  document.getElementById('pin-placement-banner').classList.add('hidden');
  document.getElementById('map').style.cursor = '';
  showToast('Report cancelled.');
}

// Step 2: User taps directly on the map where the pothole is located!
async function finalizeReportAtLocation(lat, lon) {
  if (!pendingHazardData) return;

  isPickingLocationOnMap = false;
  document.getElementById('pin-placement-banner').classList.add('hidden');
  document.getElementById('map').style.cursor = '';

  const fd = new FormData();
  fd.append('latitude', lat.toString());
  fd.append('longitude', lon.toString());
  fd.append('category', pendingHazardData.category);
  fd.append('severity', pendingHazardData.severity);
  fd.append('description', pendingHazardData.description || '');
  if (pendingHazardData.photoFile) {
    fd.append('photo', pendingHazardData.photoFile);
  }

  showToast('Submitting road hazard...');

  try {
    const res = await fetch('/api/hazards', {
      method: 'POST',
      body: fd
    });

    if (res.ok) {
      showToast('Hazard reported successfully and pinned to map! 📍');
      loadHazards();
      // Pan to new marker
      map.panTo([lat, lon]);
    } else {
      showToast('Submission error. Please try again.', true);
    }
  } catch (err) {
    showToast('Offline: Report queued, will sync when online.');
    offlineQueue.push({
      latitude: lat,
      longitude: lon,
      category: pendingHazardData.category,
      severity: pendingHazardData.severity,
      description: pendingHazardData.description,
      timestamp: new Date().toISOString()
    });
    localStorage.setItem('roadeye_offline_queue', JSON.stringify(offlineQueue));
    updateOfflineQueueBadge();
  } finally {
    pendingHazardData = null;
    // Reset form inputs
    document.getElementById('report-desc').value = '';
    const photoEl = document.getElementById('report-photo');
    if (photoEl) photoEl.value = '';
  }
}

function showToast(message, isError = false) {
  const toast = document.getElementById('toast');
  toast.innerText = message;
  toast.className = `fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg shadow-xl text-sm font-semibold transition-opacity duration-300 ${
    isError ? 'bg-rose-600 text-white' : 'bg-slate-900 border border-slate-700 text-emerald-400'
  }`;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 3500);
}

async function updateStatsDisplay() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('stat-active').innerText = data.active_hazards;
    document.getElementById('stat-critical').innerText = data.critical_hazards;
  } catch (e) {}
}

// Register PWA Service Worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js')
    .then(() => console.log('RoadEye PWA Service Worker Registered'))
    .catch((err) => console.log('SW registration failed:', err));
}

// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  initMap();
  loadHazards();
  setupWebSocket();
  updateOfflineQueueBadge();
  setInterval(loadHazards, 20000); // Refresh every 20s
});
