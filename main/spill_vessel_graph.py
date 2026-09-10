"""Aggregate observed hull/AIS candidates into an auditable spill-vessel graph.

This groups repeated observations of the same MMSI without treating the vessel
as responsible for the spill. It is an evidence organization layer only.
"""
from __future__ import annotations


def build_spill_vessel_graph(candidates: list[dict], ranked: list[dict]) -> dict:
    ranked_by_mmsi = {str(x.get("mmsi")): x for x in ranked if x.get("mmsi") is not None}
    vessels: dict[str, dict] = {}
    unresolved = []

    for candidate in candidates:
        mmsi = candidate.get("matched_mmsi")
        if mmsi is None:
            unresolved.append(candidate.get("hull_id"))
            continue
        key = str(mmsi)
        node = vessels.setdefault(key, {
            "mmsi": key,
            "vessel_name": candidate.get("matched_vessel_name"),
            "hull_ids": [],
            "observations": 0,
            "best_priority_score": None,
            "best_priority": "LOW",
            "responsibility_status": "NOT_ESTABLISHED",
        })
        hull_id = candidate.get("hull_id")
        if hull_id not in node["hull_ids"]:
            node["hull_ids"].append(hull_id)
        node["observations"] += 1
        ranked_item = ranked_by_mmsi.get(key)
        if ranked_item:
            score = ranked_item.get("priority_score")
            if score is not None and (node["best_priority_score"] is None or score > node["best_priority_score"]):
                node["best_priority_score"] = score
                node["best_priority"] = ranked_item.get("priority", "LOW")

    nodes = sorted(vessels.values(), key=lambda x: x["best_priority_score"] if x["best_priority_score"] is not None else -1, reverse=True)
    return {
        "status": "OBSERVED_EVIDENCE_GRAPH",
        "vessel_count": len(nodes),
        "nodes": nodes,
        "unresolved_hulls": unresolved,
        "responsibility_status": "NOT_ESTABLISHED",
        "interpretation": "Repeated hull observations are grouped by MMSI for investigation. Grouping and ranking do not establish causation or legal responsibility.",
    }
