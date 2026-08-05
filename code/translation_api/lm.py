"""
Mô hình ngôn ngữ bigram cho phía tiếng Việt.

Vấn đề nó giải: lớp tra từ điển chọn nghĩa cho TỪNG cụm một cách độc lập, nên
mỗi từ đều hợp lý mà ghép lại thì vô nghĩa — `mẻn slua khôm phêt` ra "ăn thua
khổ cực". Không có tín hiệu nào cho biết chuỗi tiếng Việt tạo ra có tự nhiên hay
không.

Ở đây đếm thống kê bigram từ chính 14.179 câu ví dụ tiếng Việt sẵn có (ước lượng
hợp lý cực đại, làm mượt kiểu interpolation với unigram). Bộ giải mã Viterbi
trong `excel_glossary` dùng điểm này để chọn cả CHUỖI nghĩa thay vì từng từ rời
rạc: mô hình biết "thấy tiền" tự nhiên hơn "nghe tiền" nên kéo `hăn` về "thấy".

Đây là học từ dữ liệu (đếm xác suất trên kho ngữ liệu), không phải hằng số đặt
tay — nền tảng của dịch máy thống kê trước thời neural.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

_TOKEN_RE = re.compile(r"[^\s.,!?;:()\[\]\"'«»…]+")

BOS = "<s>"
EOS = "</s>"

_CACHE: dict = {
    "path": None,
    "mtime": None,
    "uni": {},
    "bi": {},
    "total": 0,
    "vocab": 0,
    # Khi đánh giá, LM phải được dựng KHÔNG có các câu kiểm tra, nếu không nó
    # thuộc lòng đáp án và điểm số thành vô nghĩa. `locked` giữ cho bản LM đã
    # loại trừ đó không bị dựng lại bằng toàn bộ dữ liệu.
    "locked": False,
}

# Trọng số nội suy: P(w2|w1) = LAMBDA*P_bigram + (1-LAMBDA)*P_unigram
_LAMBDA = 0.75


def tokenize(text: str) -> list[str]:
    return [t for t in (x.strip("-–—") for x in _TOKEN_RE.findall((text or "").lower())) if t]


def build(excel_path: Path, exclude_vi: set[str] | None = None, lock: bool = False) -> None:
    """
    Dựng LM bigram từ phía tiếng Việt của kho ví dụ.

    `exclude_vi`: tập câu tiếng Việt (đã chuẩn hóa lower/strip) phải BỎ QUA.
    Bắt buộc dùng khi đánh giá — nếu để LM nhìn thấy câu đích của tập kiểm tra,
    nó sẽ tái tạo lại đúng câu đó và điểm số tăng vọt một cách giả tạo.
    """
    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise FileNotFoundError(f"Không thấy Excel glossary: {excel_path}")

    from .retriever import _iter_example_pairs  # tránh vòng import

    drop = exclude_vi or set()
    uni: dict[str, int] = {}
    bi: dict[tuple[str, str], int] = {}
    total = 0
    seen: set[str] = set()

    for _tay, vi in _iter_example_pairs(excel_path):
        key = (vi or "").strip().lower()
        if not key or key in seen or key in drop:
            continue
        seen.add(key)
        toks = [BOS] + tokenize(vi) + [EOS]
        if len(toks) <= 2:
            continue
        for t in toks:
            uni[t] = uni.get(t, 0) + 1
            total += 1
        for a, b in zip(toks, toks[1:]):
            bi[(a, b)] = bi.get((a, b), 0) + 1

    _CACHE.update(
        path=str(excel_path), mtime=excel_path.stat().st_mtime, uni=uni, bi=bi,
        total=max(1, total), vocab=max(1, len(uni)), locked=lock,
    )


def ensure_lm(excel_path: Path) -> None:
    excel_path = Path(excel_path)
    if _CACHE["locked"]:
        return
    if not excel_path.exists():
        raise FileNotFoundError(f"Không thấy Excel glossary: {excel_path}")
    mtime = excel_path.stat().st_mtime
    if _CACHE["path"] == str(excel_path) and _CACHE["mtime"] == mtime:
        return
    build(excel_path)


def logp(prev: str, cur: str) -> float:
    """log P(cur | prev), nội suy bigram với unigram, có làm mượt add-1."""
    uni, bi = _CACHE["uni"], _CACHE["bi"]
    total, vocab = _CACHE["total"], _CACHE["vocab"]

    p_uni = (uni.get(cur, 0) + 1.0) / (total + vocab)
    prev_count = uni.get(prev, 0)
    if prev_count > 0:
        p_bi = bi.get((prev, cur), 0) / prev_count
        p = _LAMBDA * p_bi + (1.0 - _LAMBDA) * p_uni
    else:
        p = p_uni
    return math.log(max(p, 1e-12))


def sequence_logp(tokens: list[str], prev: str = BOS) -> float:
    """Điểm trôi chảy của một chuỗi token, nối tiếp sau `prev`."""
    if not tokens:
        return 0.0
    s = 0.0
    p = prev
    for t in tokens:
        s += logp(p, t)
        p = t
    return s


def is_ready() -> bool:
    return bool(_CACHE["uni"])


def stats() -> dict:
    return {
        "unigrams": len(_CACHE["uni"]),
        "bigrams": len(_CACHE["bi"]),
        "tokens": _CACHE["total"],
    }
