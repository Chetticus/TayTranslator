"""
Khai thác cụm từ đa nghĩa-không-tách-được từ căn chỉnh mức từ.

Vấn đề đang chặn chất lượng: `mẻn slua khôm phêt` phải là "Thất bại cay đắng",
nhưng hệ thống ghép từng từ ra "ăn thua khổ cực". Nguyên nhân là `mẻn slua` mang
nghĩa "thất bại" NHƯ MỘT KHỐI — từ điển không có mục từ nào cho cụm đó, và ghép
từng từ thì không bao giờ ra được.

Cách làm ở đây là trích cụm từ từ căn chỉnh từ (phrase extraction, kỹ thuật
chuẩn của dịch máy thống kê):

  1. Dùng IBM Model 1 (align.py) căn chỉnh mỗi từ tiếng Việt về từ Tày khớp nhất
  2. Với mỗi cặp câu, liệt kê các cặp span (Tày, Việt) NHẤT QUÁN với căn chỉnh
     đó — tức không có liên kết nào bắc ra ngoài span
  3. Đếm trên toàn kho; cụm nào lặp lại nhiều lần là cụm thật, không phải ngẫu nhiên

Điểm đáng chú ý: mô hình căn chỉnh đã bị tắt ở khâu chấm điểm nghĩa vì trùng lặp
với ngữ cảnh truy xuất — nhưng chính nó lại là thứ làm được việc này.
"""

from __future__ import annotations

import re
from pathlib import Path

_TOKEN_RE = re.compile(r"[^\s.,!?;:()\[\]\"'«»…]+")

_CACHE: dict = {
    "path": None,
    "mtime": None,
    "phrases": {},   # tay_phrase -> [(vi_phrase, count), ...]
    "reverse": {},   # vi_phrase  -> [(tay_phrase, count), ...]
    "locked": False,
    "n_pairs": 0,
}

MAX_SPAN = 4
MIN_COUNT = 2


def _tokens(text: str) -> list[str]:
    return [t for t in (x.strip("-–—") for x in _TOKEN_RE.findall((text or "").lower())) if t]


def _align_sentence(f_toks: list[str], e_toks: list[str]) -> list[int | None]:
    """
    Với mỗi từ tiếng Việt, chọn từ Tày có P(việt|tày) cao nhất trong câu.

    Đây là căn chỉnh Viterbi của IBM Model 1: đơn giản, nhiều-về-một, nhưng đủ
    tốt để trích cụm.
    """
    from . import align  # tránh vòng import

    out: list[int | None] = []
    for e in e_toks:
        best_i, best_p = None, 0.0
        for i, f in enumerate(f_toks):
            p = align.prob(f, e)
            if p > best_p:
                best_i, best_p = i, p
        out.append(best_i if best_p > 0.0 else None)
    return out


def _extract(f_toks: list[str], e_toks: list[str], a: list[int | None]):
    """
    Liệt kê các cặp span nhất quán với căn chỉnh.

    Một cặp (span Tày, span Việt) là hợp lệ khi mọi từ Việt trong span Việt hoặc
    chưa được căn chỉnh, hoặc trỏ vào đúng span Tày — và span Tày phải được ít
    nhất một từ Việt trong span đó trỏ tới.
    """
    n_f, n_e = len(f_toks), len(e_toks)
    for j1 in range(n_e):
        for j2 in range(j1, min(n_e, j1 + MAX_SPAN)):
            linked = [a[j] for j in range(j1, j2 + 1) if a[j] is not None]
            if not linked:
                continue
            i_lo, i_hi = min(linked), max(linked)
            if i_hi - i_lo + 1 > MAX_SPAN:
                continue
            # Không từ Việt nào NGOÀI span được trỏ vào trong [i_lo, i_hi]
            leaks = any(
                a[j] is not None and i_lo <= a[j] <= i_hi
                for j in range(n_e)
                if j < j1 or j > j2
            )
            if leaks:
                continue
            yield (" ".join(f_toks[i_lo : i_hi + 1]), " ".join(e_toks[j1 : j2 + 1]))


def build(
    excel_path: Path,
    exclude_vi: set[str] | None = None,
    lock: bool = False,
    min_count: int = MIN_COUNT,
) -> None:
    """
    Trích bảng cụm từ. `exclude_vi` phải được truyền khi đánh giá — bảng này học
    từ chính kho ngữ liệu, nên cũng rò rỉ đáp án như LM và mô hình căn chỉnh.
    """
    excel_path = Path(excel_path)
    from . import align  # noqa: PLC0415
    from .retriever import _iter_example_pairs  # noqa: PLC0415

    drop = exclude_vi or set()
    if not align.is_ready():
        align.build(excel_path, exclude_vi=drop)

    counts: dict[tuple[str, str], int] = {}
    n_pairs = 0
    seen: set[tuple[str, str]] = set()
    for tay, vi in _iter_example_pairs(excel_path):
        key = ((tay or "").strip().lower(), (vi or "").strip().lower())
        if not key[0] or not key[1] or key in seen or key[1] in drop:
            continue
        seen.add(key)
        f_toks, e_toks = _tokens(tay), _tokens(vi)
        if not f_toks or not e_toks:
            continue
        n_pairs += 1
        a = _align_sentence(f_toks, e_toks)
        for f_phrase, e_phrase in _extract(f_toks, e_toks, a):
            # Chỉ giữ cụm THẬT SỰ đa từ ở phía Tày — cụm một từ đã có trong từ điển.
            if " " not in f_phrase:
                continue
            counts[(f_phrase, e_phrase)] = counts.get((f_phrase, e_phrase), 0) + 1

    phrases: dict[str, list[tuple[str, int]]] = {}
    reverse: dict[str, list[tuple[str, int]]] = {}
    for (f, e), c in counts.items():
        if c < min_count:
            continue
        phrases.setdefault(f, []).append((e, c))
        if " " in e:  # chiều Việt->Tày cũng chỉ giữ cụm đa từ
            reverse.setdefault(e, []).append((f, c))
    for table in (phrases, reverse):
        for k in table:
            table[k].sort(key=lambda x: -x[1])
            del table[k][4:]

    _CACHE.update(
        path=str(excel_path), mtime=excel_path.stat().st_mtime,
        phrases=phrases, reverse=reverse, locked=lock, n_pairs=n_pairs,
    )


def ensure_phrases(excel_path: Path) -> None:
    excel_path = Path(excel_path)
    if _CACHE["locked"]:
        return
    mtime = excel_path.stat().st_mtime
    if _CACHE["path"] == str(excel_path) and _CACHE["mtime"] == mtime:
        return
    build(excel_path)


def lookup(tay_phrase: str) -> list[tuple[str, int]]:
    return _CACHE["phrases"].get((tay_phrase or "").lower(), [])


def lookup_reverse(vi_phrase: str) -> list[tuple[str, int]]:
    """Cùng bảng cụm, tra theo chiều Việt -> Tày."""
    return _CACHE["reverse"].get((vi_phrase or "").lower(), [])


def all_phrases() -> dict[str, list[tuple[str, int]]]:
    return _CACHE["phrases"]


def is_ready() -> bool:
    return bool(_CACHE["phrases"])


def stats() -> dict:
    ph = _CACHE["phrases"]
    return {
        "sentence_pairs": _CACHE["n_pairs"],
        "tay_phrases": len(ph),
        "phrase_pairs": sum(len(v) for v in ph.values()),
    }
