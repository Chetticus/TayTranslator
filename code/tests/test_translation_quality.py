"""
Kiểm thử CHẤT LƯỢNG DỊCH, không phải kiểu dữ liệu.

Bộ test cũ chỉ khẳng định hàm trả về `list` — nghĩa là nó vẫn xanh khi hệ thống
không dịch được từ nào. Ở đây kiểm tra bản dịch có ĐÚNG không, độ tin cậy có
trung thực không, và chất lượng tổng thể không tụt so với mức đã đo.

Chạy:  python -m pytest tests/ -v
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import pytest

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

from eval_translation import (  # noqa: E402
    EXCEL_PATH,
    RETRIEVE_K,
    _clean,
    _norm,
    chrf,
    load_example_pairs,
    token_f1,
)
from translation_api import lm  # noqa: E402
from translation_api.excel_glossary import (  # noqa: E402
    _CACHE,
    VI2TAY,
    _ensure_index,
    _norm_loose,
    translate_with_excel_glossary,
)
from translation_api.retriever import corpus_size, retrieve  # noqa: E402

pytestmark = pytest.mark.skipif(
    not EXCEL_PATH.exists(), reason=f"cần từ điển tại {EXCEL_PATH}"
)

# Ngưỡng hồi quy: đặt dưới mức đo được (chrF 0.400 / F1 0.508 trên 500 câu) một
# khoảng an toàn, để dao động do lấy mẫu không làm đỏ test nhưng tụt chất lượng
# thật thì có.
MIN_CHRF = 0.34
MIN_TOKEN_F1 = 0.44
MIN_COVERAGE = 0.95
EVAL_SAMPLE = 150
SEED = 13


# --------------------------------------------------------------------------
# Dịch đúng trên các câu đã biết
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "tay,expected",
    [
        ("kin khẩu", "ăn cơm"),
        ("pây tàng", "đi đường"),
        ("rườn", "nhà"),
        ("nặm", "nước"),
        ("ỏ mẻ mà dá", "a mẹ đã về"),
    ],
)
def test_known_phrases_translate_correctly(tay, expected):
    r = translate_with_excel_glossary(tay, EXCEL_PATH)
    assert _clean(r["translation"]) == _clean(expected), (
        f"{tay!r} -> {r['translation']!r}, mong đợi {expected!r}"
    )


def test_single_words_are_indexed():
    """Lỗi gốc: chỉ mục KHÔNG có mục từ đơn nào, nên không tra nổi một từ lẻ."""
    _ensure_index(EXCEL_PATH)
    single = sum(1 for k in _CACHE["index"] if " " not in k)
    assert single > 2000, f"chỉ có {single} khóa một từ — nghĩa mức từ lại bị bỏ"


def test_tone_marks_are_preserved_in_keys():
    """Thanh điệu là âm vị: `ma` và `mà` không được gộp làm một."""
    _ensure_index(EXCEL_PATH)
    assert any(
        _norm_loose(k) != k for k in _CACHE["index"]
    ), "chỉ mục có vẻ đã bị bỏ dấu thanh"


# --------------------------------------------------------------------------
# Trung thực về độ phủ và độ tin cậy
# --------------------------------------------------------------------------

def test_untranslated_words_do_not_count_as_covered():
    """Từ giữ nguyên vì trùng hình thức tiếng Việt phải đếm riêng, không tính là đã dịch."""
    r = translate_with_excel_glossary("hẹn rặp lại", EXCEL_PATH)
    counted = r["known_tokens"] + r["passthrough_tokens"] + len(r["unknown_terms"])
    assert counted >= r["total_tokens"], "token bị bỏ sót khỏi thống kê"
    assert r["coverage"] <= 1.0


def test_unknown_word_is_reported_not_silently_dropped():
    r = translate_with_excel_glossary("kin khẩu zzzqqq", EXCEL_PATH)
    assert r["total_tokens"] == 3
    assert r["coverage"] < 1.0


@pytest.mark.parametrize(
    "source,protected",
    [
        ("xin chào mình là Nguyễn Hải Nam", "Nguyễn Hải Nam"),
        ("Tôi tên là Trần Minh Anh.", "Trần Minh Anh"),
        ("Hà Nội là thủ đô của Việt Nam.", "Hà Nội"),
        ("Tôi thích AI và Python.", "AI"),
    ],
)
def test_vietnamese_named_entities_are_preserved(source, protected):
    r = translate_with_excel_glossary(source, EXCEL_PATH, direction=VI2TAY)
    assert protected in r["translation"]


@pytest.mark.parametrize(
    "source,literal",
    [
        ("Email của tôi là nam@example.com", "nam@example.com"),
        ("Tôi có 2 con mèo.", "2"),
        ("Hôm nay là 12/10/2026.", "12/10/2026"),
        ("Xin chào 👋", "👋"),
    ],
)
def test_structured_literals_are_preserved_without_unknown_brackets(source, literal):
    r = translate_with_excel_glossary(source, EXCEL_PATH, direction=VI2TAY)
    assert literal in r["translation"]
    assert f"[{literal}]" not in r["translation"]


def test_unknown_capitalized_product_word_is_preserved_at_sentence_start():
    r = translate_with_excel_glossary(
        "Email của tôi là nam@example.com", EXCEL_PATH, direction=VI2TAY
    )
    assert r["translation"].startswith("Email ")
    assert "Email" not in r["unknown_terms"]


def test_named_entity_is_preserved_in_tay_to_vietnamese_text():
    r = translate_with_excel_glossary("Nguyễn Hải Nam kin khẩu", EXCEL_PATH)
    assert r["translation"] == "Nguyễn Hải Nam ăn cơm"


def test_empty_and_whitespace_only_input_is_safe():
    for source in ("", "   ", "\n\t"):
        r = translate_with_excel_glossary(source, EXCEL_PATH)
        assert r["translation"] == ""
        assert r["total_tokens"] == 0


def test_spacing_is_normalized_without_changing_translation():
    r = translate_with_excel_glossary("  kin   khẩu  ", EXCEL_PATH)
    assert r["translation"] == "ăn cơm"


def test_quotes_and_terminal_punctuation_are_preserved():
    r = translate_with_excel_glossary('"kin khẩu!"', EXCEL_PATH)
    assert r["translation"] == '"ăn cơm!"'


def test_translation_preserves_attached_punctuation():
    r = translate_with_excel_glossary("kin khẩu!", EXCEL_PATH)
    assert r["translation"] == "ăn cơm!"


def test_unknown_terms_prevent_high_confidence():
    import main  # noqa: PLC0415

    r = translate_with_excel_glossary("kin khẩu zzzqqq", EXCEL_PATH)
    assert main._build_meta(r)["confidence"] != "high"


def test_undiacriticized_input_is_flagged_low_confidence():
    """
    `khoi pay thieo` khớp CHÍNH XÁC các từ Tày có thật nhưng KHÁC nghĩa, ra kết
    quả sai với coverage 100%. Chỉ phát hiện được ở mức đầu vào.
    """
    import main  # noqa: PLC0415

    base = translate_with_excel_glossary("khoi pay thieo", EXCEL_PATH)
    meta = main._build_meta(base)
    assert meta["no_diacritics"] is True
    assert meta["confidence"] == "low", "câu không dấu không được báo tin cậy cao"


def test_confident_output_is_actually_good():
    import main  # noqa: PLC0415

    base = translate_with_excel_glossary("ỏ mẻ mà dá", EXCEL_PATH)
    meta = main._build_meta(base)
    assert meta["confidence"] == "high"
    assert chrf(base["translation"], "a mẹ đã về") > 0.9


# --------------------------------------------------------------------------
# Truy xuất và mô hình ngôn ngữ
# --------------------------------------------------------------------------

def test_retriever_finds_relevant_examples():
    hits = retrieve("ỏ mẻ mà dá", EXCEL_PATH, k=3, exclude={_norm("ỏ mẻ mà dá")})
    assert hits, "không truy xuất được câu nào"
    assert any("mẹ" in h["vi"].lower() for h in hits), (
        f"không câu nào chứa bằng chứng cho 'mẻ': {[h['vi'] for h in hits]}"
    )


def test_corpus_is_populated():
    assert corpus_size(EXCEL_PATH) > 10000


def test_language_model_prefers_natural_vietnamese():
    lm.build(EXCEL_PATH)
    assert lm.is_ready()
    # "thấy tiền" tự nhiên hơn "nghe tiền" — đây chính là tín hiệu bộ giải mã dùng.
    assert lm.logp("thấy", "tiền") > lm.logp("nghe", "tiền")


def test_alignment_model_learns_sensible_translations():
    """
    IBM Model 1 huấn luyện bằng EM phải học ra nghĩa đúng từ chính kho song ngữ,
    không cần ai gán nhãn từng từ.
    """
    from translation_api import align  # noqa: PLC0415

    align._CACHE["locked"] = False
    align.build(EXCEL_PATH, iterations=6)
    assert align.is_ready()
    assert align.stats()["pairs_trained_on"] > 10000

    for tay, expected in [("cáy", "gà"), ("rườn", "nhà"), ("nặm", "nước"), ("mẻ", "mẹ")]:
        tops = [e for e, _p in align.top_translations(tay, 3)]
        assert expected in tops, f"{tay!r} học ra {tops}, thiếu {expected!r}"


def test_alignment_model_can_exclude_held_out_sentences():
    """Mô hình học từ kho ngữ liệu cũng phải bị chặn khỏi tập kiểm tra."""
    from translation_api import align  # noqa: PLC0415

    pairs = load_example_pairs(EXCEL_PATH)
    held = {(vi or "").strip().lower() for _t, vi in pairs[:200]}
    align._CACHE["locked"] = False
    align.build(EXCEL_PATH, exclude_vi=held, iterations=2, lock=True)
    reduced = align.stats()["pairs_trained_on"]
    align._CACHE["locked"] = False
    align.build(EXCEL_PATH, iterations=2)
    assert align.stats()["pairs_trained_on"] > reduced


def test_lm_can_exclude_held_out_sentences():
    """Nếu LM nhìn thấy câu đích của tập kiểm tra, điểm số sẽ giả tạo."""
    pairs = load_example_pairs(EXCEL_PATH)
    target = pairs[0][1]
    lm.build(EXCEL_PATH, exclude_vi={target.strip().lower()}, lock=True)
    full_tokens = lm.stats()["tokens"]
    lm._CACHE["locked"] = False
    lm.build(EXCEL_PATH)
    assert lm.stats()["tokens"] > full_tokens, "loại trừ câu kiểm tra không có tác dụng"


# --------------------------------------------------------------------------
# Chốt chặn hồi quy trên tập tách riêng
# --------------------------------------------------------------------------

@pytest.mark.slow
def test_confidence_labels_separate_real_quality():
    """
    Nhãn độ tin cậy phải PHÂN BIỆT được chất lượng thật, không chỉ tồn tại.

    Bản hiệu chỉnh đầu tiên chia high/medium theo "có khớp được cụm dài không",
    tương quan với chrF là -0.010 — hai nhóm gần như trùng nhau (0.405 / 0.403).
    Test này giữ cho lỗi đó không quay lại.
    """
    import main  # noqa: PLC0415

    pairs = load_example_pairs(EXCEL_PATH)
    rng = random.Random(SEED)
    rng.shuffle(pairs)
    test = pairs[:EVAL_SAMPLE]

    _ensure_index(EXCEL_PATH)
    index, loose = _CACHE["index"], _CACHE["loose"]
    for tay, _vi in test:
        for bucket, key in ((index, _norm(tay)), (loose, _norm_loose(tay))):
            lst = bucket.get(key)
            if not lst:
                continue
            keep = [c for c in lst if c.get("kind") != "phrase"]
            if keep:
                bucket[key] = keep
            else:
                bucket.pop(key, None)

    lm._CACHE["locked"] = False
    lm.build(EXCEL_PATH, exclude_vi={(vi or "").strip().lower() for _t, vi in test}, lock=True)

    buckets: dict[str, list[float]] = {"high": [], "medium": [], "low": []}
    for tay, vi in test:
        hits = retrieve(tay, EXCEL_PATH, k=RETRIEVE_K + 8, exclude={_norm(tay)})
        ex, gq, gg = [], _clean(tay), _clean(vi)
        for h in hits:
            if _clean(h["vi"]) == gg or (gq and gq in _clean(h["tay"])):
                continue
            ex.append(h)
            if len(ex) >= RETRIEVE_K:
                break
        base = translate_with_excel_glossary(tay, EXCEL_PATH, context_pairs=ex)
        buckets[main._build_meta(base)["confidence"]].append(chrf(base["translation"], vi))

    lm._CACHE["locked"] = False
    _CACHE["path"] = None

    means = {k: (sum(v) / len(v) if v else None) for k, v in buckets.items()}
    print(f"\ncalibration: {[(k, None if m is None else round(m, 3), len(buckets[k])) for k, m in means.items()]}")

    assert buckets["high"] and buckets["low"], "cần có cả nhóm high và low để so sánh"
    assert means["high"] > means["low"] + 0.10, (
        f"nhãn tin cậy không phân biệt được chất lượng: "
        f"high={means['high']:.3f} vs low={means['low']:.3f}"
    )
    if buckets["medium"]:
        assert means["high"] >= means["medium"], "high phải không thấp hơn medium"


@pytest.mark.slow
def test_held_out_quality_does_not_regress():
    """
    Đo lại trên tập KIỂM TRA TÁCH RIÊNG và chặn tụt chất lượng.

    Câu kiểm tra bị gỡ khỏi cả hai lớp chỉ mục, và LM được dựng lại không có câu
    đích — nếu thiếu một trong hai, hệ thống chỉ đang đọc lại thứ nó đã thuộc.
    """
    pairs = load_example_pairs(EXCEL_PATH)
    rng = random.Random(SEED)
    rng.shuffle(pairs)
    test = pairs[:EVAL_SAMPLE]

    _ensure_index(EXCEL_PATH)
    index, loose = _CACHE["index"], _CACHE["loose"]
    for tay, _vi in test:
        for bucket, key in ((index, _norm(tay)), (loose, _norm_loose(tay))):
            lst = bucket.get(key)
            if not lst:
                continue
            keep = [c for c in lst if c.get("kind") != "phrase"]
            if keep:
                bucket[key] = keep
            else:
                bucket.pop(key, None)

    lm._CACHE["locked"] = False
    lm.build(
        EXCEL_PATH,
        exclude_vi={(vi or "").strip().lower() for _t, vi in test},
        lock=True,
    )

    def clean_examples(query, gold, k):
        hits = retrieve(query, EXCEL_PATH, k=k + 8, exclude={_norm(query)})
        out, gq, gg = [], _clean(query), _clean(gold)
        for h in hits:
            if _clean(h["vi"]) == gg or (gq and gq in _clean(h["tay"])):
                continue
            out.append(h)
            if len(out) >= k:
                break
        return out

    total_chrf = total_f1 = total_cov = 0.0
    for tay, vi in test:
        ex = clean_examples(tay, vi, RETRIEVE_K)
        r = translate_with_excel_glossary(tay, EXCEL_PATH, context_pairs=ex)
        total_chrf += chrf(r["translation"], vi)
        total_f1 += token_f1(r["translation"], vi)
        total_cov += r["coverage"]

    n = len(test)
    avg_chrf, avg_f1, avg_cov = total_chrf / n, total_f1 / n, total_cov / n
    print(f"\nheld-out n={n}: chrF={avg_chrf:.4f} tokF1={avg_f1:.4f} cov={avg_cov:.4f}")

    lm._CACHE["locked"] = False
    _CACHE["path"] = None  # buộc dựng lại chỉ mục đầy đủ cho test sau

    assert avg_chrf >= MIN_CHRF, f"chrF tụt xuống {avg_chrf:.4f} (ngưỡng {MIN_CHRF})"
    assert avg_f1 >= MIN_TOKEN_F1, f"token-F1 tụt xuống {avg_f1:.4f}"
    assert avg_cov >= MIN_COVERAGE, f"độ phủ tụt xuống {avg_cov:.4f}"
