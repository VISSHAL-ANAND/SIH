// Phase 4D — render AIS before/after evidence without over-interpreting gaps.
(function () {
    function esc(v) {
        return String(v ?? "").replace(/[&<>"']/g, ch => ({
            "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
        }[ch]));
    }

    window.renderAISInvestigationWindow = function (data) {
        const root = document.getElementById("ais-investigation-window");
        if (!root) return;
        const w = data?.window;
        if (!w) {
            root.innerHTML = '<div class="ais-empty">AIS investigation window not available.</div>';
            return;
        }
        const before = data.before_observations || [];
        const after = data.after_observations || [];
        root.innerHTML =
            '<div class="ais-window-header">AIS INVESTIGATION WINDOW</div>' +
            '<div class="ais-detection">Detection: ' + esc(w.detection_time) + '</div>' +
            '<div class="ais-window-columns">' +
              '<section><h4>BEFORE</h4><div class="ais-range">' + esc(w.before.start) + ' → ' + esc(w.before.end) + '</div>' +
                '<div class="ais-count">' + before.length + ' observations</div></section>' +
              '<section><h4>AFTER</h4><div class="ais-range">' + esc(w.after.start) + ' → ' + esc(w.after.end) + '</div>' +
                '<div class="ais-count">' + after.length + ' observations</div></section>' +
            '</div>' +
            '<div class="ais-interpretation">' + esc(data.interpretation || '') + '</div>';
    };
})();
