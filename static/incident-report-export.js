// Phase 4L — export the currently displayed incident report as JSON.
(function () {
  function download(text, filename) {
    const blob = new Blob([text], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  window.exportIMWIncidentReport = function (report) {
    if (!report) return {ok: false, reason: "NO_REPORT"};
    const id = String(report.incident_id || "incident").replace(/[^a-zA-Z0-9_-]/g, "_");
    download(JSON.stringify(report, null, 2), "IMW-" + id + ".json");
    return {ok: true};
  };
})();
