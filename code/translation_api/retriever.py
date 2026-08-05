"""
Truy xuất câu ví dụ song ngữ tương tự (phần "R" thật sự của RAG).

Bối cảnh: `rag.py::fetch_examples` lấy 5 câu NGẪU NHIÊN và thậm chí không nhận
câu người dùng làm tham số, lại đọc `corpus.db` đang rỗng — nên chưa từng có
truy xuất nào xảy ra. Trong khi đó chính từ điển Excel đã chứa hơn 14.000 cặp
câu Tày–Việt chưa được dùng tới.

Module này lập chỉ mục các cặp đó và trả về những câu GIỐNG câu đang dịch, để
đưa vào prompt làm ví dụ few-shot. Đây là tín hiệu ngữ cảnh mà bảng tần suất
không thể có: thấy `mẻ` trong câu tương tự sẽ biết nên chọn "mẹ" hay "cái".

Không dùng thư viện ngoài: chỉ số nghịch đảo + trọng số IDF trên token, cộng
điểm phụ theo 3-gram ký tự để chịu được sai khác chính tả/dấu.
"""

from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path

import pandas as pd

_TOKEN_RE = re.compile(r"[^\s.,!?;:()\[\]\"'«»…]+")

_CACHE: dict = {
    "path": None,
    "mtime": None,
    "pairs": [],       # list[(tay, vi)]
    "postings": {},    # token -> list[doc_id]
    "idf": {},         # token -> idf
    "doc_tokens": [],  # list[set[str]]
    "doc_grams": [],   # list[set[str]]
    "norm_tay": [],    # list[str] khóa chuẩn hóa để loại trừ khi đánh giá
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _strip_tone(text: str) -> str:
    t = unicodedata.normalize("NFKD", _norm(text))
    return "".join(c for c in t if not unicodedata.combining(c))


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(_norm(text))


def _grams(text: str, n: int = 3) -> set[str]:
    """3-gram ký tự trên bản bỏ dấu — bắt được biến thể chính tả gần giống."""
    s = " " + re.sub(r"\s+", " ", _strip_tone(text)) + " "
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def _iter_example_pairs(excel_path: Path):
    """Bóc các cặp (Tày, Việt) từ cột definition_raw của từ điển."""
    from .excel_glossary import _split_definition  # tránh vòng import

    df = pd.read_excel(excel_path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    for _, row in df.iterrows():
        head = str(row.get("headword", "") or "").strip()
        raw = str(row.get("definition_raw", "") or "")
        if not head or not raw:
            continue
        _glosses, examples = _split_definition(raw, head)
        for vi, tay in examples:
            if tay and vi:
                yield tay.strip(), vi.strip()


def ensure_index(excel_path: Path) -> None:
    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise FileNotFoundError(f"Không thấy Excel glossary: {excel_path}")

    mtime = excel_path.stat().st_mtime
    if _CACHE["path"] == str(excel_path) and _CACHE["mtime"] == mtime:
        return

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for tay, vi in _iter_example_pairs(excel_path):
        key = (_norm(tay), _norm(vi))
        if key in seen:
            continue
        seen.add(key)
        pairs.append((tay, vi))

    postings: dict[str, list[int]] = {}
    doc_tokens: list[set[str]] = []
    doc_grams: list[set[str]] = []
    norm_tay: list[str] = []

    for i, (tay, _vi) in enumerate(pairs):
        toks = set(_tokens(tay))
        doc_tokens.append(toks)
        doc_grams.append(_grams(tay))
        norm_tay.append(_norm(tay))
        for t in toks:
            postings.setdefault(t, []).append(i)

    n_docs = max(1, len(pairs))
    idf = {t: math.log(1.0 + n_docs / (1.0 + len(ids))) for t, ids in postings.items()}

    _CACHE.update(
        path=str(excel_path), mtime=mtime, pairs=pairs, postings=postings,
        idf=idf, doc_tokens=doc_tokens, doc_grams=doc_grams, norm_tay=norm_tay,
    )


def retrieve(
    query: str,
    excel_path: Path,
    k: int = 5,
    exclude: set[str] | None = None,
    min_score: float = 0.12,
) -> list[dict]:
    """
    Trả về tối đa `k` cặp câu ví dụ giống `query` nhất.

    `exclude`: tập khóa `_norm(tay)` cần bỏ qua — dùng khi đánh giá để không
    truy xuất trúng chính câu đang được chấm điểm (nếu không, điểm sẽ ảo).
    """
    ensure_index(excel_path)
    pairs = _CACHE["pairs"]
    if not pairs:
        return []

    q_tokens = set(_tokens(query))
    if not q_tokens:
        return []
    q_grams = _grams(query)
    idf = _CACHE["idf"]
    postings = _CACHE["postings"]
    doc_tokens = _CACHE["doc_tokens"]
    doc_grams = _CACHE["doc_grams"]
    norm_tay = _CACHE["norm_tay"]
    excl = exclude or set()

    # Chỉ chấm điểm các câu có chung ít nhất một token -> nhanh hơn quét toàn bộ.
    cand: dict[int, float] = {}
    for t in q_tokens:
        w = idf.get(t)
        if w is None:
            continue
        for doc in postings[t]:
            cand[doc] = cand.get(doc, 0.0) + w
    if not cand:
        return []

    q_idf_total = sum(idf.get(t, 0.0) for t in q_tokens) or 1.0

    scored: list[tuple[float, int]] = []
    for doc, overlap in cand.items():
        if norm_tay[doc] in excl:
            continue
        # Bao phủ token có trọng số IDF, phạt nhẹ câu dài để tránh câu dài
        # nào cũng khớp; cộng thêm độ giống 3-gram ký tự.
        cover = overlap / q_idf_total
        dt = doc_tokens[doc]
        length_pen = len(q_tokens) / max(len(q_tokens), len(dt))
        dg = doc_grams[doc]
        gram_sim = len(q_grams & dg) / max(1, len(q_grams | dg))
        score = 0.7 * cover * length_pen + 0.3 * gram_sim
        if score >= min_score:
            scored.append((score, doc))

    scored.sort(key=lambda x: (-x[0], x[1]))
    out = []
    for score, doc in scored[:k]:
        tay, vi = pairs[doc]
        out.append({"tay": tay, "vi": vi, "score": round(score, 4)})
    return out


def corpus_size(excel_path: Path) -> int:
    ensure_index(excel_path)
    return len(_CACHE["pairs"])
