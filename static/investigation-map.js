// Phase 6 — evidence-first investigation map.
// Renders observed SAR/hull/AIS evidence separately from estimated drift evidence.
(function () {
  function esc(v) {
    return String(v ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  }

  function finite(v) { return Number.isFinite(Number(v)); }
  function coords(lat, lon) { return finite(lat) && finite(lon) ? [Number(lat), Number(lon)] : null; }

  function candidatePosition(candidate) {
    return coords(
      candidate?.ais_lat ?? candidate?.position?.lat ?? candidate?.history?.last_position?.lat,
      candidate?.ais_lon ?? candidate?.position?.lon ?? candidate?.history?.last_position?.lon
    );
  }

  function spillPosition(incident) {
    const g = incident?.geolocation || {};
    const s = incident?.spill || {};
    return coords(
      g.center_lat ?? g.latitude ?? s.center_lat ?? s.latitude ?? incident?.detection?.lat,
      g.center_lon ?? g.longitude ?? s.center_lon ?? s.longitude ?? incident?.detection?.lon
    );
  }

  function trajectoryPoints(candidate) {
    const points = candidate?.trajectory?.points;
    if (!Array.isArray(points)) return [];
    return points.map(p => coords(p?.lat, p?.lon)).filter(Boolean);
  }

  function layerLabel(position, title, subtitle, kind) {
    const icon = L.divIcon({
      className: 'imw-evidence-marker imw-' + kind,
      html: '<div class="imw-marker-core"></div><div class="imw-marker-label"><b>' + esc(title) + '</b><span>' + esc(subtitle) + '</span></div>',
      iconSize: [1, 1], iconAnchor: [0, 0]
    });
    return L.marker(position, { icon, keyboard: false });
  }

  function evidencePopup(title, status, details) {
    return '<div class="imw-map-popup"><b>' + esc(title) + '</b><br><span class="imw-popup-status">' + esc(status) + '</span><br>' + esc(details) + '</div>';
  }

  window.renderIncidentMap = function (incident) {
    if (typeof map === 'undefined' || !incident) return;

    if (window.__imwInvestigationMapLayers) {
      window.__imwInvestigationMapLayers.forEach(layer => layer.remove());
    }
    const layers = [];
    window.__imwInvestigationMapLayers = layers;

    const observed = L.layerGroup().addTo(map);
    const estimated = L.layerGroup().addTo(map);
    layers.push(observed, estimated);

    const bounds = [];
    const spill = spillPosition(incident);
    const drift = incident?.drift || {};

    // OBSERVED: SAR spill anchor.
    if (spill) {
      const spillMarker = L.circleMarker(spill, {
        radius: 9, weight: 3, fillOpacity: 0.35
      }).addTo(observed);
      spillMarker.bindPopup(evidencePopup('SAR SPILL ANCHOR', 'OBSERVED / SAR', 'Georeferenced incident location from the SAR analysis.'));
      bounds.push(spill);
    }

    // ESTIMATED: environmental source zone. Never style it as an observed detection.
    const origin = coords(drift.origin_lat, drift.origin_lon);
    if (origin && String(drift.status || '').toUpperCase() === 'ESTIMATED') {
      const uncertainty = Math.max(500, Number(drift.uncertainty_km || 1) * 1000);
      const zone = L.circle(origin, {
        radius: uncertainty, weight: 2, dashArray: '7 5', fillOpacity: 0.10
      }).addTo(estimated);
      zone.bindPopup(evidencePopup(
        'ESTIMATED DRIFT SOURCE ZONE',
        'ESTIMATED / ENVIRONMENTAL MODEL',
        'Uncertainty: ' + Number(drift.uncertainty_km || 0).toFixed(2) + ' km. This is a modelled source zone, not a legal attribution radius.'
      ));
      const marker = L.circleMarker(origin, { radius: 5, weight: 2, fillOpacity: 0.25 }).addTo(estimated);
      marker.bindPopup(evidencePopup('ESTIMATED SOURCE CENTRE', 'ESTIMATED', 'Derived from supplied environmental observations.'));
      bounds.push(origin);
    }

    const candidates = Array.isArray(incident.candidates) ? incident.candidates : [];
    candidates.forEach((candidate, index) => {
      const position = candidatePosition(candidate);
      if (position) {
        const marker = layerLabel(
          position,
          candidate.vessel_name || 'Candidate vessel ' + (index + 1),
          'AIS observed · ' + (candidate.mmsi || 'MMSI unavailable'),
          'observed'
        ).addTo(observed);
        marker.bindPopup(evidencePopup(
          candidate.vessel_name || 'Candidate vessel',
          'OBSERVED / AIS',
          'MMSI: ' + (candidate.mmsi || '—') + '. Candidate correlation does not establish responsibility.'
        ));
        bounds.push(position);
      }

      const track = trajectoryPoints(candidate);
      if (track.length >= 2) {
        const line = L.polyline(track, { weight: 3, opacity: 0.75 }).addTo(observed);
        line.bindPopup(evidencePopup(
          'AIS TRAJECTORY',
          'OBSERVED / AIS TRACK',
          candidate?.trajectory?.status || 'Observed trajectory available.'
        ));
        track.forEach(p => bounds.push(p));
      }
    });

    // Evidence legend.
    const legend = L.control({ position: 'topright' });
    legend.onAdd = function () {
      const div = L.DomUtil.create('div', 'imw-map-legend');
      div.innerHTML =
        '<div class="imw-legend-title">EVIDENCE LAYERS</div>' +
        '<div><i class="imw-legend-dot observed"></i> Observed SAR / AIS</div>' +
        '<div><i class="imw-legend-line observed"></i> Observed AIS trajectory</div>' +
        '<div><i class="imw-legend-zone estimated"></i> Estimated drift zone</div>' +
        '<div class="imw-legend-note">Evidence only · responsibility not established</div>';
      L.DomEvent.disableClickPropagation(div);
      return div;
    };
    legend.addTo(map);
    layers.push(legend);

    if (bounds.length > 0) {
      map.fitBounds(L.latLngBounds(bounds), { padding: [55, 55], maxZoom: 12 });
    }
  };
})();
