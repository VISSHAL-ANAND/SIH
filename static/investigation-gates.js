// Phase 4C — render evidence decision gates without inventing evidence.
(function () {
    function byId(id) { return document.getElementById(id); }

    window.renderInvestigationGates = function (incident) {
        const root = byId("investigation-gates");
        if (!root) return;

        const ais = incident?.ais || {};
        const rf = incident?.rf || {};
        const drift = incident?.drift || {};
        const gates = [
            ["SAR DETECTED", Boolean(incident?.spill), "SAR_ANALYSIS"],
            ["LOCATION AVAILABLE", Boolean((incident?.geolocation?.hulls || []).length), "GEOLOCATION"],
            ["AIS DATA", !["NOT_REQUESTED", "UNAVAILABLE"].includes(ais.source_status), "AIS"],
            ["DARK-VESSEL REVIEW", (incident?.candidates || []).some(c =>
                ["UNRESOLVED", "WEAK_CANDIDATE"].includes(c?.association?.classification)
            ), "EVIDENCE_REVIEW"],
            ["DRIFT ANALYSIS", drift.status === "COMPLETED", "DRIFT"],
            ["RF CORROBORATION", rf.status === "CORROBORATED", "RF"],
        ];

        root.innerHTML = gates.map(([label, ok, source]) =>
            '<div class="gate-row">' +
              '<span class="gate-indicator">' + (ok ? '✓' : '○') + '</span>' +
              '<span class="gate-label">' + label + '</span>' +
              '<span class="gate-source">' + source + '</span>' +
            '</div>'
        ).join("");
    };
})();
