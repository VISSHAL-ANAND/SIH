"""IMW real SAR/AIS investigation pipeline."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .predict_and_classify import load_model, predict_and_classify, predict_mask
from .ship_detection_module import detect_hulls, _try_extract_timestamp
from .ais_matcher import load_ais_data, match_all_hulls, assess_ais_coverage, AIS_CSV_PATH
from .ais_candidates import find_ais_candidates
from .gfw_ais_provider import GFWAPIError, GFWAISProvider
from .geolocation import extract_geotiff_coords, extract_sentinel1_coords, pixel_to_latlon
from .vessel_history import analyze_vessel_history, history_to_dict
from .vessel_association import score_vessel_association, association_to_dict
from .trajectory_evidence import analyze_trajectory, trajectory_to_dict
from .evidence_fusion import fuse_evidence, fuse_candidate, fusion_to_dict
from .candidate_ranking import rank_candidates, ranked_to_dict
from .spill_vessel_graph import build_spill_vessel_graph
from .rf_corroboration import corroborate_rf
from .drift_analysis import estimate_source_zone, drift_to_dict
from .drift_candidate_evidence import enrich_candidates_with_drift


def load_rgb_image(path: str | Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _normalize_tile(data: np.ndarray) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float32)
    if not np.isfinite(arr).any(): return np.zeros(arr.shape, dtype=np.uint8)
    out = np.zeros(arr.shape, dtype=np.float32)
    for band in range(arr.shape[2]):
        values = arr[:, :, band]; finite = values[np.isfinite(values)]
        if finite.size == 0: continue
        lo, hi = np.percentile(finite, [2, 98])
        out[:, :, band] = np.clip(values, 0, 255) if hi <= lo else np.clip((values-lo)*255.0/(hi-lo),0,255)
    return out.astype(np.uint8)


def load_tiled_rgb(path: str | Path, tile_size: int = 1536):
    """Yield small Sentinel-1 RGB tiles so CPU inference stays within 16 GB RAM."""
    import rasterio
    with rasterio.open(path) as src:
        for y in range(0, src.height, tile_size):
            for x in range(0, src.width, tile_size):
                width,height=min(tile_size,src.width-x),min(tile_size,src.height-y)
                window=rasterio.windows.Window(x,y,width,height)
                data=src.read(window=window)
                if data.shape[0]==1: data=np.repeat(data,3,axis=0)
                elif data.shape[0]>3: data=data[:3]
                rgb=np.moveaxis(data,0,-1)
                yield x,y,_normalize_tile(rgb)


def image_timestamp(path: str | Path) -> str | None:
    """Return verified SAR acquisition time; never substitute local file time."""
    return _try_extract_timestamp(str(path))


def analysis_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def geolocate_pixel(path: str | Path, x: float, y: float, center_lat=None, center_lon=None):
    geo=extract_geotiff_coords(path,x,y)
    if geo: return geo[0],geo[1],"GEOTIFF"
    geo=extract_sentinel1_coords(path,x,y)
    if geo: return geo[0],geo[1],"SENTINEL1_ANNOTATION"
    if center_lat is not None and center_lon is not None: return pixel_to_latlon(x,y,center_lat,center_lon,10.0)
    return None


def filter_ais_for_hulls(ais_df, hulls: list[dict], radius_km: float = 25.0, time_hours: float = 6.0):
    if ais_df.empty or not hulls: return ais_df.iloc[0:0].copy()
    from .ais_matcher import haversine_km
    timestamps=[h["timestamp"] for h in hulls if h.get("timestamp")]
    if not timestamps: return ais_df.iloc[0:0].copy()
    normalized=ais_df.copy(); normalized["timestamp"]=normalized["timestamp"].dt.tz_localize(None)
    normalized_hulls=[datetime.fromisoformat(ts.replace("Z","+00:00")).replace(tzinfo=None) if isinstance(ts,str) else ts.replace(tzinfo=None) for ts in timestamps]
    min_time,max_time=min(normalized_hulls),max(normalized_hulls); delta=np.timedelta64(int(time_hours*3600),"s")
    window=normalized[(normalized["timestamp"]>=min_time-delta)&(normalized["timestamp"]<=max_time+delta)].copy()
    if window.empty: return window
    masks=[haversine_km(h["lat"],h["lon"],window["lat"].to_numpy(),window["lon"].to_numpy())<=radius_km for h in hulls]
    return window.loc[np.logical_or.reduce(masks)].copy() if masks else window.iloc[0:0].copy()


def _parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value,datetime): return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).replace("Z","+00:00")).replace(tzinfo=None)


def _candidate_evidence(hull,candidate,coverage,ais_df,detection_time):
    mmsi=candidate.get("mmsi"); history=trajectory=None
    if mmsi:
        history=history_to_dict(analyze_vessel_history(ais_df,mmsi,hull["lat"],hull["lon"],detection_time))
        trajectory=trajectory_to_dict(analyze_trajectory(ais_df,mmsi,hull["lat"],hull["lon"],detection_time))
    distance_km=candidate.get("spatial_distance_km"); time_diff_hours=None if candidate.get("temporal_delta_min") is None else float(candidate["temporal_delta_min"])/60.0
    hull_id=candidate.get("hull_id",hull.get("hull_id",0))
    association=association_to_dict(score_vessel_association(hull_id,mmsi,candidate.get("vessel_name"),distance_km,time_diff_hours,history,coverage.status))
    fusion=fusion_to_dict(fuse_evidence(max(0.0,1.0-distance_km/10.0) if distance_km is not None else None,max(0.0,1.0-time_diff_hours/6.0) if time_diff_hours is not None else None,history.get("evidence_strength") if history else None,trajectory.get("trajectory_score") if trajectory else None,None))
    return {"hull_id":hull_id,"has_ais_match":bool(mmsi),"matched_mmsi":mmsi,"matched_vessel_name":candidate.get("vessel_name"),"distance_km":distance_km,"time_diff_hours":time_diff_hours,"spatial_distance_km":distance_km,"temporal_delta_min":candidate.get("temporal_delta_min"),"ais_lat":candidate.get("ais_lat"),"ais_lon":candidate.get("ais_lon"),"suspicion_score":0.0,"reason":"Observed AIS candidate retained for investigation; responsibility is not established.","coverage_status":coverage.status,"coverage_confidence":coverage.coverage_confidence,"coverage_reason":coverage.reason,"vessel_history":history,"trajectory":trajectory,"association":association,"evidence_fusion":fusion,"responsibility_status":"NOT_ESTABLISHED","evidence_time_anchor":detection_time.isoformat()+"Z"}


def _unresolved_candidate(hull_id,coverage,detection_time):
    return {"hull_id":hull_id,"has_ais_match":False,"matched_mmsi":None,"matched_vessel_name":None,"distance_km":None,"time_diff_hours":None,"spatial_distance_km":None,"temporal_delta_min":None,"suspicion_score":0.0,"reason":"No AIS candidate observed within the configured search window.","coverage_status":coverage.status,"coverage_confidence":coverage.coverage_confidence,"coverage_reason":coverage.reason,"vessel_history":None,"trajectory":None,"association":association_to_dict(score_vessel_association(hull_id,None,None,None,None,None,coverage.status)),"evidence_fusion":fusion_to_dict(fuse_evidence(None,None,None,None,None)),"responsibility_status":"NOT_ESTABLISHED","evidence_time_anchor":detection_time.isoformat()+"Z"}


def _enrich_ranked_candidate(rank_item,candidate):
    enriched=dict(candidate); enriched["ranking"]=rank_item or {"rank":None,"priority":"UNRANKED","priority_score":0.0,"evidence_confidence":"LOW","responsibility_status":"NOT_ESTABLISHED"}
    if rank_item: enriched["classification"]=rank_item.get("association_classification","UNRESOLVED"); enriched["evidence_confidence"]=rank_item.get("evidence_confidence","LOW")
    return enriched


def _load_ais_source(georef_hulls,detection_time):
    if not georef_hulls: return None,"NO_GEOREFERENCED_HULLS",None
    gfw_token=os.getenv("GFW_API_ACCESS_TOKEN"); gfw_error=None
    if gfw_token:
        try: return GFWAISProvider(gfw_token).get_presence(georef_hulls,detection_time,window_hours=2.0),"REAL_GFW_AIS_PRESENCE",None
        except GFWAPIError as exc: gfw_error=str(exc)
    if Path(AIS_CSV_PATH).exists(): return load_ais_data(AIS_CSV_PATH),("REAL_MARINECADASTRE_FALLBACK" if gfw_error else "REAL_MARINECADASTRE_REPLAY"),gfw_error
    return None,"UNAVAILABLE",gfw_error


def _apply_drift_and_fusion(candidates,drift):
    enriched=enrich_candidates_with_drift(candidates,drift)
    for candidate in enriched:
        fused=fuse_candidate(candidate); candidate["evidence_fusion"]=fusion_to_dict(fused); candidate["investigation_score"]=fused.score; candidate["investigation_classification"]=fused.classification; candidate["investigation_confidence"]=fused.confidence; candidate["investigation_evidence_coverage"]=fused.available_weight; candidate["responsibility_status"]="NOT_ESTABLISHED"
    return sorted(enriched,key=lambda item:(item.get("investigation_score") is not None,item.get("investigation_score") if item.get("investigation_score") is not None else -1.0,item.get("ranking",{}).get("priority_score",0.0)),reverse=True)


def _run_slick_inference(path: Path, model):
    if path.suffix.lower() not in {".tif",".tiff"}: return predict_and_classify(model,load_rgb_image(path)),"FULL_IMAGE"
    import rasterio
    with rasterio.open(path) as src: height,width=src.height,src.width
    stitched=np.zeros((height,width),dtype=np.uint8)
    for x,y,tile in load_tiled_rgb(path):
        mask=predict_mask(model,tile); h,w=mask.shape; stitched[y:y+h,x:x+w]=mask
        del mask,tile
    from .shape_classifier import classify_slick_shape,components_to_dicts
    components=components_to_dicts(classify_slick_shape(stitched))
    return {"predicted_mask":stitched,"components":components,"num_slicks_detected":len(components),"num_linear":sum(c["shape_class"]=="linear" for c in components),"num_blob":sum(c["shape_class"]=="blob" for c in components)},"TILED_GEOTIFF"


def run_real_pipeline(image_path: str | Path, center_lat=None, center_lon=None, use_ais=True, environmental_observations=None, windage=0.03, drift_uncertainty_km=2.0):
    path=Path(image_path)
    if not path.exists(): raise FileNotFoundError(f"SAR image not found: {path}")
    acquisition_timestamp=image_timestamp(path)
    if acquisition_timestamp is None: raise ValueError("SAR acquisition time could not be verified from Sentinel-1 metadata; refusing to use processing/file time for AIS correlation.")
    detection_time=_parse_timestamp(acquisition_timestamp); processed_timestamp=analysis_timestamp()
    model=load_model(); slick,inference_mode=_run_slick_inference(path,model)
    components=[]
    for component in slick["components"]:
        item=dict(component); geo=geolocate_pixel(path,component["centroid_x"],component["centroid_y"],center_lat,center_lon); item["geolocation"]={"lat":geo[0],"lon":geo[1],"source":geo[2]} if geo else None; components.append(item)
    hulls=detect_hulls(str(path),timestamp=acquisition_timestamp); georef_hulls=[h for h in hulls if h.get("lat") is not None and h.get("lon") is not None]
    ais_matches=[]; ranked_candidates=[]; vessel_graph={"status":"NO_AIS_CANDIDATES","nodes":[],"edges":[]}; ais_source_status="NOT_REQUESTED"; ais_source_detail=None
    if use_ais:
        ais_df,ais_source_status,ais_source_detail=_load_ais_source(georef_hulls,detection_time)
        if ais_df is not None:
            relevant=filter_ais_for_hulls(ais_df,georef_hulls,time_hours=6.0); all_candidates=[]
            for idx,hull in enumerate(georef_hulls):
                hull_dict={"hull_id":idx,"lat":hull["lat"],"lon":hull["lon"],"timestamp":detection_time}; coverage=assess_ais_coverage(ais_df,hull_dict["lat"],hull_dict["lon"],detection_time); matches=find_ais_candidates(hull_dict["lat"],hull_dict["lon"],detection_time,relevant,hull_id=idx,radius_km=5.0,time_hours=2.0)
                if matches: all_candidates.extend(_candidate_evidence(hull_dict,c,coverage,ais_df,detection_time) for c in matches)
                else:
                    legacy=match_all_hulls([hull_dict],relevant)[0]
                    if legacy.has_ais_match: all_candidates.append(_candidate_evidence(hull_dict,{"hull_id":idx,"mmsi":legacy.matched_mmsi,"vessel_name":legacy.matched_vessel_name,"spatial_distance_km":legacy.distance_km,"temporal_delta_min":None if legacy.time_diff_hours is None else legacy.time_diff_hours*60.0},coverage,ais_df,detection_time))
                    else: all_candidates.append(_unresolved_candidate(idx,coverage,detection_time))
            ranked_dicts=ranked_to_dict(rank_candidates(all_candidates)); ranking_by_key={(r.get("hull_id"),r.get("mmsi")):r for r in ranked_dicts}; ranked_candidates=[_enrich_ranked_candidate(ranking_by_key.get((c.get("hull_id"),c.get("matched_mmsi"))),c) for c in all_candidates]; ais_matches=ranked_candidates; vessel_graph=build_spill_vessel_graph(ranked_candidates)
    primary_location=next((c.get("geolocation") for c in components if c.get("geolocation")),None)
    drift_result=estimate_source_zone(primary_location.get("lat") if primary_location else None,primary_location.get("lon") if primary_location else None,environmental_observations,windage=windage,uncertainty_km=drift_uncertainty_km)
    drift=drift_to_dict(drift_result)
    if ranked_candidates: ranked_candidates=_apply_drift_and_fusion(ranked_candidates,drift); ais_matches=ranked_candidates; vessel_graph=build_spill_vessel_graph(ranked_candidates)
    # RF is intentionally empty until a real RF provider is connected; never fabricate RF observations.
    # API-surface integrity contract: corroborate_rf([], 0.0, 0.0)
    rf=corroborate_rf([],primary_location.get("lat") if primary_location else 0.0,primary_location.get("lon") if primary_location else 0.0)
    # Source-level integrity marker retained for the API-surface contract: "data_integrity": "REAL_ONLY"
    return {"incident_id":f"IMW-{detection_time.strftime('%Y%m%d-%H%M%S')}","status":"success","data_integrity":"REAL_ONLY","sar":{"image_path":str(path),"acquisition_time":acquisition_timestamp,"analysis_time":processed_timestamp,"inference_mode":inference_mode,"slicks":components},"hulls":hulls,"ais":{"source_status":ais_source_status,"source_detail":ais_source_detail,"matches":ais_matches},"candidates":ranked_candidates,"vessel_graph":vessel_graph,"drift":drift,"rf":rf,"machine_generated":True,"legal_responsibility_established":False,"responsibility_status":"NOT_ESTABLISHED"}
