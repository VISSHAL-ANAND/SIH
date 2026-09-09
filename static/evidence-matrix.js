// Phase 4G — explainable candidate evidence matrix.
(function () {
  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }
  function bar(v) {
    if (v == null || Number.isNaN(Number(v))) return '<span class="evidence-na">N/A</span>';
    const n = Math.max(0, Math.min(1, Number(v)));
    return '<span class="evidence-bar"><span style="width:' + Math.round(n*100) + '%"></span></span> <b>' + n.toFixed(2) + '</b>';
  }
  window.renderEvidenceMatrix = function (candidate) {
    const root = document.getElementById("evidence-matrix");
    if (!root) return;
    const e = candidate?.evidence || candidate?.components || {};
    const fused = candidate?.fusion || {};
    const rows = [
      ["Spatial", e.spatial ?? e.proximity],
      ["Temporal", e.temporal],
      ["Continuity", e.continuity ?? e.ais_continuity],
      ["Trajectory", e.trajectory],
      ["Drift", e.drift],
      ["RF", e.rf]
    ];
    root.innerHTML =
      '<div class="evidence-title">VESSEL INVESTIGATION</div>' +
      '<div class="evidence-meta">MMSI: ' + esc(candidate?.mmsi) + '</div>' +
      '<div class="evidence-rows">' +
      rows.map(r => '<div class="evidence-row"><span>' + esc(r[0]) + '</span><span>' + bar(r[1]) + '</span></div>').join("") +
      '</div>' +
      '<div class="evidence-classification">' + esc(candidate?.classification || fused.classification || "UNRESOLVED") + '</div>' +
      '<div class="evidence-warning">⚠ Investigative evidence only — does not establish responsibility.</div>';
  };
})();
