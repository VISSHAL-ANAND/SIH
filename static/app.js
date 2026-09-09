/**
 * Indo Marine Watch (IMW) — Frontend Application Logic
 * =====================================================
 * Leaflet map with CartoDB Positron tiles, SAR drag-and-drop upload,
 * distinct AIS track / blackout / RF lock markers, map.flyTo() on new
 * incidents, and layer-group clearing on every upload cycle.
 */

// ── Global State ────────────────────────────────────────────────────
let currentIncident = null;   // latest /api/process-sar response
let currentTraffic  = null;   // latest /api/analyze-traffic response

// ── Leaflet Map Init ────────────────────────────────────────────────
const map = L.map('map', {
    zoomControl: true,
    attributionControl: false,
}).setView([12.0, 76.0], 6);

// CartoDB Positron — free public CDN
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    subdomains: 'abcd',
}).addTo(map);

// Attribution (bottom-right, unobtrusive)
L.control.attribution({ position: 'bottomright' })
    .addAttribution('&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/">OSM</a>')
    .addTo(map);

// ── Layer Groups (cleared on each new upload) ───────────────────────
const spillLayer    = L.layerGroup().addTo(map);
const hullLayer     = L.layerGroup().addTo(map);
const driftLayer    = L.layerGroup().addTo(map);
const aisTrackLayer = L.layerGroup().addTo(map);
const trafficLayer  = L.layerGroup().addTo(map);

function clearAllLayers() {
    spillLayer.clearLayers();
    hullLayer.clearLayers();
    driftLayer.clearLayers();
    aisTrackLayer.clearLayers();
    trafficLayer.clearLayers();
}

// ── DOM References ──────────────────────────────────────────────────
const $  = (id) => document.getElementById(id);
const uploadZone      = $('upload-zone');
const uploadInput     = $('upload-input');
const uploadIcon      = $('upload-icon');
const uploadTitle     = $('upload-title');
const uploadSubtitle  = $('upload-subtitle');
const overlay         = $('processing-overlay');
const btnDispatch     = $('btn-dispatch');
const dispatchConfirm = $('dispatch-confirm');
const toastEl         = $('toast');

// ── UTC Clock ───────────────────────────────────────────────────────
function tickClock() {
    const now = new Date();
    const utc = now.toISOString().slice(11, 19) + ' UTC';
    $('clock-value').textContent = utc;
}
tickClock();
setInterval(tickClock, 1000);

// ── Toast Notification ──────────────────────────────────────────────
function showToast(message, type = 'info', ms = 3500) {
    toastEl.textContent = message;
    toastEl.className = 'toast ' + type + ' visible';
    setTimeout(() => { toastEl.classList.remove('visible'); }, ms);
}

// ── Activate Sidebar Sections ───────────────────────────────────────
function activateSections(...ids) {
    ids.forEach(id => {
        const el = $(id);
        if (el) el.classList.add('active');
    });
}

// ── Upload Zone — Drag & Drop + Click ───────────────────────────────
uploadZone.addEventListener('click', () => uploadInput.click());

uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('drag-over');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('drag-over');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
    }
});

uploadInput.addEventListener('change', () => {
    if (uploadInput.files.length > 0) {
        handleFile(uploadInput.files[0]);
    }
});

