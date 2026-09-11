// Phase 6 — evidence-first investigation map.
// Renders observed SAR/hull/AIS evidence separately from estimated drift evidence.
(function () {
  function esc(v) { return String(v ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c])); }
  function finite(v) { return Number.isFinite(Number(v)); }
  function coords(lat, lon) { return finite(lat) && finite(lon) ? [Number(lat), Number(lon)] : null; }
  function candidatePosition(candidate) { return coords(candidate?.ais_lat ?? candidate?.position?.lat ?? candidate?.history?.last_position?.lat, candidate?.ais_lon ?? candidate?.position?.lon ?? candidate?.history?.last_position?.lon); }
  function spillPosition(incident) { const g=incident?.geolocation||{},s=incident?.spill||{}; return coords(g.center_lat??g.latitude??s.center_lat??s.latitude??incident?.detection?.lat,g.center_lon??g.longitude??s.center_lon??s.longitude??incident?.detection?.lon); }
  function trajectoryPoints(candidate) { return Array.isArray(candidate?.trajectory?.points) ? candidate.trajectory.points.map(p=>coords(p?.lat,p?.lon)).filter(Boolean) : []; }
  function popup(title,status,details) { return '<div class="imw-map-popup"><b>'+esc(title)+'</b><br><span class="imw-popup-status">'+esc(status)+'</span><br>'+esc(details)+'</div>'; }
  function key(candidate,index) { return String(candidate?.mmsi||candidate?.vessel_name||index); }

  function syncCandidate(candidate,index) {
    const k=key(candidate,index); window.__imwSelectedCandidateKey=k; window.__imwInvestigationSelectedCandidate=candidate;
    window.__imwInvestigationCandidateMarkers?.forEach(m=>m.setRadius(m.__imwSelected?8:7).setStyle({weight:m.__imwSelected?4:2}));
    const marker=window.__imwInvestigationCandidateMarkers?.get(k);
    if(marker){marker.__imwSelected=true;marker.setRadius(11).setStyle({weight:4});}
    if(typeof window.renderVesselInvestigation==='function') window.renderVesselInvestigation(candidate);
    document.dispatchEvent(new CustomEvent('imw:candidate-selected',{detail:{candidate,index,key:k}}));
  }
  window.selectInvestigationCandidate=syncCandidate;

  window.renderIncidentMap=function(incident){
    if(typeof map==='undefined'||!incident)return;
    if(window.__imwInvestigationMapLayers)window.__imwInvestigationMapLayers.forEach(l=>l.remove());
    const observed=L.layerGroup().addTo(map),estimated=L.layerGroup().addTo(map),layers=[observed,estimated];
    window.__imwInvestigationMapLayers=layers; window.__imwInvestigationCandidateMarkers=new Map();
    const bounds=[],spill=spillPosition(incident),drift=incident?.drift||{};
    if(spill){const marker=L.circleMarker(spill,{radius:9,weight:3,fillOpacity:.35}).addTo(observed);marker.bindPopup(popup('SAR SPILL ANCHOR','OBSERVED / SAR','Georeferenced incident location from SAR analysis.'));bounds.push(spill);}
    const origin=coords(drift.origin_lat,drift.origin_lon);
    if(origin&&String(drift.status||'').toUpperCase()==='ESTIMATED'){
      const zone=L.circle(origin,{radius:Math.max(500,Number(drift.uncertainty_km||1)*1000),weight:2,dashArray:'7 5',fillOpacity:.1}).addTo(estimated);
      zone.bindPopup(popup('ESTIMATED DRIFT SOURCE ZONE','ESTIMATED / ENVIRONMENTAL MODEL','Uncertainty: '+Number(drift.uncertainty_km||0).toFixed(2)+' km. Modelled evidence, not a legal attribution radius.'));bounds.push(origin);
    }
    const candidates=Array.isArray(incident.candidates)?incident.candidates:[];
    candidates.forEach((candidate,index)=>{
      const position=candidatePosition(candidate),candidateKey=key(candidate,index);
      if(position){const selected=candidateKey===window.__imwSelectedCandidateKey;const marker=L.circleMarker(position,{radius:selected?11:7,weight:selected?4:2,fillOpacity:.45}).addTo(observed);marker.__imwSelected=selected;marker.bindPopup(popup(candidate.vessel_name||'Candidate vessel','OBSERVED / AIS','MMSI: '+(candidate.mmsi||'—')+'. Correlation is investigative evidence; responsibility is not established.'));marker.on('click',()=>syncCandidate(candidate,index));window.__imwInvestigationCandidateMarkers.set(candidateKey,marker);bounds.push(position);}
      const track=trajectoryPoints(candidate); if(track.length>=2){const line=L.polyline(track,{weight:candidateKey===window.__imwSelectedCandidateKey?5:3,opacity:.75}).addTo(observed);line.bindPopup(popup('AIS TRAJECTORY','OBSERVED / AIS TRACK',candidate?.trajectory?.status||'Observed trajectory available.'));line.on('click',()=>syncCandidate(candidate,index));track.forEach(point=>bounds.push(point));}
    });
    const legend=L.control({position:'topright'});legend.onAdd=function(){const d=L.DomUtil.create('div','imw-map-legend');d.innerHTML='<div class="imw-legend-title">EVIDENCE LAYERS</div><div><i class="imw-legend-dot observed"></i> Observed SAR / AIS</div><div><i class="imw-legend-line observed"></i> Observed AIS trajectory</div><div><i class="imw-legend-zone estimated"></i> Estimated drift zone</div><div class="imw-legend-note">Click vessel/track to inspect candidate evidence<br>Evidence only · responsibility not established</div>';L.DomEvent.disableClickPropagation(d);return d;};legend.addTo(map);layers.push(legend);
    if(bounds.length)map.fitBounds(L.latLngBounds(bounds),{padding:[55,55],maxZoom:12});
  };
})();
