// Phase 6 — evidence-first investigation map.
// Renders observed SAR/hull/AIS evidence separately from estimated drift evidence.
(function () {
  function esc(v) { return String(v ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c])); }
  function finite(v) { return Number.isFinite(Number(v)); }
  function coords(lat, lon) { return finite(lat) && finite(lon) ? [Number(lat), Number(lon)] : null; }
  function candidatePosition(c) { return coords(c?.ais_lat ?? c?.position?.lat ?? c?.history?.last_position?.lat, c?.ais_lon ?? c?.position?.lon ?? c?.history?.last_position?.lon); }
  function spillPosition(i) { const g=i?.geolocation||{},s=i?.spill||{}; return coords(g.center_lat??g.latitude??s.center_lat??s.latitude??i?.detection?.lat,g.center_lon??g.longitude??s.center_lon??s.longitude??i?.detection?.lon); }
  function trajectoryPoints(c) { return Array.isArray(c?.trajectory?.points) ? c.trajectory.points.map(p=>coords(p?.lat,p?.lon)).filter(Boolean) : []; }
  function popup(title,status,details) { return '<div class="imw-map-popup"><b>'+esc(title)+'</b><br><span class="imw-popup-status">'+esc(status)+'</span><br>'+esc(details)+'</div>'; }
  function key(c,i) { return String(c?.mmsi||c?.vessel_name||i); }

  function syncCandidate(candidate,index) {
    const k=key(candidate,index); window.__imwSelectedCandidateKey=k;
    window.__imwInvestigationCandidateMarkers?.forEach(m=>m.setRadius(m.__imwSelected?8:7).setStyle({weight:m.__imwSelected?4:2}));
    const m=window.__imwInvestigationCandidateMarkers?.get(k);
    if(m){m.__imwSelected=true;m.setRadius(11).setStyle({weight:4});}
    window.__imwInvestigationSelectedCandidate=candidate;
    if(typeof window.renderVesselInvestigation==='function') window.renderVesselInvestigation(candidate);
    document.dispatchEvent(new CustomEvent('imw:candidate-selected',{detail:{candidate,index,key:k}}));
  }
  window.selectInvestigationCandidate=syncCandidate;

  window.renderIncidentMap=function(incident){
    if(typeof map==='undefined'||!incident)return;
    if(window.__imwInvestigationMapLayers)window.__imwInvestigationMapLayers.forEach(l=>l.remove());
    const observed=L.layerGroup().addTo(map),estimated=L.layerGroup().addTo(map),layers=[observed,estimated];
    window.__imwInvestigationMapLayers=layers;window.__imwInvestigationCandidateMarkers=new Map();
    const bounds=[],spill=spillPosition(incident),drift=incident?.drift||{};
    if(spill){const m=L.circleMarker(spill,{radius:9,weight:3,fillOpacity:.35}).addTo(observed);m.bindPopup(popup('SAR SPILL ANCHOR','OBSERVED / SAR','Georeferenced incident location from SAR analysis.'));bounds.push(spill);}
    const origin=coords(drift.origin_lat,drift.origin_lon);
    if(origin&&String(drift.status||'').toUpperCase()==='ESTIMATED'){
      const zone=L.circle(origin,{radius:Math.max(500,Number(drift.uncertainty_km||1)*1000),weight:2,dashArray:'7 5',fillOpacity:.1}).addTo(estimated);
      zone.bindPopup(popup('ESTIMATED DRIFT SOURCE ZONE','ESTIMATED / ENVIRONMENTAL MODEL','Uncertainty: '+Number(drift.uncertainty_km||0).toFixed(2)+' km. Modelled evidence, not a legal attribution radius.'));bounds.push(origin);
    }
    const candidates=Array.isArray(incident.candidates)?incident.candidates:[];
    candidates.forEach((c,i)=>{
      const p=candidatePosition(c),k=key(c,i); if(p){const m=L.circleMarker(p,{radius:k===window.__imwSelectedCandidateKey?11:7,weight:k===window.__imwSelectedCandidateKey?4:2,fillOpacity:.45}).addTo(observed);m.__imwSelected=k===window.__imwSelectedCandidateKey;m.bindPopup(popup(c.vessel_name||'Candidate vessel','OBSERVED / AIS','MMSI: '+(c.mmsi||'—')+'. Correlation is investigative evidence; responsibility is not established.'));m.on('click',()=>syncCandidate(c,i));window.__imwInvestigationCandidateMarkers.set(k,m);bounds.push(p);}
      const track=trajectoryPoints(c); if(track.length>=2){const line=L.polyline(track,{weight:k===window.__imwSelectedCandidateKey?5:3,opacity:.75}).addTo(observed);line.bindPopup(popup('AIS TRAJECTORY','OBSERVED / AIS TRACK',c?.trajectory?.status||'Observed trajectory available.'));line.on('click',()=>syncCandidate(c,i));track.forEach(x=>bounds.push(x));}
    });
    const legend=L.control({position:'topright'});legend.onAdd=function(){const d=L.DomUtil.create('div','imw-map-legend');d.innerHTML='<div class="imw-legend-title">EVIDENCE LAYERS</div><div><i class="imw-legend-dot observed"></i> Observed SAR / AIS</div><div><i class="imw-legend-line observed"></i> Observed AIS trajectory</div><div><i class="imw-legend-zone estimated"></i> Estimated drift zone</div><div class="imw-legend-note">Click vessel/track to inspect candidate evidence<br>Evidence only · responsibility not established</div>';L.DomEvent.disableClickPropagation(d);return d;};legend.addTo(map);layers.push(legend);
    if(bounds.length)map.fitBounds(L.latLngBounds(bounds),{padding:[55,55],maxZoom:12});
  };
})();