// ── File Handler — Orchestrates Full Pipeline ───────────────────────
async function handleFile(file) {
    // Reset state
    clearAllLayers();
    currentIncident = null;
    currentTraffic = null;
    btnDispatch.disabled = true;
    dispatchConfirm.classList.remove('visible');

    // Upload zone → processing state
    uploadZone.classList.add('processing');
    uploadIcon.className = 'fa-solid fa-spinner';
    uploadTitle.textContent = 'Processing ' + file.name;
    uploadSubtitle.textContent = 'Running AI pipeline...';
    overlay.classList.add('visible');

    try {
        // ---- Stage 1: Process SAR ----
        const formData = new FormData();
        formData.append('file', file);

        const sarResp = await fetch('/api/process-sar', {
            method: 'POST',
            body: formData,
        });

        if (!sarResp.ok) throw new Error('SAR processing failed (' + sarResp.status + ')');
        const sar = await sarResp.json();
        currentIncident = sar;

        // Populate sidebar — Coordinates
        $('coord-lat').textContent = sar.coordinates.center_lat.toFixed(4) + '° N';
        $('coord-lon').textContent = sar.coordinates.center_lon.toFixed(4) + '° E';
        const bb = sar.coordinates.bbox;
        $('coord-bbox').textContent =
            bb[0][0].toFixed(2) + ', ' + bb[0][1].toFixed(2) + '  →  ' +
            bb[1][0].toFixed(2) + ', ' + bb[1][1].toFixed(2);

        // Populate sidebar — Evidence Metrics
        const areaSqKm = (sar.spill.area_sq_m / 1e6).toFixed(2);
        $('metric-area').textContent = areaSqKm + ' km²';
        $('metric-shape').textContent = sar.spill.shape_classification.shape_class.toUpperCase();
        $('metric-ratio').textContent = sar.spill.shape_classification.eigenvalue_ratio.toFixed(4);
        $('metric-drift').textContent = sar.drift.drift_distance_km.toFixed(2) + ' km';
        const orig = sar.drift.origin_coordinates;
        $('metric-origin').textContent = orig[0].toFixed(4) + '°, ' + orig[1].toFixed(4) + '°';
        $('ship-confidence').textContent = (sar.hull.confidence * 100).toFixed(0) + '%';

        activateSections('section-coords', 'section-evidence');

        // Render map — spill bounding box
        renderSpillOnMap(sar);

        // ---- Stage 2: Analyze Traffic ----
        const trafficResp = await fetch('/api/analyze-traffic', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                slick_lat: sar.coordinates.center_lat,
                slick_lon: sar.coordinates.center_lon,
                hull_lat: sar.hull.coordinates[0],
                hull_lon: sar.hull.coordinates[1],
            }),
        });

        if (!trafficResp.ok) throw new Error('Traffic analysis failed');
        const traffic = await trafficResp.json();
        currentTraffic = traffic;

        // Populate sidebar — AIS / RF
        populateAISPanel(traffic);
        populateShipCard(traffic);
        activateSections('section-ais', 'section-ship');

        // Render map — AIS track, blackout, RF lock, surrounding traffic
        renderTrafficOnMap(traffic, sar);

        // Enable dispatch
        btnDispatch.disabled = false;

        // Fly to incident
        map.flyTo(
            [sar.coordinates.center_lat, sar.coordinates.center_lon],
            11,
            { duration: 1.8 }
        );

        showToast('Pipeline complete — ' + sar.incident_id, 'success');

    } catch (err) {
        console.error(err);
        showToast('Error: ' + err.message, 'error', 5000);
    } finally {
        // Reset upload zone
        overlay.classList.remove('visible');
        uploadZone.classList.remove('processing');
        uploadIcon.className = 'fa-solid fa-satellite';
        uploadTitle.textContent = 'Drop SAR Imagery Here';
        uploadSubtitle.textContent = 'TIFF · PNG · JPG';
    }
}

// ── Render Spill + Hull + Drift on Map ──────────────────────────────
function renderSpillOnMap(sar) {
    const bb = sar.coordinates.bbox;
    const center = [sar.coordinates.center_lat, sar.coordinates.center_lon];

    // Spill bounding box (red rectangle)
    L.rectangle(bb, {
        color: '#dc2626',
        weight: 2,
        fillColor: '#dc2626',
        fillOpacity: 0.12,
        dashArray: '6 4',
    }).addTo(spillLayer).bindPopup(
        '<b>Oil Spill Footprint</b><br>' +
        'Area: ' + (sar.spill.area_sq_m / 1e6).toFixed(2) + ' km²<br>' +
        'Shape: ' + sar.spill.shape_classification.shape_class
    );

    // Spill centroid marker (red circle)
    L.circleMarker(center, {
        radius: 7,
        color: '#dc2626',
        fillColor: '#dc2626',
        fillOpacity: 0.8,
        weight: 2,
    }).addTo(spillLayer).bindPopup(
        '<b>Spill Centroid</b><br>' +
        center[0].toFixed(4) + '°N, ' + center[1].toFixed(4) + '°E'
    );

    // Hull detection marker (orange pulsing diamond)
    const hullCoords = sar.hull.coordinates;
    const suspectIcon = L.divIcon({
        className: 'marker-suspect',
        html: '<div class="marker-suspect-inner"></div>',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
    });
    L.marker(hullCoords, { icon: suspectIcon })
        .addTo(hullLayer)
        .bindPopup(
            '<b>YOLOv8 Hull Detection</b><br>' +
            'Confidence: ' + (sar.hull.confidence * 100).toFixed(0) + '%<br>' +
            hullCoords[0].toFixed(4) + '°N, ' + hullCoords[1].toFixed(4) + '°E'
        );

    // Drift origin marker (blue triangle)
    const orig = sar.drift.origin_coordinates;
    L.circleMarker(orig, {
        radius: 7,
        color: '#1d4ed8',
        fillColor: '#1d4ed8',
        fillOpacity: 0.8,
        weight: 2,
    }).addTo(driftLayer).bindPopup(
        '<b>Estimated Spill Origin</b><br>' +
        'GNOME 3% Wind Backward Drift<br>' +
        orig[0].toFixed(4) + '°N, ' + orig[1].toFixed(4) + '°E<br>' +
        'Drift: ' + sar.drift.drift_distance_km.toFixed(2) + ' km over ' +
        sar.drift.hours_back + 'h'
    );

    // Drift line (dashed blue)
    L.polyline([center, orig], {
        color: '#1d4ed8',
        weight: 2,
        dashArray: '8 6',
        opacity: 0.6,
    }).addTo(driftLayer);
}

