// Phase 5D — canonical incident integration and report export.
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
    getReport() { return latestReport; },
    exportReport() {
      if (!latestReport) return {ok:false, reason:'NO_REPORT'};
      return window.exportIMWIncidentReport ? window.exportIMWIncidentReport(latestReport) : {ok:false, reason:'EXPORT_MODULE_UNAVAILABLE'};
    }
  };

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function (...args) {
    const response = await nativeFetch(...args);
    try {
      const requestUrl = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
      if (requestUrl.endsWith('/api/process-sar') && response.ok) {
        const copy = response.clone();
        copy.json().then(payload => {
          const incident = payload?.incident || null;
          if (incident) window.imwIntegration.sync(incident);
        }).catch(() => {});
      }
    } catch (_) {}
    return response;
  };

  document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('export-incident-report');
    if (!button) return;
    button.addEventListener('click', async () => {
      const incident = window.currentIncident?.incident || window.currentIncident || null;
      if (!incident?.incident_id) {
        window.showToast?.('No canonical incident available to export.', 'warning');
        return;
      }
      button.disabled = true;
      try {
        const responseDraft = window.imwPendingResponse || null;
        const resp = await nativeFetch('/api/build-report', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({incident, response_draft: responseDraft})
        });
        if (!resp.ok) throw new Error('Report API returned ' + resp.status);
        const report = await resp.json();
        window.imwIntegration.setReport(report);
        const result = window.imwIntegration.exportReport();
        if (!result.ok) throw new Error(result.reason || 'EXPORT_FAILED');
        window.showToast?.('Auditable incident report exported.', 'success');
      } catch (err) {
        window.showToast?.('Could not build report: ' + err.message, 'warning');
      } finally {
        button.disabled = false;
      }
    });
  });
})();
