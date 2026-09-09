// Phase 4M.1 — connect canonical incident data to Phase 4 UI modules.
(function () {
  let latestReport = null;
  window.imwIntegration = {
    sync(incident) {
      if (!incident) return;
      if (window.renderInvestigationGates) window.renderInvestigationGates(incident);
      if (window.renderIncidentTimeline) window.renderIncidentTimeline(incident);
      const candidates = incident.candidates || [];
      const first = candidates[0];
      if (first && window.renderEvidenceMatrix) window.renderEvidenceMatrix(first);
      if (first && window.openVesselInvestigation) window.openVesselInvestigation(first);
      if (window.renderIncidentResponse && window.buildResponseDraft) {
        const draft = window.buildResponseDraft(incident);
        window.renderIncidentResponse(draft);
      }
    },
    setReport(report) { latestReport = report; },
    exportReport() {
      if (!latestReport) return {ok:false, reason:'NO_REPORT'};
      return window.exportIMWIncidentReport ? window.exportIMWIncidentReport(latestReport) : {ok:false, reason:'EXPORT_MODULE_UNAVAILABLE'};
    }
  };
})();
