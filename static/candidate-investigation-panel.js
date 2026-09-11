// Phase 6A — synchronized candidate investigation panel.
(function () {
  function esc(v) {
    return String(v ?? "").replace(/[&<>\"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#39;"}[c]));
  }

  function fmt(v, suffix = "") {
    return v == null || v === "" ? "N/A" : `${v}${suffix}`;
  }

  function status(v, fallback = "NOT_ASSESSABLE") {
    return String(v || fallback).toUpperCase();
  }

  function score(v) {
    if (v == null || Number.isNaN(Number(v))) return "N/A";
    return `${(Number(v) * 100).toFixed(0)}%`;
  }

  function row(label, value) {
    return `<div style="display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid var(--border-light);"><span style="color:var(--text-muted);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;">${esc(label)}</span><strong style="font-size:11px;text-align:right;max-width:62%;word-break:break-word;">${esc(value)}</strong></div>`;
  }

  window.renderCandidateInvestigationPanel = function (candidate) {
    const root = document.getElementById("candidate-investigation-panel");
    if (!root) return;

    const c = candidate || {};
    const ranking = c.ranking || {};
    const association = c.association || {};
    const history = c.vessel_history || c.history || {};
    const trajectory = c.trajectory || {};
    const fusion = c.evidence_fusion || c.fusion || {};
    const classification = c.investigation_classification || fusion.classification || "UNRESOLVED";
    const confidence = c.investigation_confidence || fusion.confidence || "LOW";
    const coverage = c.investigation_evidence_coverage ?? fusion.available_weight;
    const finalScore = c.investigation_score ?? fusion.score;
    const rf = status(c.rf_status || fusion.rf_status, "NOT_IMPLEMENTED");
    const gap = status(association.ais_gap_status || history.gap_status, "NOT_ESTABLISHED");
    const continuity = status(history.status || ranking.history_continuity);
    const trajectoryStatus = status(trajectory.status, "NOT_AVAILABLE");
    const driftStatus = status(c.drift_source_status || c.drift?.status, "NOT_AVAILABLE");
    const selectedKey = `${c.mmsi ?? "unresolved"}:${c.hull_id ?? "unresolved"}`;

    root.innerHTML = `
      <div style="border:1px solid var(--border);border-radius:10px;background:var(--bg-panel);overflow:hidden;box-shadow:var(--shadow-sm);">
        <div style="padding:10px 12px;background:var(--accent-blue-bg);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:8px;">
          <div><div style="font-size:10px;font-weight:800;letter-spacing:.08em;color:var(--accent-blue);text-transform:uppercase;">Candidate Investigation</div><div style="font-size:13px;font-weight:700;margin-top:2px;">${esc(c.vessel_name || "Unknown vessel")}</div></div>
          <span style="font-size:10px;font-weight:800;padding:3px 7px;border-radius:4px;background:var(--accent-amber-bg);color:var(--accent-amber);">${esc(classification)}</span>
        </div>
        <div style="padding:10px 12px;">
          <div style="display:flex;justify-content:space-between;align-items:end;margin-bottom:6px;"><span style="font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;">Unified score</span><strong style="font-size:22px;">${score(finalScore)}</strong></div>
          <div style="height:7px;background:var(--border-light);border-radius:8px;overflow:hidden;"><span style="display:block;height:100%;width:${finalScore == null ? 0 : Math.max(0,Math.min(1,Number(finalScore)))*100}%;background:var(--accent-blue);border-radius:8px;"></span></div>
          <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:10px;color:var(--text-secondary);"><span>${esc(confidence)} confidence</span><span>Coverage ${score(coverage)}</span></div>

          <div style="margin-top:10px;">${row("MMSI", c.mmsi || "UNRESOLVED")}${row("AIS observation", fmt(c.ais_observation_time))}${row("SAR ↔ AIS distance", fmt(c.spatial_distance_km," km"))}${row("SAR ↔ AIS time", fmt(c.temporal_delta_min," min"))}${row("AIS continuity", continuity)}${row("AIS gap evidence", gap)}${row("Trajectory", trajectoryStatus)}${row("Trajectory score", fmt(trajectory.trajectory_score))}${row("Movement alignment", fmt(trajectory.movement_alignment_score))}${row("Drift source-zone", driftStatus)}${row("Drift proximity score", score(c.drift_source_score))}${row("RF corroboration", rf)}</div>

          <div style="margin-top:10px;padding:9px 10px;border:1px solid #fecaca;border-radius:7px;background:var(--accent-red-bg);color:var(--accent-red);font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;">⚠ Responsibility: NOT ESTABLISHED</div>
          <div style="margin-top:7px;font-size:10px;line-height:1.5;color:var(--text-secondary);">Observed AIS correlation and trajectory evidence support investigation prioritization only. AIS gaps do not prove intentional shutdown. Drift-back output is estimated environmental evidence, not a legal attribution radius.</div>
        </div>
      </div>`;

    root.dataset.selectedCandidate = selectedKey;
    window.__imwSelectedCandidateKey = selectedKey;
    window.__imwInvestigationSelectedCandidate = c;
  };

  document.addEventListener("imw:candidate-selected", event => {
    if (event?.detail?.candidate) window.renderCandidateInvestigationPanel(event.detail.candidate);
  });
})();
