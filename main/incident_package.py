"""Canonical IMW incident evidence package.

Keeps detection, geolocation, AIS, trajectory, environmental/drift and
candidate evidence together so the dashboard can render one auditable object.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class IncidentTimelineEvent:
    timestamp: str
    event_type: str
    title: str
    details: str
    source: str


@dataclass
class CandidateVessel:
    mmsi: str | None
    vessel_name: str | None
    association: dict[str, Any]
    history: dict[str, Any] | None = None
    trajectory: dict[str, Any] | None = None


@dataclass
class IncidentEvidencePackage:
    incident_id: str
    status: str
    created_at: str
    detection: dict[str, Any]
    geolocation: dict[str, Any]
    spill: dict[str, Any]
    ais: dict[str, Any]
    environmental: dict[str, Any]
    drift: dict[str, Any]
    candidates: list[CandidateVessel] = field(default_factory=list)
    rf: dict[str, Any] = field(default_factory=lambda: {
        "status": "NOT_AVAILABLE",
        "records": [],
        "reason": "RF corroboration has not been connected.",
    })
    timeline: list[IncidentTimelineEvent] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def build_incident_package(
    incident_id: str,
    detection: dict[str, Any],
    geolocation: dict[str, Any],
    spill: dict[str, Any],
    ais: dict[str, Any],
    environmental: dict[str, Any] | None = None,
    drift: dict[str, Any] | None = None,
    rf: dict[str, Any] | None = None,
    candidates: list[CandidateVessel] | None = None,
    limitations: list[str] | None = None,
) -> IncidentEvidencePackage:
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    package = IncidentEvidencePackage(
        incident_id=incident_id,
        status="UNDER_INVESTIGATION",
        created_at=now,
        detection=detection,
        geolocation=geolocation,
        spill=spill,
        ais=ais,
        environmental=environmental or {"status": "NOT_AVAILABLE"},
        drift=drift or {"status": "AWAITING_ENVIRONMENTAL_DATA"},
        rf=rf or {"status": "NOT_AVAILABLE", "records": [], "reason": "No RF observations were supplied."},
        candidates=candidates or [],
        limitations=limitations or [],
    )

    ts = detection.get("timestamp") or now
    package.timeline.append(IncidentTimelineEvent(
        timestamp=str(ts),
        event_type="SAR_DETECTION",
        title="Oil spill detected",
        details="SAR analysis produced a candidate spill observation.",
        source="SAR_ANALYSIS",
    ))
    if candidates:
        package.timeline.append(IncidentTimelineEvent(
            timestamp=now,
            event_type="AIS_CORRELATION",
            title="AIS candidate vessels correlated",
            details=f"{len(candidates)} candidate vessel(s) available for investigation.",
            source="AIS",
        ))
    if package.rf.get("status") != "NOT_AVAILABLE":
        package.timeline.append(IncidentTimelineEvent(
            timestamp=now,
            event_type="RF_CORROBORATION",
            title="RF corroboration available",
            details="RF records were supplied for cross-checking.",
            source="RF",
        ))
    return package


def incident_to_dict(package: IncidentEvidencePackage) -> dict[str, Any]:
    return asdict(package)
