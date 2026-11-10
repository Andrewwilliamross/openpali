"""The recovery ladder and the map score derived from it."""
from openpali.domain.lifecycles import REBUILD_SCORE, RECOVERY_STAGE, rebuild_score


def test_recovery_stage_never_moves_backwards():
    assert RECOVERY_STAGE.advance('permit', 'application') == 'permit'
    assert RECOVERY_STAGE.advance('permit', 'occupancy') == 'occupancy'
    assert RECOVERY_STAGE.order[0] == 'unknown' and RECOVERY_STAGE.order[-1] == 'occupancy'


def test_rebuild_score_follows_the_recovery_ladder():
    # one score per rung, in ladder order, rising from 0 to 100: the colour
    # ramp can never rank a later milestone below an earlier one
    assert list(REBUILD_SCORE) == list(RECOVERY_STAGE.order)
    scores = list(REBUILD_SCORE.values())
    assert scores[0] == 0 and scores[-1] == 100 and scores == sorted(set(scores))
    assert rebuild_score('permit', 'destroyed') == 40
    assert rebuild_score('permit', 'unknown') is None  # unassessed is not zero
    assert rebuild_score('not-a-stage', 'destroyed') == 0
