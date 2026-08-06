from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd

from . import align, lm
from .tay_input_preprocess import preprocess_tay_input

_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"\S+")
_PAREN_RE = re.compile(r"\([^)]*\)")
_GLOSS_SPLIT_RE = re.compile(r"[,;/]")

# Dấu câu bám đầu/cuối token: bỏ khi tra cứu, giữ nguyên khi hiển thị.
_PUNCT = ".,!?;:()[]{}\"'«»…"

_CACHE: dict = {
    "path": None,
    "mtime": None,
    "index": {},   # khóa GIỮ dấu thanh -> list ứng viên đã xếp hạng
    "loose": {},   # khóa BỎ dấu thanh -> list ứng viên (chỉ dùng khi khóa giữ dấu trượt)
    "max_ngram": 1,
}

_COMMON_VIET_FILE = Path(
    os.getenv(
        "COMMON_VIET_LEXICON_PATH",
        str(Path(__file__).resolve().parent / "data" / "common_viet_lexicon.json"),
    )
)
_COMMON_VIET_NORMS: frozenset[str] | None = None
_COMMON_VIET_EXACT: frozenset[str] | None = None
_COMMON_VIET_MTIME: float | None = None


def _norm(text: str) -> str:
    """Chuẩn hóa GIỮ dấu thanh — thanh điệu là âm vị, không được bỏ."""
    return _SPACE_RE.sub(" ", (text or "").strip().lower())


def _norm_loose(text: str) -> str:
    """Chuẩn hóa BỎ dấu thanh — chỉ dùng làm lớp dự phòng khi gõ thiếu dấu."""
    text = _norm(text)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _load_common_viet(force: bool = False) -> tuple[frozenset[str], frozenset[str]]:
    """
    Bảng từ tiếng Việt dùng chung (Hán-Việt / từ mượn).

    Trả về (bản bỏ dấu, bản giữ dấu). Bản bỏ dấu dành cho `preprocess_tay_input`;
    bản giữ dấu dùng cho passthrough để tránh va chạm đồng tự (nặm ≠ năm).
    """
    global _COMMON_VIET_NORMS, _COMMON_VIET_EXACT, _COMMON_VIET_MTIME
    path = _COMMON_VIET_FILE
    if not path.exists():
        _COMMON_VIET_NORMS = frozenset()
        _COMMON_VIET_EXACT = frozenset()
        _COMMON_VIET_MTIME = None
        return _COMMON_VIET_NORMS, _COMMON_VIET_EXACT

    mtime = path.stat().st_mtime
    if not force and _COMMON_VIET_NORMS is not None and _COMMON_VIET_MTIME == mtime:
        return _COMMON_VIET_NORMS, _COMMON_VIET_EXACT  # type: ignore[return-value]

    raw = json.loads(path.read_text(encoding="utf-8"))
    loose: set[str] = set()
    exact: set[str] = set()
    for w in raw:
        if not isinstance(w, str):
            continue
        k = _norm(w)
        if k:
            exact.add(k)
            loose.add(_norm_loose(w))

    _COMMON_VIET_NORMS = frozenset(loose)
    _COMMON_VIET_EXACT = frozenset(exact)
    _COMMON_VIET_MTIME = mtime
    return _COMMON_VIET_NORMS, _COMMON_VIET_EXACT


def _load_common_viet_norms() -> frozenset[str]:
    """Giữ tương thích ngược: bản bỏ dấu dùng cho tiền xử lý."""
    return _load_common_viet()[0]


