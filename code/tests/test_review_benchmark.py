import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_benchmark import export_page, summarize


@pytest.fixture
def study():
    score = {"output": "example", "status": "ok", "meaning_1_to_5": None,
             "fluency_1_to_5": None, "critical_error": None, "notes": ""}
    row = {"case_hash": "one", "case": {"id": "one", "category": "basic", "text": "hello"},
           "reviewer": "", "dialect": "", "reference_translation": "",
           "A": copy.deepcopy(score), "B": copy.deepcopy(score)}
    return [row], [{"case_hash": "one", "A": "local", "B": "taynung"}]


def rated(row, reviewer="r1", meaning=5):
    result = copy.deepcopy(row)
    result.update(reviewer=reviewer, dialect="test dialect")
    result["A"].update(meaning_1_to_5=meaning, fluency_1_to_5=4, critical_error=False)
    result["B"].update(meaning_1_to_5=3, fluency_1_to_5=3, critical_error=True)
    return result


def test_empty_scores_do_not_become_zero(study):
    template, key = study
    result = summarize(template, key, [])
    assert result["engines"]["local"]["quality"]["meaning_1_to_5"] == {"n": 0, "mean": None}
    assert result["engines"]["local"]["coverage"]["outputs_available"] == 1


def test_aggregation_and_disagreement(study):
    template, key = study
    result = summarize(template, key, [rated(template[0]), rated(template[0], "r2", 1)])
    assert result["reviewers"] == 2
    assert result["engines"]["local"]["quality"]["meaning_1_to_5"]["mean"] == 3
    assert result["paired_quality"]["meaning_1_to_5"]["matched_case_reviewer_pairs"] == 2
    assert result["disagreements"][0]["reasons"] == ["meaning_1_to_5"]


def test_duplicate_submission_rejected(study):
    template, key = study
    row = rated(template[0])
    with pytest.raises(ValueError, match="Duplicate review"):
        summarize(template, key, [row, row])


@pytest.mark.parametrize("value", [0, 6, True, "5", 2.5])
def test_invalid_ratings_rejected(study, value):
    template, key = study
    row = rated(template[0]); row["A"]["meaning_1_to_5"] = value
    with pytest.raises(ValueError, match="Invalid"):
        summarize(template, key, [row])


def test_tampered_output_rejected(study):
    template, key = study
    row = rated(template[0]); row["A"]["output"] = "changed"
    with pytest.raises(ValueError, match="Output/status"):
        summarize(template, key, [row])


def test_missing_output_cannot_be_scored(study):
    template, key = study
    template[0]["A"].update(output=None, status="no_exact")
    with pytest.raises(ValueError, match="Missing outputs"):
        summarize(template, key, [rated(template[0])])


def test_page_escapes_script_and_removes_ratings(tmp_path, study):
    template, _ = study
    row = rated(template[0]); row["A"]["output"] = '</script><script>alert(1)</script>'
    source, output = tmp_path / "input.jsonl", tmp_path / "index.html"
    source.write_text(json.dumps(row), encoding="utf-8")
    export_page(source, output)
    page = output.read_text(encoding="utf-8")
    assert '</script><script>alert(1)</script>' not in page
    assert '"reviewer": ""' in page
    assert '"meaning_1_to_5": null' in page
    with pytest.raises(FileExistsError):
        export_page(source, output)
