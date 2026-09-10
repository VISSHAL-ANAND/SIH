// Phase 5C — connect the canonical incident to all operator UI modules.
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
        window.imwPendingResponse = draft;
        window.renderIncidentResponse(draft);
      }
    },
    setReport(report) { latestReport = report; },
    exportReport() {
      if (!latestReport) return {ok:false, reason:'NO_REPORT'};
      return window.exportIMWIncidentReport ? window.exportIMWIncidentReport(latestReport) : {ok:false, reason:'EXPORT_MODULE_UNAVAILABLE'};
    }
  };

  // The legacy app owns the upload flow. Intercept only the process-sar
  // response so the canonical incident package is rendered immediately,
  // without changing or duplicating the upload request.
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function (...args) {
    const response = await nativeFetch(...args);
    try {
      const requestUrl = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
      if (requestUrl.endsWith('/api/process-sar') && response.ok) {
        const copy = response.clone();
        copy.json().then(payload => {
          const incident = payload?.incident || null;
          if (incident && window.imwIntegration) window.imwIntegration.sync(incident);
        }).catch(() => {});
      }
    } catch (_) {}
    return response;
  };
})();
