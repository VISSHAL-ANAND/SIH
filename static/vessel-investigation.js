// Phase 5I — ranked vessel investigation record.
(function () {
  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }

  window.openVesselInvestigation = function (candidate) {
    const root = document.getElementById("vessel-investigation-record");
    if (!root) return;
    const history = candidate?.vessel_history || {};
    const association = candidate?.association || {};
    const ranking = candidate?.ranking || {};
    const trajectory = candidate?.trajectory || {};
    const fmt = (v, suffix = "") => v != null ? String(v) + suffix : "N/A";
    const rows = [
      ["Rank", ranking.rank ?? "N/A"],
      ["Investigation priority", ranking.priority || "UNRANKED"],
      ["MMSI", candidate?.mmsi || ranking.mmsi || "UNRESOLVED"],
      ["Vessel", candidate?.vessel_name || ranking.vessel_name || "Unknown"],
      ["Classification", association.classification || candidate?.classification || "UNRESOLVED"],
      ["Spatial separation", fmt(candidate?.spatial_distance_km, " km")],
      ["Temporal separation", fmt(candidate?.temporal_delta_min, " min")],
      ["AIS coverage", candidate?.coverage_status || ranking.ais_coverage || "NOT_ASSESSABLE"],
      ["AIS gap", association.ais_gap_status || ranking.ais_gap || "NOT_ESTABLISHED"],
      ["History continuity", history.status || ranking.history_continuity || "NOT_ASSESSABLE"],
      ["Trajectory evidence", trajectory.status || "NOT_ASSESSABLE"],
      ["Trajectory score", fmt(trajectory.trajectory_score)],
      ["Nearest pre-event position", fmt(trajectory.nearest_before_km, " km")],
      ["Nearest post-event position", fmt(trajectory.nearest_after_km, " km")],
      ["Heading alignment", fmt(trajectory.heading_alignment_score)],
      ["Evidence confidence", ranking.evidence_confidence || "LOW"],
      ["Responsibility", "NOT_ESTABLISHED"],
    ];
    const reasons = Array.isArray(ranking.reasons) ? ranking.reasons : [];
    const trajectoryReason = trajectory.reason ? '<div class="timeline-row"><span>•</span><span>' + esc(trajectory.reason) + '</span></div>' : '';
    root.innerHTML =
      '<div class="record-title">VESSEL INVESTIGATION RECORD</div>' +
      rows.map(r => '<div class="record-row"><span>' + esc(r[0]) + '</span><b>' + esc(r[1]) + '</b></div>').join("") +
      '<div class="record-subtitle">WHY THIS VESSEL IS RANKED</div>' +
      (reasons.length ? '<div class="record-timeline">' + reasons.map(r => '<div class="timeline-row"><span>•</span><span>' + esc(r) + '</span></div>').join("") + trajectoryReason + '</div>' : '<div class="record-empty">No independent ranking reasons available.</div>') +
      '<div class="record-warning">⚠ Investigative evidence only — trajectory describes observed AIS movement and does not establish causality or responsibility. Operator review required.</div>';
  };
})();
