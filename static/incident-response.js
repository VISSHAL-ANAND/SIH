// Phase 5A — operator response model + clean response panel.
(function () {
  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }

  window.buildResponseDraft = function (incident, urgency = "REVIEW") {
    incident = incident || {};
    const geo = incident.geolocation || {};
    const spill = incident.spill || {};
    const candidates = Array.isArray(incident.candidates) ? incident.candidates : [];
    const limitations = Array.isArray(incident.limitations) ? incident.limitations : [];
    const locations = Array.isArray(geo.hulls) ? geo.hulls : [];
    const primary = locations.length ? locations[0] : null;
    const allowed = ["LOW", "REVIEW", "HIGH", "CRITICAL"];
    const level = allowed.includes(urgency) ? urgency : "REVIEW";

    return {
      incident_id: incident.incident_id || null,
      status: "DRAFT_REQUIRES_OPERATOR_CONFIRMATION",
      urgency: level,
      subject: "Marine oil-spill incident — evidence review required",
      summary: {
        detection_time: (incident.detection || {}).timestamp || null,
        spill_count: spill.count ?? 0,
        primary_location: primary,
        candidate_count: candidates.length
      },
      candidate_vessels: candidates.map(c => ({
        mmsi: c.mmsi ?? null,
        vessel_name: c.vessel_name ?? null,
        classification: c.classification || (c.association || {}).classification || null
      })),
      limitations,
      operator_confirmation: {required: true, confirmed: false, confirmed_by: null, confirmed_at: null},
      transmission: {status: "NOT_SENT", recipient: null},
      notice: "Draft only. Verify evidence and recipient details before any official transmission."
    };
  };

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