// ── Render AIS Track, Blackout, RF Lock, Surrounding Traffic ────────
function renderTrafficOnMap(traffic, sar) {
    // AIS Track polyline (gray)
    if (traffic.ais_track && traffic.ais_track.length > 0) {
        const trackCoords = traffic.ais_track.map(p => [p.lat, p.lon]);

        L.polyline(trackCoords, {
            color: '#64748b',
            weight: 3,
            opacity: 0.7,
        }).addTo(aisTrackLayer).bindPopup('<b>AIS Track History</b><br>24h vessel path before blackout');

        // Small gray dots along track
        traffic.ais_track.forEach((pt, i) => {
            L.circleMarker([pt.lat, pt.lon], {
                radius: 3,
                color: '#94a3b8',
                fillColor: '#94a3b8',
                fillOpacity: 0.8,
                weight: 1,
            }).addTo(aisTrackLayer).bindTooltip(
                'SOG: ' + pt.sog + ' kn | ' + pt.timestamp.slice(11, 19) + ' UTC',
                { direction: 'top', offset: [0, -6] }
            );
        });
    }

    // AIS Blackout Point (red X marker)
    if (traffic.ais_blackout_point) {
        const bp = traffic.ais_blackout_point;
        const blackoutIcon = L.divIcon({
            className: 'marker-blackout',
            html: '<div class="marker-blackout-inner"></div>',
            iconSize: [24, 24],
            iconAnchor: [12, 12],
        });
        L.marker([bp.lat, bp.lon], { icon: blackoutIcon })
            .addTo(aisTrackLayer)
            .bindPopup(
                '<b style="color:#dc2626;">⚠ AIS DISABLED</b><br>' +
                'Last AIS broadcast received here.<br>' +
                bp.lat.toFixed(4) + '°N, ' + bp.lon.toFixed(4) + '°E<br>' +
                'Time: ' + bp.timestamp.slice(0, 19).replace('T', ' ') + ' UTC'
            );

        // Dashed line from blackout to current hull position (red)
        const hullCoords = sar.hull.coordinates;
        L.polyline([[bp.lat, bp.lon], hullCoords], {
            color: '#dc2626',
            weight: 2,
            dashArray: '4 6',
            opacity: 0.5,
        }).addTo(aisTrackLayer);
    }

    // RF Lock marker (green pulsing circle)
    if (traffic.rf_intercept && traffic.rf_intercept.match) {
        const rfCoords = traffic.rf_intercept.lock_coordinates;
        const rfIcon = L.divIcon({
            className: 'marker-rf-lock',
            html: '<div class="marker-rf-lock-inner"></div>',
            iconSize: [28, 28],
            iconAnchor: [14, 14],
        });
        L.marker(rfCoords, { icon: rfIcon })
            .addTo(hullLayer)
            .bindPopup(
                '<b style="color:#059669;">RF SIGNAL LOCK</b><br>' +
                traffic.rf_intercept.signature + '<br>' +
                rfCoords[0].toFixed(4) + '°N, ' + rfCoords[1].toFixed(4) + '°E'
            );
    }

    // Surrounding traffic (small blue circles)
    if (traffic.surrounding_traffic) {
        traffic.surrounding_traffic.forEach(v => {
            L.circleMarker([v.lat, v.lon], {
                radius: 5,
                color: '#3b82f6',
                fillColor: '#3b82f6',
                fillOpacity: 0.6,
                weight: 1,
            }).addTo(trafficLayer).bindPopup(
                '<b>' + v.vessel_name + '</b><br>' +
                'MMSI: ' + v.mmsi + '<br>' +
                'SOG: ' + v.sog + ' kn<br>' +
                'Distance: ' + v.distance_km + ' km<br>' +
                '<span style="color:#059669;">AIS ACTIVE ✓</span>'
            );
        });
    }
}

