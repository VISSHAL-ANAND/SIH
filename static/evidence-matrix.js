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
    const trajectory = candidate?.trajectory || {};
    const driftScore = candidate?.drift_source_score;
    const finalScore = candidate?.investigation_score ?? f.score;
    const classification = candidate?.investigation_classification || f.classification || a.classification || candidate?.classification || "UNRESOLVED";
    const confidence = candidate?.investigation_confidence || f.confidence || "LOW";
    const coverage = candidate?.investigation_evidence_coverage ?? f.available_weight;
    const components = f.components || {};

    const scoreText = finalScore == null ? 'N/A' : (Number(finalScore) * 100).toFixed(0) + '%';
    const scoreWidth = finalScore == null ? 0 : Math.round(Math.max(0, Math.min(1, Number(finalScore))) * 100);

    const rows = [
      ["Spatial separation", value(a.spatial_distance_km ?? candidate?.spatial_distance_km)],
      ["Temporal separation", value(a.temporal_delta_min ?? candidate?.temporal_delta_min) + " min"],
      ["Spatial evidence", bar(components.spatial ?? a.distance_score)],
      ["Temporal evidence", bar(components.temporal ?? a.time_score)],
      ["AIS continuity", esc(history.status || "NOT_ASSESSABLE")],
      ["AIS gap", esc(a.ais_gap_status || history.gap_status || "NOT_ESTABLISHED")],
      ["Trajectory", esc(trajectory.status || "NOT_AVAILABLE")],
      ["Drift source proximity", bar(driftScore)],
      ["Evidence coverage", bar(coverage)],
      ["RF corroboration", esc(candidate?.rf_status || f.rf_status || "NOT_IMPLEMENTED")]
    ];

    root.innerHTML =
      '<div class="evidence-title">VESSEL INVESTIGATION</div>' +
      '<div class="evidence-meta">MMSI: ' + esc(candidate?.mmsi || "UNRESOLVED") + '</div>' +
      '<div style="margin:10px 0 12px;padding:11px 12px;border:1px solid var(--border);border-radius:8px;background:var(--bg-app);">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">' +
          '<span style="font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;">Unified investigation score</span>' +
          '<strong style="font-size:18px;">' + scoreText + '</strong>' +
        '</div>' +
        '<div style="height:7px;background:var(--border);border-radius:8px;overflow:hidden;"><span style="display:block;height:100%;width:' + scoreWidth + '%;background:var(--accent-blue);border-radius:8px;"></span></div>' +
        '<div style="display:flex;justify-content:space-between;margin-top:7px;font-size:10px;color:var(--text-secondary);"><span>' + esc(classification) + '</span><span>' + esc(confidence) + ' confidence</span></div>' +
      '</div>' +
      '<div class="evidence-rows">' +
      rows.map(r => '<div class="evidence-row"><span>' + esc(r[0]) + '</span><span>' + r[1] + '</span></div>').join("") +
      '</div>' +
      '<div class="evidence-classification">' + esc(classification) + '</div>' +
      '<div class="evidence-warning">⚠ Investigative evidence only — does not establish responsibility.</div>';
  };
})();
