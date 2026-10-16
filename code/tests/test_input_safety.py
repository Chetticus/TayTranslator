"""Mechanical invariants, not claims of linguistic correctness. No dictionary required."""
import sys
import unicodedata
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from translation_api import excel_glossary as g


@pytest.fixture
def translator(monkeypatch):
    entries = {"xin chào": "greeting", "xin": "ask", "chào": "hello", "tôi": "I",
               "mình": "I", "là": "am", "tên": "name", "kin khẩu": "ăn cơm",
               "kin": "ăn", "khẩu": "cơm", "nam": "south", "hải": "sea",
               "nguyễn": "wrong", "kin nam": "MUST NOT CONSUME NAME"}
    index = {k: [{"vi": v, "kind": "phrase" if ' ' in k else "word", "score": 20}] for k, v in entries.items()}
    cache = {"index": index, "loose": {}, "fuzzy": {}, "max_ngram": 14}
    monkeypatch.setattr(g, "_CACHES", {g.TAY2VI: cache, g.VI2TAY: cache})
    monkeypatch.setattr(g, "_ensure_index", lambda *args: None)
    monkeypatch.setattr(g, "_load_common_viet", lambda: (frozenset(), frozenset()))
    monkeypatch.setattr(g, "PHRASES_ENABLED", False)
    monkeypatch.setattr(g, "ALIGN_ENABLED", False)
    monkeypatch.setattr(g, "FUZZY_ENABLED", False)
    monkeypatch.setattr(g, "LM_DECODE", False)
    return lambda text, **kw: g.translate_with_excel_glossary(text, Path("unused"), **kw)


@pytest.mark.parametrize("literal", ["!!!", "…", "👋", "https://example.com/~name?a=1", "nam@example.com", "12/10/2026", "-3.5", "(AI)"])
def test_literals_exactly_once(translator, literal):
    result = translator(literal)
    assert result["translation"] == literal
    assert result["known_tokens"] == 0
    assert result["coverage"] == 0


@pytest.mark.parametrize("name", ["nguyễn hải nam", "Nguyễn Hải Nam", "nguyen hai nam"])
def test_introduction_name_preserved(translator, name):
    result = translator("xin chào mình là " + name, direction=g.VI2TAY)
    assert result["translation"].endswith(name)


def test_normal_introduction_is_not_name(translator):
    result = translator("tôi là sinh viên", direction=g.VI2TAY)
    assert not any(x["source"] == "named_entity" for x in result["glossary"])


def test_name_boundary_stops_at_conjunction(translator):
    result = translator("tôi tên là nguyễn hải nam và tôi", direction=g.VI2TAY)
    names = [x["tay"] for x in result["glossary"] if x["source"] == "named_entity"]
    assert names == ["nguyễn hải nam"]


def test_phrase_cannot_consume_protected_span(translator):
    assert translator("kin Nam")['translation'] == 'ăn Nam'


def test_explicit_keep_phrase(translator):
    result = translator("kin nam", protected_terms=["nam"])
    assert result["translation"] == "ăn nam"


@pytest.mark.parametrize("text,expected", [('“kin khẩu!”', '“ăn cơm!”'), ('kin, khẩu!', 'ăn, cơm!'), ('Xin Chào', 'greeting'), ('XIN CHÀO', 'greeting')])
def test_punctuation_and_case(translator, text, expected):
    assert translator(text, direction=g.VI2TAY)["translation"] == expected


def test_unicode_canonical_equivalence(translator):
    assert translator(unicodedata.normalize('NFD', 'kin khẩu'))['translation'] == 'ăn cơm'


def test_tokens_are_accounted_for(translator):
    result = translator("kin Nam 42 zzzzzz")
    assert result['known_tokens'] + result['passthrough_tokens'] + len(result['unknown_terms']) == result['total_tokens']


@pytest.mark.parametrize("payload", [{"message":" "}, {"message":"x" * 2001}, {"message":"a " * 201}, {"message":"a\x00b"}, {"message":"hello", "direction":"unsupported"}, {"message":"hello", "protected_terms":["x"] * 21}])
def test_invalid_api_requests_rejected(payload):
    with pytest.raises(ValidationError):
        main.ChatIn(**payload)


def test_unknown_logging_default_off(monkeypatch, tmp_path):
    path = tmp_path / "unknown.jsonl"
    monkeypatch.setattr(main, "LOG_UNKNOWN_TERMS", False)
    monkeypatch.setattr(main, "UNKNOWN_LOG_PATH", path)
    main._append_unknown_terms_log("private input", ["private"], {})
    assert not path.exists()


def test_reverse_never_uses_forward_llm(monkeypatch):
    monkeypatch.setattr(main, "USE_LLM", True)
    monkeypatch.setattr(main, "LOG_UNKNOWN_TERMS", False)
    monkeypatch.setattr(main, "translate_with_excel_glossary", lambda *a, **k: {"translation":"result", "coverage":1, "total_tokens":1, "known_tokens":1})
    monkeypatch.setattr(main, "translate_tay_to_vi_ollama_with_glossary", lambda *a, **k: pytest.fail("wrong direction LLM"))
    result = main.translate(main.ChatIn(message="test", direction="vi2tay"))
    assert result["reply"] == "result"
    assert result["meta"]["direction"] == "vi2tay"