def _split_definition(definition_raw: str, headword: str) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Tách `definition_raw` thành (danh sách nghĩa Tày, các cặp ví dụ (vi, tay)).

    Định dạng nguồn: "nghĩa1, nghĩa2. Ví dụ Việt: ví dụ Tày. ..."
    Đoạn đầu tiên (trước dấu chấm) CHÍNH LÀ nghĩa mức từ — trước đây bị bỏ đi.
    """
    segs = [s.strip() for s in (definition_raw or "").split(".")]
    if not segs:
        return [], []

    glosses: list[str] = []
    for cand in _GLOSS_SPLIT_RE.split(_PAREN_RE.sub(" ", segs[0])):
        cand = cand.strip().strip("-–—*+ ").strip()
        if cand and ":" not in cand and "~" not in cand and len(cand) <= 40:
            glosses.append(cand)

    examples: list[tuple[str, str]] = []
    for seg in segs[1:]:
        if ":" not in seg:
            continue
        vi, _, tay = seg.partition(":")
        vi = vi.strip().strip("*+ ").replace("~", headword or "").strip()
        tay = tay.strip()
        if vi and tay:
            examples.append((vi, tay))
    return glosses, examples


def _add_candidate(bucket: dict, key: str, vi: str, kind: str, score: float) -> None:
    if not key or not vi:
        return
    lst = bucket.setdefault(key, [])
    for cand in lst:
        if cand["vi"] == vi:
            if score > cand["score"]:
                cand["score"] = score
            return
    lst.append({"vi": vi, "kind": kind, "score": score})


def _ensure_index(excel_path: Path) -> None:
    if not excel_path.exists():
        raise FileNotFoundError(f"Không thấy Excel glossary: {excel_path}")

    mtime = excel_path.stat().st_mtime
    if _CACHE["path"] == str(excel_path) and _CACHE["mtime"] == mtime:
        return

    df = pd.read_excel(excel_path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "headword" not in df.columns or "definition_raw" not in df.columns:
        raise ValueError("Excel phải có cột 'headword' và 'definition_raw'.")

    # Lượt 1: phân tích sẵn và ước lượng độ phổ biến của từ tiếng Việt.
    # Từ điển gốc là Việt->Tày, nên khi lật chiều một nghĩa Tày thường ứng với
    # rất nhiều mục từ Việt (mẻ -> mẹ/vợ/cái/gái...). Tần suất trong chính các
    # câu ví dụ là tín hiệu sẵn có để xếp hạng thay vì chọn bừa.
    parsed: list[tuple[str, list[str], list[tuple[str, str]]]] = []
    vi_freq: dict[str, int] = {}
    for _, row in df.iterrows():
        headword = str(row.get("headword", "") or "").strip()
        definition_raw = str(row.get("definition_raw", "") or "")
        if not headword or not definition_raw:
            continue
        glosses, examples = _split_definition(definition_raw, headword)
        parsed.append((headword, glosses, examples))
        key = _norm(headword)
        vi_freq[key] = vi_freq.get(key, 0) + 2
        for vi, _tay in examples:
            for tok in _TOKEN_RE.findall(_norm(vi).strip(_PUNCT)):
                tok = tok.strip(_PUNCT)
                if tok:
                    vi_freq[tok] = vi_freq.get(tok, 0) + 1

    max_freq = max(vi_freq.values()) if vi_freq else 1
    log_max = math.log1p(max_freq)

    def _freq_bonus(vi: str) -> float:
        """0..2, nén log để từ chức năng siêu phổ biến không nuốt hết nghĩa đúng."""
        f = vi_freq.get(_norm(vi), 0)
        if f <= 0 or log_max <= 0:
            return 0.0
        return 2.0 * math.log1p(f) / log_max

    index: dict[str, list[dict]] = {}
    max_ngram = 1

    for headword, glosses, examples in parsed:
        example_tay = " ".join(_norm(t) for _, t in examples)

        # (1) Nghĩa mức từ: Tày -> từ khóa tiếng Việt của mục từ.
        for pos, gloss in enumerate(glosses):
            key = _norm(gloss)
            if not key:
                continue
            # Nghĩa đầu tiên là nghĩa chính; nghĩa được ví dụ của chính mục từ
            # nhắc lại thì càng chắc chắn (dùng để chọn nghĩa thay vì "ghi trước thắng").
            score = 2.0 if pos == 0 else 1.0
            if key in example_tay:
                score += 1.0
            score += _freq_bonus(headword)
            _add_candidate(index, key, headword, "word", score)
            max_ngram = max(max_ngram, len(_TOKEN_RE.findall(key)))

        # (2) Câu ví dụ song ngữ: khớp cụm dài luôn đáng tin hơn ghép từng từ,
        # nên luôn xếp trên mọi ứng viên mức từ.
        for vi, tay in examples:
            key = _norm(tay)
            if not key:
                continue
            _add_candidate(index, key, vi, "phrase", 20.0)
            max_ngram = max(max_ngram, len(_TOKEN_RE.findall(key)))

    for lst in index.values():
        lst.sort(key=lambda c: (-c["score"], len(c["vi"])))

    loose: dict[str, list[dict]] = {}
    for key, lst in index.items():
        lkey = _norm_loose(key)
        if lkey == key:
            continue
        bucket = loose.setdefault(lkey, [])
        for cand in lst:
            _add_candidate(loose, lkey, cand["vi"], cand["kind"], cand["score"])
    for lst in loose.values():
        lst.sort(key=lambda c: (-c["score"], len(c["vi"])))

    # Gom khóa MỘT TỪ (bản bỏ dấu) theo độ dài để dò gần đúng cho nhanh:
    # chỉ cần so với các khóa lệch tối đa 1 ký tự về độ dài.
    fuzzy: dict[int, list[str]] = {}
    for key in index:
        if " " in key:
            continue
        lkey = _norm_loose(key)
        if len(lkey) >= _FUZZY_MIN_LEN:
            fuzzy.setdefault(len(lkey), []).append(lkey)
    for bucket in fuzzy.values():
        bucket[:] = sorted(set(bucket))

    _CACHE["path"] = str(excel_path)
    _CACHE["mtime"] = mtime
    _CACHE["index"] = index
    _CACHE["loose"] = loose
    _CACHE["fuzzy"] = fuzzy
    _CACHE["max_ngram"] = max_ngram


def _lookup(index: dict, loose: dict, phrase: str) -> tuple[list[dict] | None, str]:
    """Tra khóa giữ dấu trước; chỉ rơi xuống khóa bỏ dấu khi trượt."""
    key = _norm(phrase)
    hit = index.get(key)
    if hit:
        return hit, "dict"
    hit = loose.get(_norm_loose(phrase))
    if hit:
        return hit, "dict-loose"
    return None, ""


_FUZZY_MIN_LEN = 3
FUZZY_ENABLED = os.getenv("FUZZY_MATCH", "1").strip().lower() in ("1", "true", "yes", "on")


def _edit_within(a: str, b: str, max_d: int) -> int | None:
    """Khoảng cách Levenshtein, bỏ sớm khi đã vượt `max_d`."""
    if abs(len(a) - len(b)) > max_d:
        return None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        lo, hi = max(1, i - max_d), min(len(b), i + max_d)
        for j in range(1, len(b) + 1):
            if j < lo or j > hi:
                cur.append(max_d + 1)
                continue
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != b[j - 1])))
        if min(cur) > max_d:
            return None
        prev = cur
    return prev[-1] if prev[-1] <= max_d else None


def _fuzzy_lookup(token: str, loose: dict, fuzzy: dict) -> tuple[list[dict] | None, str]:
    """
    Dò gần đúng cho từ gõ sai / thiếu dấu.

    Người học tiếng Tày gõ sai chính tả là chuyện thường, mà trước đây chỉ lệch
    một ký tự là trượt hoàn toàn. Chỉ chạy khi mọi cách tra khác đã thất bại nên
    không thể làm hỏng kết quả vốn đã đúng.
    """
    probe = _norm_loose(token)
    if len(probe) < _FUZZY_MIN_LEN or not fuzzy:
        return None, ""
    max_d = 1 if len(probe) <= 5 else 2

    best_key, best_d = None, max_d + 1
    for length in range(len(probe) - max_d, len(probe) + max_d + 1):
        for key in fuzzy.get(length, ()):
            d = _edit_within(probe, key, max_d)
            if d is not None and d < best_d:
                best_key, best_d = key, d
                if d == 1:
                    break
        if best_d == 1:
            break

    if best_key is None:
        return None, ""
    hit = loose.get(best_key)
    return (hit, "dict-fuzzy") if hit else (None, "")


# Bằng chứng CÓ MỤC TIÊU (câu ví dụ thật sự chứa từ đang xét) đáng tin hơn hẳn
# bằng chứng gộp chung (từ xuất hiện đâu đó trong 5 câu truy xuất).
# Đo trên 500 câu tách riêng: chỉ dùng bằng chứng gộp chung còn TỆ HƠN không
# dùng ngữ cảnh (chrF 0.3677 so với 0.3691) vì một câu truy xuất có thể đẩy sai
# nghĩa cho từ khác. Toàn bộ phần cải thiện đến từ bằng chứng có mục tiêu.
_CTX_BOOST_TARGETED = 2.5
_CTX_BOOST_POOLED = 0.5


# Câu truy xuất giống 0.83 đáng tin hơn hẳn câu giống 0.30, nên bằng chứng được
# cân theo độ tương đồng thay vì tính ngang nhau.
_SIM_REF = 0.35  # độ tương đồng đạt mức này trở lên được hưởng trọn boost
_SIM_FLOOR = 0.45  # bằng chứng yếu vẫn giữ được phần này của boost


def _prep_context(context_pairs: list[dict] | None) -> list[dict]:
    """Chuẩn hóa sẵn các cặp ví dụ để tra bằng chứng cho từng từ."""
    out = []
    for p in context_pairs or []:
        tay, vi = p.get("tay"), p.get("vi")
        if not tay or not vi:
            continue
        out.append(
            {
                "tay_pad": f" {_norm(tay)} ",
                "score": float(p.get("score") or 0.0),
                "vi_tokens": frozenset(
                    t for t in (x.strip(_PUNCT) for x in _TOKEN_RE.findall(_norm(vi))) if t
                ),
            }
        )
    return out


def _sim_weight(score: float) -> float:
    if score <= 0:
        return _SIM_FLOOR
    frac = min(1.0, score / _SIM_REF)
    return _SIM_FLOOR + (1.0 - _SIM_FLOOR) * frac


def _evidence_for(phrase: str, ctx: list[dict]) -> dict[str, float]:
    """
    Chỉ lấy nghĩa tiếng Việt từ những câu ví dụ THỰC SỰ chứa cụm `phrase`,
    kèm trọng số theo độ tương đồng của câu đó.

    Gộp chung cả 5 câu truy xuất sẽ nhiễu: một câu nói về con gà có thể đẩy sai
    nghĩa cho từ khác trong câu. Ràng buộc theo từng từ thì bằng chứng
    "cáy => gà" chỉ đến từ câu có chứa `cáy`.
    """
    if not ctx:
        return {}
    needle = f" {_norm(phrase)} "
    weights: dict[str, float] = {}
    for p in ctx:
        if needle not in p["tay_pad"]:
            continue
        w = _sim_weight(p["score"])
        for t in p["vi_tokens"]:
            if w > weights.get(t, 0.0):
                weights[t] = w
    return weights


def _pick_candidate(
    cands: list[dict], targeted: dict[str, float], pooled: frozenset[str]
) -> tuple[dict, bool]:
    """
    Chọn nghĩa theo NGỮ CẢNH thay vì luôn lấy nghĩa phổ biến nhất.

    Một từ Tày thường ứng với nhiều từ Việt (mẻ -> mẹ/vợ/cái/gái...). Xếp hạng
    theo tần suất luôn chọn "cái" cho `mẻ`. Câu ví dụ tương tự có chứa chính từ
    đó cho bằng chứng mạnh hơn nhiều.

    Trả về (ứng viên, có_được_ngữ_cảnh_hỗ_trợ).
    """
    if len(cands) < 2 or (not targeted and not pooled):
        return cands[0], False

    best, best_score, boosted = cands[0], None, False
    for c in cands:
        toks = [t for t in (x.strip(_PUNCT) for x in _TOKEN_RE.findall(_norm(c["vi"]))) if t]
        if not toks:
            bonus, hit = 0.0, False
        elif targeted and all(t in targeted for t in toks):
            bonus = _CTX_BOOST_TARGETED * min(targeted[t] for t in toks)
            hit = True
        elif pooled and all(t in pooled for t in toks):
            bonus, hit = _CTX_BOOST_POOLED, True
        else:
            bonus, hit = 0.0, False
        score = c["score"] + bonus
        if best_score is None or score > best_score:
            best, best_score, boosted = c, score, hit
    return best, boosted


_MAX_CANDS = 6
# Mô hình căn chỉnh IBM Model 1 (align.py) MẶC ĐỊNH TẮT — lại là quyết định
# theo số đo. Trên 500 câu tách riêng (mô hình học KHÔNG có câu kiểm tra):
#
#   có ngữ cảnh   : tắt 0.4003 / bật 0.3923   (bật vào thì tệ hơn)
#   không ngữ cảnh: tắt 0.3857 / bật 0.3867   token-F1 0.4863 -> 0.5034
#
# Nghĩa là: xác suất học được THẬT SỰ tốt hơn luật tần suất đặt tay (mẻ->mẹ 0.71
# thay vì chọn nhầm "cái"), nhưng phần cải thiện đó trùng với việc chọn nghĩa
# theo ngữ cảnh truy xuất. Khi đã có ngữ cảnh thì thêm nó vào chỉ gây hại.
ALIGN_ENABLED = os.getenv("ALIGN_MODEL", "0").strip().lower() in ("1", "true", "yes", "on")
_ALIGN_WEIGHT = float(os.getenv("ALIGN_WEIGHT", "0.60"))
LM_DECODE = os.getenv("LM_DECODE", "1").strip().lower() in ("1", "true", "yes", "on")
# Quét trên 500 câu tách riêng (LM dựng KHÔNG có câu đích kiểm tra):
#   có ngữ cảnh : w=0 -> 0.3954 | w=0.10 -> 0.4003 | w=0.35 -> 0.3974 | w=1.0 -> 0.3930
#   không ngữ cảnh: w=0 -> 0.3688 | w=0.35 -> 0.3955
# Khi đã chọn nghĩa theo ngữ cảnh thì LM chỉ cần "đẩy nhẹ"; đè nặng lại làm hỏng
# những cụm vốn đã đúng. Hai tín hiệu này sửa phần lớn cùng một loại lỗi.
_LM_WEIGHT = float(os.getenv("LM_WEIGHT", "0.10"))


def _score_candidates(
    cands: list[dict],
    targeted: dict[str, float],
    pooled: frozenset[str],
    phrase: str = "",
) -> list[dict]:
    """Cộng điểm ngữ cảnh cho MỌI ứng viên (bộ giải mã cần cả danh sách, không chỉ top-1)."""
    use_align = ALIGN_ENABLED and align.is_ready() and phrase
    out: list[dict] = []
    for c in cands[:_MAX_CANDS]:
        toks = [t for t in (x.strip(_PUNCT) for x in _TOKEN_RE.findall(_norm(c["vi"]))) if t]
        if not toks:
            bonus, hit = 0.0, False
        elif targeted and all(t in targeted for t in toks):
            bonus, hit = _CTX_BOOST_TARGETED * min(targeted[t] for t in toks), True
        elif pooled and all(t in pooled for t in toks):
            bonus, hit = _CTX_BOOST_POOLED, True
        else:
            bonus, hit = 0.0, False
        # Xác suất dịch HỌC ĐƯỢC từ kho song ngữ, thay cho luật tần suất đặt tay.
        align_term = _ALIGN_WEIGHT * align.score_pair(phrase, c["vi"]) if use_align else 0.0
        out.append(
            {**c, "adj": c["score"] + bonus + align_term, "by_ctx": hit,
             "by_align": bool(use_align and align_term > -3.0)}
        )
    out.sort(key=lambda x: -x["adj"])
    return out


def _decode_spans(spans: list[dict], excel_path: Path) -> list[dict]:
    """
    Chọn CẢ CHUỖI nghĩa bằng Viterbi, cân giữa điểm từ điển và độ trôi chảy.

    Trước đây mỗi cụm chọn nghĩa độc lập nên từng từ đều hợp lý mà ghép lại thì
    vô nghĩa ("ăn thua khổ cực"). Mô hình bigram tiếng Việt cho biết chuỗi nào
    nghe tự nhiên, nhờ đó các lựa chọn ảnh hưởng lẫn nhau.
    """
    if not spans:
        return []
    fallback = [s["cands"][0] for s in spans]
    if not LM_DECODE or len(spans) < 2:
        return fallback
    try:
        lm.ensure_lm(excel_path)
    except Exception:
        return fallback
    if not lm.is_ready():
        return fallback

    for s in spans:
        for c in s["cands"]:
            toks = lm.tokenize(c["vi"]) or [_norm(c["vi"])]
            c["_toks"] = toks
            c["_last"] = toks[-1]

    def lm_term(toks: list[str], prev: str) -> float:
        # Trung bình theo token để không thiên vị nghĩa ngắn.
        return lm.sequence_logp(toks, prev) / max(1, len(toks))

    dp: list[list[tuple[float, int]]] = []
    for si, s in enumerate(spans):
        cur: list[tuple[float, int]] = []
        for c in s["cands"]:
            if si == 0:
                cur.append((c["adj"] + _LM_WEIGHT * lm_term(c["_toks"], lm.BOS), -1))
                continue
            best_sc, best_prev = None, 0
            for pj, (psc, _bp) in enumerate(dp[si - 1]):
                ptok = spans[si - 1]["cands"][pj]["_last"]
                sc = psc + c["adj"] + _LM_WEIGHT * lm_term(c["_toks"], ptok)
                if best_sc is None or sc > best_sc:
                    best_sc, best_prev = sc, pj
            cur.append((best_sc or 0.0, best_prev))
        dp.append(cur)

    idx = [0] * len(spans)
    idx[-1] = max(range(len(dp[-1])), key=lambda j: dp[-1][j][0])
    for si in range(len(spans) - 1, 0, -1):
        idx[si - 1] = dp[si][idx[si]][1]

    chosen = []
    for si, s in enumerate(spans):
        c = s["cands"][idx[si]]
        # Đánh dấu khi mô hình ngôn ngữ đổi lựa chọn so với xếp hạng từ điển.
        if idx[si] != 0:
            c = {**c, "by_lm": True}
        chosen.append(c)
    return chosen


def translate_with_excel_glossary(
    text: str,
    excel_path: Path,
    max_ngram_cap: int = 14,
    context_pairs: list[dict] | None = None,
) -> dict:
    """
    Dịch Tày -> Việt bằng glossary Excel, khớp cụm dài nhất trước.

    `coverage` chỉ tính các token khớp THẬT trong từ điển. Token chỉ trùng hình thức
    với tiếng Việt được trả về nguyên dạng nhưng đếm riêng (`passthrough_tokens`),
    vì trả lại nguyên từ Tày không phải là dịch được.
    """
    raw = (text or "").strip()
    if not raw:
        return {
            "translation": "",
            "glossary": [],
            "unknown_terms": [],
            "coverage": 0.0,
            "known_tokens": 0,
            "passthrough_tokens": 0,
            "total_tokens": 0,
            "preprocessed_input": "",
        }

    common_loose, common_exact = _load_common_viet()
    clean = preprocess_tay_input(raw, common_loose)

    _ensure_index(excel_path)
    if ALIGN_ENABLED:
        try:
            align.ensure_model(excel_path)
        except Exception:
            pass  # thiếu mô hình căn chỉnh thì vẫn chạy được bằng luật cũ
    index: dict = _CACHE["index"]
    loose: dict = _CACHE["loose"]
    max_ngram = min(max_ngram_cap, int(_CACHE["max_ngram"] or 1))

    words = _TOKEN_RE.findall(clean)
    # Bản đã tỉa dấu câu để tra cứu; bản gốc để hiển thị.
    probes = [w.strip(_PUNCT) or w for w in words]

    # Bằng chứng ngữ cảnh từ các câu ví dụ tương tự -> dùng để chọn nghĩa.
    ctx = _prep_context(context_pairs)
    pooled: frozenset[str] = frozenset()
    for p in ctx:
        pooled |= p["vi_tokens"]
    n_ctx_picks = 0

    # ---- Lượt 1: cắt câu thành cụm và thu ứng viên cho từng cụm ----
    spans: list[dict] = []
    unknown_terms: list[str] = []
    known_tokens = 0
    passthrough_tokens = 0
    i = 0

    while i < len(words):
        found = False
        size_max = min(max_ngram, len(words) - i)
        for size in range(size_max, 0, -1):
            phrase = " ".join(probes[i:i + size])
            cands, source = _lookup(index, loose, phrase)
            if not cands:
                continue
            spans.append(
                {
                    "tay": " ".join(words[i:i + size]),
                    "source": source,
                    "cands": _score_candidates(cands, _evidence_for(phrase, ctx), pooled, phrase),
                }
            )
            known_tokens += size
            i += size
            found = True
            break

        if found:
            continue

        token = words[i]
        probe = probes[i]
        if _norm(probe) in common_exact:
            # Trùng hình thức với một từ Việt dùng chung: giữ nguyên, nhưng KHÔNG
            # tính là đã dịch — đây chính là chỗ trước đây thổi phồng coverage.
            spans.append(
                {
                    "tay": token,
                    "source": "common_viet",
                    "note": "giữ nguyên do trùng hình thức tiếng Việt, chưa tra được nghĩa Tày",
                    "cands": [{"vi": token, "kind": "word", "score": 0.0, "adj": 0.0, "by_ctx": False}],
                }
            )
            passthrough_tokens += 1
            i += 1
            continue

        # Cứu cánh cuối: dò gần đúng. Chỉ chạy khi mọi cách khác đã trượt nên
        # không thể phá kết quả vốn đã đúng — chỉ biến "không biết" thành "đoán".
        if FUZZY_ENABLED:
            fz_cands, fz_source = _fuzzy_lookup(probe, loose, _CACHE.get("fuzzy") or {})
            if fz_cands:
                spans.append(
                    {
                        "tay": token,
                        "source": fz_source,
                        "note": "khớp gần đúng, có thể do gõ sai chính tả",
                        "cands": _score_candidates(fz_cands, _evidence_for(probe, ctx), pooled, probe),
                    }
                )
                known_tokens += 1
                i += 1
                continue

        unknown_terms.append(token)
        spans.append(
            {
                "tay": token,
                "source": "unknown",
                "cands": [
                    {"vi": f"[{token}]", "kind": "unknown", "score": 0.0, "adj": 0.0, "by_ctx": False}
                ],
            }
        )
        i += 1

    # ---- Lượt 2: chọn cả CHUỖI nghĩa, không phải từng cụm rời rạc ----
    chosen = _decode_spans(spans, excel_path)

    # ---- Lượt 3: dựng bản dịch và bảng đối chiếu ----
    translated: list[str] = []
    glossary: list[dict] = []
    for span, cand in zip(spans, chosen):
        translated.append(cand["vi"])
        if cand.get("by_ctx"):
            n_ctx_picks += 1
        src = span["source"]
        if src == "unknown":
            glossary.append(
                {"tay": span["tay"], "vi": "(chưa có trong từ điển)", "source": "unknown"}
            )
            continue
        if src == "dict" and cand.get("kind") == "phrase":
            conf = "high"
        elif src in ("common_viet", "dict-fuzzy"):
            conf = "low"
        else:
            conf = "medium"
        entry = {
            "tay": span["tay"],
            "vi": cand["vi"],
            "source": src,
            "kind": cand.get("kind", "word"),
            "confidence": conf,
        }
        if span.get("note"):
            entry["note"] = span["note"]
        if cand.get("by_ctx"):
            entry["by_context"] = True
        if cand.get("by_lm"):
            entry["by_lm"] = True
        alts = [c["vi"] for c in span["cands"] if c["vi"] != cand["vi"]][:3]
        if alts:
            entry["alternatives"] = alts
        glossary.append(entry)

    total = len(words)
    coverage = round(known_tokens / max(1, total), 3)
    return {
        "translation": " ".join(translated),
        "glossary": glossary,
        "unknown_terms": unknown_terms,
        "coverage": coverage,
        "known_tokens": known_tokens,
        "passthrough_tokens": passthrough_tokens,
        "total_tokens": total,
        "context_picks": n_ctx_picks,
        "preprocessed_input": clean,
    }
