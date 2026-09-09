// Phase 4J — clean operator response panel.
(function () {
  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }

  window.renderIncidentResponse = function (draft) {
    const root = document.getElementById("incident-response");
    if (!root) return;

    const s = draft?.summary || {};
    const candidates = draft?.candidate_vessels || [];
    const limitations = draft?.limitations || [];

    root.innerHTML =
      '<div class="response-title">INCIDENT RESPONSE</div>' +
      '<div class="response-status">' + esc(draft?.status || "DRAFT_REQUIRES_OPERATOR_CONFIRMATION") + '</div>' +
      '<div class="response-row"><span>Incident</span><b>' + esc(draft?.incident_id) + '</b></div>' +
      '<div class="response-row"><span>Detection</span><b>' + esc(s.detection_time) + '</b></div>' +
      '<div class="response-row"><span>Spill count</span><b>' + esc(s.spill_count) + '</b></div>' +
      '<div class="response-row"><span>Primary location</span><b>' +
        esc(s.primary_location ? ((s.primary_location.lat ?? "?") + ", " + (s.primary_location.lon ?? "?")) : "N/A") +
      '</b></div>' +
      '<div class="response-subtitle">CANDIDATE VESSELS</div>' +
      (candidates.length ? candidates.map(c =>
        '<div class="response-vessel"><b>' + esc(c.vessel_name || "Unknown") + '</b><span>' +
        esc(c.mmsi) + ' · ' + esc(c.classification || "UNRESOLVED") + '</span></div>'
      ).join("") : '<div class="response-empty">No candidate vessels supplied.</div>') +
      '<div class="response-subtitle">LIMITATIONS</div>' +
      (limitations.length ? '<ul>' + limitations.map(x => '<li>' + esc(x) + '</li>').join("") + '</ul>' :
        '<div class="response-empty">None recorded.</div>') +
      '<div class="response-warning">' + esc(draft?.notice || "Draft only. Operator review required.") + '</div>';
  };
})();