// ── Populate AIS / RF Panel ─────────────────────────────────────────
function populateAISPanel(traffic) {
    // AIS Status badge
    const aisBadge = $('ais-badge');
    if (traffic.ais_status.includes('INACTIVE')) {
        aisBadge.textContent = 'INACTIVE';
        aisBadge.className = 'status-badge danger';
    } else {
        aisBadge.textContent = 'ACTIVE';
        aisBadge.className = 'status-badge success';
    }

    // Dark vessel badge
    const dvBadge = $('dark-vessel-badge');
    if (traffic.is_dark_vessel) {
        dvBadge.textContent = 'CONFIRMED';
        dvBadge.className = 'status-badge danger';
    } else {
        dvBadge.textContent = 'NO';
        dvBadge.className = 'status-badge success';
    }

    // RF Lock badge
    const rfBadge = $('rf-lock-badge');
    if (traffic.rf_intercept && traffic.rf_intercept.match) {
        rfBadge.textContent = 'LOCKED';
        rfBadge.className = 'status-badge success';
    } else {
        rfBadge.textContent = 'NO SIGNAL';
        rfBadge.className = 'status-badge neutral';
    }

    // Threat score
    const score = traffic.suspect_vessel.threat_score;
    const scoreEl = $('threat-score');
    const barEl = $('threat-bar');
    scoreEl.textContent = score.toFixed(2);

    const pct = Math.round(score * 100);
    barEl.style.width = pct + '%';

    if (score >= 0.7) {
        scoreEl.className = 'threat-score-value high';
        barEl.className = 'threat-bar-fill high';
    } else if (score >= 0.4) {
        scoreEl.className = 'threat-score-value medium';
        barEl.className = 'threat-bar-fill medium';
    } else {
        scoreEl.className = 'threat-score-value low';
        barEl.className = 'threat-bar-fill low';
    }
}

// ── Populate Ship Details Card ──────────────────────────────────────
function populateShipCard(traffic) {
    const sv = traffic.suspect_vessel;
    $('ship-name').textContent = sv.name || '—';
    $('ship-mmsi').textContent = sv.mmsi || '—';
    $('ship-flag').textContent = sv.flag || '—';
    $('ship-type').textContent = sv.type || '—';
}

// ── Dispatch Button Handler ─────────────────────────────────────────
btnDispatch.addEventListener('click', async () => {
    if (!currentIncident || !currentTraffic) return;

    btnDispatch.disabled = true;
    btnDispatch.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Dispatching...';

    try {
        const resp = await fetch('/api/dispatch-alert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                incident_id: currentIncident.incident_id,
                slick_centroid: [
                    currentIncident.coordinates.center_lat,
                    currentIncident.coordinates.center_lon,
                ],
                spill_area_sq_m: currentIncident.spill.area_sq_m,
                suspect_vessel: currentTraffic.suspect_vessel,
                threat_score: currentTraffic.suspect_vessel.threat_score,
                evidence_summary: currentTraffic.attribution_reason,
            }),
        });

        if (!resp.ok) throw new Error('Dispatch failed');
        const data = await resp.json();

        // Show confirmation
        dispatchConfirm.classList.add('visible');
        $('dispatch-detail').textContent =
            data.dispatch_id + ' → ' + data.recipient +
            ' | Urgency: ' + data.urgency +
            ' | ' + data.timestamp.slice(0, 19).replace('T', ' ') + ' UTC';

        showToast('Evidence transmitted to Indian Coast Guard', 'success');

    } catch (err) {
        console.error(err);
        showToast('Dispatch failed: ' + err.message, 'error');
        btnDispatch.disabled = false;
    } finally {
        btnDispatch.innerHTML =
            '<i class="fa-solid fa-tower-broadcast"></i> Dispatch Evidence to Coast Guard';
    }
});
