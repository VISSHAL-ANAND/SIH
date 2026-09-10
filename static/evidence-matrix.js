// Phase 5I — explainable spill/hull/AIS evidence matrix.
(function () {
  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }
  function bar(v) {
    if (v == null || Number.isNaN(Number(v))) return '<span class="evidence-na">N/A</span>';
    const n = Math.max(0, Math.min(1, Number(v)));
    return '<span class="evidence-bar"><span style="width:' + Math.round(n * 100) + '%"></span></span> <b>' + n.toFixed(2) + '</b>';
  }
  function value(v) { return v == null ? 'N/A' : esc(v); }

  window.renderEvidenceMatrix = function (candidate) {
    const root = document.getElementById("evidence-matrix");
    if (!root) return;
    const a = candidate?.association || {};
    const f = candidate?.evidence_fusion || candidate?.fusion || {};
    const history = candidate?.history || candidate?.vessel_history || {};
    const rows = [
      ["Spatial separation", value(a.spatial_distance_km ?? candidate?.spatial_distance_km)],
      ["Temporal separation", value(a.temporal_delta_min ?? candidate?.temporal_delta_min) + " min"],
      ["Spatial evidence", bar(a.distance_score)],
      ["Temporal evidence", bar(a.time_score)],
      ["AIS continuity", esc(history.status || "NOT_ASSESSABLE")],
      ["AIS gap", esc(a.ais_gap_status || "NOT_ESTABLISHED")],
      ["Evidence confidence", bar(a.evidence_confidence ?? a.overall_score ?? f.overall_score)],
      ["RF corroboration", esc(f.rf_status || candidate?.rf_status || "NOT_IMPLEMENTED")]
    ];
    root.innerHTML =
      '<div class="evidence-title">VESSEL INVESTIGATION</div>' +
      '<div class="evidence-meta">MMSI: ' + esc(candidate?.mmsi || "UNRESOLVED") + '</div>' +
      '<div class="evidence-rows">' +
      rows.map(r => '<div class="evidence-row"><span>' + esc(r[0]) + '</span><span>' + r[1] + '</span></div>').join("") +
      '</div>' +
      '<div class="evidence-classification">' + esc(a.classification || candidate?.classification || "UNRESOLVED") + '</div>' +
      '<div class="evidence-warning">⚠ Investigative evidence only — does not establish responsibility.</div>';
  };
})();
