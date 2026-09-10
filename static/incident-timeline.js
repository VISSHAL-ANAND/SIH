// Phase 5E — render the investigation timeline from canonical evidence only.
(function () {
  function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  window.renderIncidentTimeline = function (incident) {
    const root = document.getElementById('imw-timeline');
    if (!root) return;
    const detection = incident?.detection || {};
    const ais = incident?.ais || {};
    const drift = incident?.drift || {};
    const rf = incident?.rf || {};
    const candidates = Array.isArray(incident?.candidates) ? incident.candidates : [];
    const events = [
      ['SAR DETECTION', detection.timestamp || 'Timestamp unavailable', detection.source || 'SAR'],
      ['GEOLOCATION', (incident?.geolocation?.hulls || []).length ? 'Georeferenced hull location available' : 'No georeferenced hull', 'GEOLOCATION'],
      ['AIS CORRELATION', ais.source_status || ais.window_status || 'AIS state unavailable', 'AIS'],
      ['VESSEL REVIEW', candidates.length ? `${candidates.length} candidate vessel(s)` : 'No candidate vessel', 'EVIDENCE'],
      ['DRIFT ANALYSIS', drift.status || 'NOT_AVAILABLE', 'DRIFT'],
      ['RF CORROBORATION', rf.status || 'NOT_AVAILABLE', 'RF'],
    ];
    root.innerHTML = events.map(([title, value, source]) =>
      '<div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-content"><b>' + esc(title) + '</b><span>' + esc(value) + '</span><small>' + esc(source) + '</small></div></div>'
    ).join('');
  };
})();
