import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from training_gate import check_training


def cleared_row():
    return {"id":"test", "direction":"vi2tay", "source":"test source", "target":"test target",
            "provenance":{"kind":"synthetic", "origin":"test fixture only", "training_allowed":True, "permission_evidence":"test fixture only"},
            "reviews":[{"reviewer_id":r, "dialect":"fixture", "approved":True} for r in ("one", "two")]}


HOLDOUT = [{"direction":"vi2tay", "text":"held out"}]


def test_eligible_fixture():
    assert check_training([cleared_row()], HOLDOUT)["ready"]


def test_uncleared_and_unreviewed_rejected():
    row = cleared_row(); row["provenance"]["training_allowed"] = False; row["reviews"] = []
    result = check_training([row], HOLDOUT)
    assert not result["ready"] and len(result["errors"]) == 2


def test_holdout_case_and_punctuation_leakage():
    row = cleared_row(); row["source"] = "HELD OUT!"
    assert not check_training([row], HOLDOUT)["ready"]


def test_reverse_direction_leakage():
    row = cleared_row(); row.update(direction="tay2vi", target="held out")
    assert not check_training([row], HOLDOUT)["ready"]


def test_duplicate_sources():
    row = cleared_row(); other = copy.deepcopy(row); other["id"] = "second"
    assert not check_training([row, other], HOLDOUT)["ready"]


def test_same_reviewer_twice_not_independent():
    row = cleared_row(); row["reviews"][1]["reviewer_id"] = "one"
    assert not check_training([row], HOLDOUT)["ready"]


def test_empty_data_is_not_ready():
    assert not check_training([], HOLDOUT)["ready"]
