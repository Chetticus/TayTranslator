import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_translators import identity, parse_output, ensure_manifest


def test_missing_exact_is_not_a_translation():
    assert parse_output("taynung", {"exact": [], "suggestions": [{"target": "x"}]}) == ("no_exact", None)


def test_exact():
    assert parse_output("taynung", {"exact": [{"target": "xo tuộng"}]}) == ("ok", "xo tuộng")


def test_local():
    assert parse_output("local", {"reply": "hello"}) == ("ok", "hello")


def test_bad_schema():
    with pytest.raises(ValueError):
        parse_output("taynung", {"exact": [{"unexpected": "x"}]})


def test_identity_is_order_independent_and_content_sensitive():
    assert identity({"id": "a", "text": "b"}) == identity({"text": "b", "id": "a"})
    assert identity({"text": "b"}) != identity({"text": "c"})


def test_manifest_refuses_mixed_versions(tmp_path):
    out = tmp_path / 'results.jsonl'
    ensure_manifest(out, {"engine": "v1"})
    ensure_manifest(out, {"engine": "v1"})
    with pytest.raises(ValueError, match="configuration changed"):
        ensure_manifest(out, {"engine": "v2"})


def test_legacy_output_not_silently_relabelled(tmp_path):
    out = tmp_path / 'legacy.jsonl'
    out.write_text('{}\n', encoding='utf-8')
    with pytest.raises(ValueError, match="Legacy"):
        ensure_manifest(out, {"engine": "v1"})
