// Phase 5E — canonical incident/UI/report synchronization.
(function () {
  let latestReport = null;

  function renderEnvironmentalDrift(incident) {
    const host = document.getElementById('environmental-drift');
    if (!host) return;
    const drift = incident?.drift || {};
    const env = incident?.environmental || {};
    const status = String(drift.status || 'NOT_AVAILABLE').toUpperCase();
    const available = status === 'ESTIMATED';
    const badgeClass = available ? 'warning' : 'neutral';
    const origin = available && drift.origin_lat != null && drift.origin_lon != null
      ? `${Number(drift.origin_lat).toFixed(5)}, ${Number(drift.origin_lon).toFixed(5)}`
      : '—';
    const uncertainty = drift.uncertainty_km != null ? `${Number(drift.uncertainty_km).toFixed(2)} km` : '—';
    const elapsed = drift.elapsed_hours != null ? `${Number(drift.elapsed_hours).toFixed(2)} h` : '—';
    const observations = env.observation_count ?? 0;
    const assumptions = Array.isArray(drift.assumptions) ? drift.assumptions : [];
    host.innerHTML = `
      <div class="section-label">Environmental Evidence</div>
      <div class="environmental-card">
        <div class="environmental-header">
          <span class="environmental-title">Source-Zone Backtrack</span>
          <span class="status-badge ${badgeClass}">${status}</span>
        </div>
        <div class="environmental-grid">
          <div><span>Estimated zone</span><strong>${origin}</strong></div>
          <div><span>Uncertainty</span><strong>${uncertainty}</strong></div>
          <div><span>Elapsed</span><strong>${elapsed}</strong></div>
          <div><span>Observations</span><strong>${observations}</strong></div>
        </div>
        <div class="environmental-note">${available ? 'Estimated environmental evidence only. This does not establish the spill source or vessel responsibility.' : (drift.reason || 'Environmental observations are not available.')}</div>
        ${assumptions.length ? `<details><summary>Model assumptions</summary><ul>${assumptions.map(a => `<li>${String(a)}</li>`).join('')}</ul></details>` : ''}
      </div>`;
  }

  window.imwIntegration = {
    sync(incident) {
      if (!incident) return;
      window.imwCanonicalIncident = incident;
      if (window.renderInvestigationGates) window.renderInvestigationGates(incident);
      if (window.renderIncidentTimeline) window.renderIncidentTimeline(incident);
      if (window.renderAISInvestigationWindow && incident.ais) window.renderAISInvestigationWindow(incident.ais);
      renderEnvironmentalDrift(incident);
      const candidates = Array.isArray(incident.candidates) ? incident.candidates : [];
      const first = candidates[0];
      if (first && window.renderEvidenceMatrix) window.renderEvidenceMatrix(first);
      if (first && window.openVesselInvestigation) window.openVesselInvestigation(first);
      if (window.renderIncidentResponse && window.buildResponseDraft) {
        const draft = window.buildResponseDraft(incident);
        window.imwPendingResponse = draft;
        window.renderIncidentResponse(draft);
      }
    },
    setReport(report) { latestReport = report; window.imwLatestIncidentReport = report; },
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
    renderEnvironmentalDrift(window.imwCanonicalIncident || null);
    const button = document.getElementById('export-incident-report');
    if (!button) return;
    button.addEventListener('click', async () => {
      const incident = window.imwCanonicalIncident || null;
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
