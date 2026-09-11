from main.candidate_ranking import rank_candidates, ranked_to_dict


def test_multiple_candidates_are_ranked_without_responsibility_claim():
    ranked = rank_candidates([
        {
            "matched_mmsi": "111",
            "matched_vessel_name": "ALPHA",
            "distance_km": 1.0,
            "time_diff_hours": 0.2,
            "coverage_status": "LOCAL_AIS_ACTIVITY",
            "vessel_history": {"status": "CONTINUITY_OBSERVED", "evidence_strength": 0.9},
            "trajectory": {"trajectory_score": 0.8},
            "association": {"classification": "STRONG_CANDIDATE"},
        },
        {
            "matched_mmsi": "222",
            "matched_vessel_name": "BRAVO",
            "distance_km": 4.0,
            "time_diff_hours": 1.5,
            "coverage_status": "LOCAL_AIS_ACTIVITY",
            "vessel_history": {"status": "PRE_EVENT_HISTORY_ONLY", "evidence_strength": 0.15},
            "trajectory": {"trajectory_score": 0.2},
            "association": {"classification": "POSSIBLE_CANDIDATE"},
        },
    ])
    assert len(ranked) == 2
    assert ranked[0].mmsi == "111"
    assert ranked[0].rank == 1
    assert ranked[0].priority_score > ranked[1].priority_score
    assert all(x.association_classification != "RESPONSIBLE" for x in ranked)


def test_unresolved_candidate_remains_unresolved():
    ranked = rank_candidates([{"matched_mmsi": None, "distance_km": None, "time_diff_hours": None}])
    payload = ranked_to_dict(ranked)
    assert payload[0]["association_classification"] == "UNRESOLVED"
    assert payload[0]["responsibility_status"] == "NOT_ESTABLISHED"


def test_confirmed_ais_gap_raises_priority_without_claiming_responsibility():
    base = {
        "matched_mmsi": "111",
        "matched_vessel_name": "ALPHA",
        "distance_km": 2.0,
        "time_diff_hours": 0.5,
        "coverage_status": "LOCAL_AIS_ACTIVITY",
        "vessel_history": {"status": "CONTINUITY_OBSERVED", "evidence_strength": 0.8},
        "trajectory": {"trajectory_score": 0.6},
        "association": {"classification": "POSSIBLE_CANDIDATE"},
    }
    without_gap = rank_candidates([base])[0]
    with_gap = rank_candidates([{**base, "ais_gap": {"status": "AIS_GAP_OBSERVED"}}])[0]

    assert with_gap.priority_score > without_gap.priority_score
    assert with_gap.ais_gap == "AIS_GAP_OBSERVED"
    assert "AIS gap evidence: AIS_GAP_OBSERVED" in with_gap.reasons
    assert ranked_to_dict([with_gap])[0]["responsibility_status"] == "NOT_ESTABLISHED"


def test_unknown_coverage_gap_is_modest_and_not_treated_as_dark_vessel():
    ranked = rank_candidates([{
        "matched_mmsi": "222",
        "distance_km": 2.0,
        "time_diff_hours": 0.5,
        "vessel_history": {"status": "PRE_EVENT_HISTORY_ONLY", "evidence_strength": 0.4},
        "trajectory": {"trajectory_score": 0.4},
        "ais_gap": {"status": "GAP_REQUIRES_COVERAGE_REVIEW"},
        "association": {"classification": "POSSIBLE_CANDIDATE"},
    }])[0]

    assert 0.0 <= ranked.priority_score <= 1.0
    assert ranked.ais_gap == "GAP_REQUIRES_COVERAGE_REVIEW"
    assert ranked.priority != "HIGH" or ranked.priority_score < 0.9
    assert ranked_to_dict([ranked])[0]["responsibility_status"] == "NOT_ESTABLISHED"
