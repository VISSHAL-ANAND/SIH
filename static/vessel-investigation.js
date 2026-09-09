// Phase 4H — interactive candidate investigation record.
(function () {
  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }

  window.openVesselInvestigation = function (candidate) {
    const root = document.getElementById("vessel-investigation-record");
    if (!root) return;
    const observations = candidate?.ais_observations || [];
    const evidence = candidate?.evidence || candidate?.components || {};
    const rows = [
      ["MMSI", candidate?.mmsi],
      ["Vessel", candidate?.vessel_name || "Unknown"],
      ["Classification", candidate?.classification || "UNRESOLVED"],
      ["Distance to spill", candidate?.distance_km != null ? candidate.distance_km + " km" : "N/A"],
      ["Time delta", candidate?.time_delta_minutes != null ? candidate.time_delta_minutes + " min" : "N/A"],
      ["AIS observations", observations.length],
    ];
    root.innerHTML =
      '<div class="record-title">VESSEL INVESTIGATION RECORD</div>' +
      rows.map(r => '<div class="record-row"><span>' + esc(r[0]) + '</span><b>' + esc(r[1]) + '</b></div>').join("") +
      '<div class="record-subtitle">AIS POSITION HISTORY</div>' +
      (observations.length
        ? '<div class="record-timeline">' + observations.map(o =>
            '<div class="timeline-row"><span>' + esc(o.timestamp) + '</span><span>' +
            esc(o.lat) + ', ' + esc(o.lon) + '</span></div>').join("") + '</div>'
        : '<div class="record-empty">No AIS observations supplied.</div>') +
      '<div class="record-subtitle">EVIDENCE SOURCES</div>' +
      Object.entries(evidence).map(([k,v]) =>
        '<div class="record-evidence"><span>' + esc(k) + '</span><b>' + esc(v == null ? "N/A" : Number(v).toFixed ? Number(v).toFixed(2) : v) + '</b></div>'
      ).join("") +
      '<div class="record-warning">⚠ Investigative evidence only — operator review required.</div>';
  };
})();
