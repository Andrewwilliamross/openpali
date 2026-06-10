from datetime import date

from palisades.model import Event, Parcel
from palisades.score import score_all, score_parcel, cohort_transition_medians

TODAY = date(2026, 6, 9)
FIRE = date(2025, 1, 7)


def mk(apn: str, *events: Event) -> Parcel:
    p = Parcel(apn=apn)
    p.events = [Event(FIRE, "destroyed", "Destroyed")] + list(events)
    return p


def test_stage_bands_ordering():
    parcels = [
        mk("1"),
        mk("2", Event(date(2025, 4, 1), "debris_cleared", "Cleared")),
        mk("3", Event(date(2025, 4, 1), "debris_cleared", "c"), Event(date(2026, 5, 20), "permit_submitted", "s")),
        mk("4", Event(date(2026, 5, 1), "permit_issued", "i")),
        mk("5", Event(date(2025, 9, 1), "permit_issued", "i"), Event(date(2026, 5, 25), "inspection", "f", milestone="framing")),
        mk("6", Event(date(2026, 2, 1), "cofo", "done")),
    ]
    score_all(parcels, today=TODAY)
    scores = [p.score for p in parcels]
    stages = [p.stage for p in parcels]
    assert stages == [0, 1, 2, 3, 4, 5]
    assert scores == sorted(scores), f"scores must rise with stage: {scores}"
    assert scores[0] < 8 and scores[-1] == 100


def test_stalled_vs_moving_same_stage():
    # both permitted; one fresh, one silent for 8 months
    fresh = mk("f", Event(date(2026, 5, 30), "permit_issued", "i"))
    stalled = mk("s", Event(date(2025, 10, 1), "permit_issued", "i"))
    cohort = cohort_transition_medians([fresh, stalled])
    score_parcel(fresh, cohort, TODAY)
    score_parcel(stalled, cohort, TODAY)
    assert fresh.stage == stalled.stage == 3
    assert fresh.score > stalled.score, (fresh.score, stalled.score)
    # both stay within the stage-3 band
    assert 40 <= stalled.score <= 49 and 40 <= fresh.score <= 49


def test_construction_milestones_progress():
    base = [Event(date(2025, 8, 1), "permit_issued", "i")]
    foundation = mk("a", *base, Event(date(2026, 1, 10), "inspection", "x", milestone="foundation"))
    framing = mk("b", *base, Event(date(2026, 1, 10), "inspection", "x", milestone="framing"))
    finals = mk("c", *base, Event(date(2026, 5, 10), "inspection", "x", milestone="final"))
    score_all([foundation, framing, finals], today=TODAY)
    assert foundation.score < framing.score < finals.score
    assert finals.score <= 92


def test_eta_present_for_active_stages_only():
    p_active = mk("a", Event(date(2026, 4, 1), "permit_submitted", "s"))
    p_done = mk("d", Event(date(2026, 2, 1), "cofo", "done"))
    p_nothing = mk("n")
    score_all([p_active, p_done, p_nothing], today=TODAY)
    assert p_active.est_completion is not None
    assert p_done.est_completion is None
    assert p_nothing.est_completion is None


def test_stage4_with_inspection_but_no_issue_date():
    # A lot with construction inspections but a null permit-issue date upstream
    # should still score as under-construction (stage 4) with a milestone-based
    # position — never crash or land below the stage-4 band.
    p = mk("x", Event(date(2026, 3, 1), "inspection", "Framing", milestone="framing"))
    score_all([p], today=TODAY)
    assert p.stage == 4
    assert 50 <= p.score <= 92
    assert p.est_completion is not None


def test_coarse_parcel_scored_midband_and_excluded_from_cohort():
    # Malibu/county coarse parcels carry a stage but no dated timeline.
    coarse = Parcel(apn="c", jurisdiction="MALIBU", coarse=True, coarse_stage=3)
    coarse.events = [Event(FIRE, "destroyed", "d")]
    rich = mk("r", Event(date(2025, 6, 1), "permit_submitted", "s"),
              Event(date(2025, 9, 1), "permit_issued", "i"))
    score_all([coarse, rich], today=TODAY)
    assert coarse.stage == 3
    assert 40 <= coarse.score <= 49  # mid stage-3 band
    assert coarse.est_completion is not None
    # coarse parcel must not pollute cohort stats
    from palisades.score import cohort_transition_medians
    cohort = cohort_transition_medians([coarse, rich])
    assert cohort[2]["n"] == 1  # only the rich parcel contributed


def test_cohort_medians_from_observed_transitions():
    parcels = []
    for i in range(20):
        parcels.append(
            mk(
                str(i),
                Event(date(2025, 6, 1), "permit_submitted", "s"),
                Event(date(2025, 9, 1), "permit_issued", "i"),  # 92 days in plan check
            )
        )
    cohort = cohort_transition_medians(parcels)
    assert cohort[2]["n"] == 20
    assert abs(cohort[2]["median"] - 92) <= 1
