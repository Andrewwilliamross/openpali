"""Unit tests for the statistical core flagged by the methods review:
IPCW Brier weighting, chronological split blocking, and baseline honesty."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from openpali.ml.experiments import NaiveBaseline, _calibration_bins, _ipcw_brier


# ---------------------------------------------------------------------------
# IPCW Brier
# ---------------------------------------------------------------------------


def _row(duration: int, event: int, **extra) -> dict:
    return {"duration_days": duration, "event_issued": event,
            "submission_month": 1, **extra}


def test_ipcw_no_censoring_equals_plain_brier():
    # all events observed before horizon -> G == 1 everywhere -> plain Brier
    rows = [_row(30, 1), _row(60, 1), _row(90, 1), _row(120, 1)]
    score, evaluable, floor_hits = _ipcw_brier(rows, 180, lambda r: 0.25)
    assert evaluable == 4
    assert floor_hits == 0
    assert score == pytest.approx(0.25**2)


def test_ipcw_survivors_scored_against_one():
    rows = [_row(400, 0), _row(500, 0)]
    score, evaluable, _ = _ipcw_brier(rows, 180, lambda r: 0.9)
    assert evaluable == 2
    assert score == pytest.approx((0.9 - 1.0) ** 2)


def test_ipcw_censored_before_horizon_dilutes_denominator_only():
    # one event + one early-censored row: the censored row contributes 0 to
    # the numerator but stays in n (Graf denominator)
    rows = [_row(30, 1), _row(40, 0)]
    score, evaluable, _ = _ipcw_brier(rows, 180, lambda r: 0.5)
    assert evaluable == 1
    # G(29.5) = 1 (censoring event at 40 hasn't happened yet)
    assert score == pytest.approx(0.5**2 / 2)


def test_ipcw_event_weight_uses_left_limit_of_G():
    # censoring at day 30 AND an event at day 30: the event's weight must use
    # G(30-) = 1.0 (before the drop), not G(30) < 1
    rows = [_row(30, 1), _row(30, 0), _row(200, 0)]
    score, evaluable, _ = _ipcw_brier(rows, 180, lambda r: 0.0)
    # event contributes 0 (perfect prediction of issuance); survivor term:
    # weight 1/G(180): G drops at t=30 by factor (1 - 1/2)... KM on censoring
    # with 1 censor among {30ev,30cs,200cs}: risk set at 30 has 3, censor
    # event count 1 -> G(30)=2/3; G(180)=2/3.
    survivor = (0.0 - 1.0) ** 2 / (2 / 3)
    assert score == pytest.approx(survivor / 3)
    # sanity: if the implementation used G(30) for the event the score would
    # differ (event term would be 0 either way here) — assert via a nonzero
    # event prediction instead
    score2, _, _ = _ipcw_brier(rows, 180, lambda r: 0.4)
    event_term = 0.4**2 / 1.0  # G(29.5) == 1.0 (left limit)
    survivor_term = (0.4 - 1.0) ** 2 / (2 / 3)
    assert score2 == pytest.approx((event_term + survivor_term) / 3)


def test_ipcw_heavy_censoring_still_bounded_and_counted():
    # heavy censoring: weights inflate but stay finite; the diagnostic counter
    # returns a number (0 here — G = 1/31 is small but above the floor)
    rows = [_row(10, 0)] * 30 + [_row(15, 1)]
    score, evaluable, floor_hits = _ipcw_brier(rows, 180, lambda r: 0.5)
    assert evaluable == 1
    assert floor_hits == 0
    # event weight = 1/G(14.5) = 31
    assert score == pytest.approx(31 * 0.25 / 31)


# ---------------------------------------------------------------------------
# chronological split blocks (rolling-origin-v2)
# ---------------------------------------------------------------------------


def test_split_blocks_are_contiguous_in_time():
    from openpali.ml.dataset import FINAL_BLOCK_DAYS, ROLLING_FOLDS

    cutoff = date(2026, 7, 1)
    origins = [cutoff - timedelta(days=365) + timedelta(days=i) for i in range(360)]
    rows = [{"origin_date": o.isoformat()} for o in sorted(origins)]

    # replicate the production assignment (dataset.py)
    final_block_start = cutoff - timedelta(days=FINAL_BLOCK_DAYS)
    train_rows = [r for r in rows if date.fromisoformat(r["origin_date"]) < final_block_start]
    n_train = len(train_rows)
    for index, row in enumerate(train_rows):
        block = min(index * ROLLING_FOLDS // max(n_train, 1), ROLLING_FOLDS - 1)
        row["split"] = f"fold_{block}"
    for row in rows:
        if date.fromisoformat(row["origin_date"]) >= final_block_start:
            row["split"] = "final_holdout"

    # every fold_k origin must be <= every fold_{k+1} origin (contiguity)
    max_origin = {}
    min_origin = {}
    for row in rows:
        s = row["split"]
        o = row["origin_date"]
        max_origin[s] = max(max_origin.get(s, o), o)
        min_origin[s] = min(min_origin.get(s, o), o)
    assert max_origin["fold_0"] <= min_origin["fold_1"]
    assert max_origin["fold_1"] <= min_origin["fold_2"]
    assert max_origin["fold_2"] <= min_origin["final_holdout"]


# ---------------------------------------------------------------------------
# naive baseline horizon honesty + calibration bin mass
# ---------------------------------------------------------------------------


def test_naive_baseline_is_horizon_specific():
    rows = (
        [_row(50, 1)] * 30      # issued by day 50 (counts at 90 and 180)
        + [_row(120, 1)] * 30   # issued by 120 (counts at 180 only)
        + [_row(400, 0)] * 40   # survivors past both horizons
    )
    naive = NaiveBaseline()
    naive.fit(rows)
    assert naive.survival(rows[0], 180) == pytest.approx(1 - 60 / 100)
    assert naive.survival(rows[0], 90) == pytest.approx(1 - 30 / 100)
    with pytest.raises(ValueError):
        naive.survival(rows[0], 45)


def test_calibration_bins_enforce_minimum_mass():
    rows = [_row(30, 1)] * 10  # only 10 definitive rows: below the minimum
    bins = _calibration_bins(rows, 180, lambda r: 0.5)
    assert bins == []
