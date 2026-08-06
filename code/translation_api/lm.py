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

VI = "vi"
TAY = "tay"


def _blank() -> dict:
    return {
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


# Một LM cho mỗi phía: dịch sang tiếng Việt cần LM tiếng Việt, dịch sang tiếng
# Tày cần LM tiếng Tày.
_CACHES: dict[str, dict] = {VI: _blank(), TAY: _blank()}
_CACHE: dict = _CACHES[VI]  # bí danh cho phía mặc định (sửa tại chỗ, không gán lại)

# Trọng số nội suy: P(w2|w1) = LAMBDA*P_bigram + (1-LAMBDA)*P_unigram
_LAMBDA = 0.75


def tokenize(text: str) -> list[str]:
    return [t for t in (x.strip("-–—") for x in _TOKEN_RE.findall((text or "").lower())) if t]


def build(
    excel_path: Path,
    exclude_vi: set[str] | None = None,
    lock: bool = False,
    side: str = VI,
) -> None:
    """
    Dựng LM bigram từ một phía của kho ví dụ.

    `exclude_vi`: tập câu tiếng Việt (đã chuẩn hóa lower/strip) phải BỎ QUA — loại
    theo phía Việt ở cả hai chiều, vì đó là thứ định danh một cặp bị giữ lại.
    Bắt buộc dùng khi đánh giá: nếu LM nhìn thấy câu đích của tập kiểm tra, nó sẽ
    tái tạo lại đúng câu đó và điểm số tăng vọt một cách giả tạo.
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

    for tay, vi in _iter_example_pairs(excel_path):
        vi_key = (vi or "").strip().lower()
        if not vi_key or vi_key in drop:
            continue
        text = tay if side == TAY else vi
        key = (text or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        toks = [BOS] + tokenize(text) + [EOS]
        if len(toks) <= 2:
            continue
        for t in toks:
            uni[t] = uni.get(t, 0) + 1
            total += 1
        for a, b in zip(toks, toks[1:]):
            bi[(a, b)] = bi.get((a, b), 0) + 1

    _CACHES[side].update(
        path=str(excel_path), mtime=excel_path.stat().st_mtime, uni=uni, bi=bi,
        total=max(1, total), vocab=max(1, len(uni)), locked=lock,
    )


def ensure_lm(excel_path: Path, side: str = VI) -> None:
    excel_path = Path(excel_path)
    cache = _CACHES[side]
    if cache["locked"]:
        return
    if not excel_path.exists():
        raise FileNotFoundError(f"Không thấy Excel glossary: {excel_path}")
    mtime = excel_path.stat().st_mtime
    if cache["path"] == str(excel_path) and cache["mtime"] == mtime:
        return
    build(excel_path, side=side)


def logp(prev: str, cur: str, side: str = VI) -> float:
    """log P(cur | prev), nội suy bigram với unigram, có làm mượt add-1."""
    cache = _CACHES[side]
    uni, bi = cache["uni"], cache["bi"]
    total, vocab = cache["total"], cache["vocab"]

    p_uni = (uni.get(cur, 0) + 1.0) / (total + vocab)
    prev_count = uni.get(prev, 0)
    if prev_count > 0:
        p_bi = bi.get((prev, cur), 0) / prev_count
        p = _LAMBDA * p_bi + (1.0 - _LAMBDA) * p_uni
    else:
        p = p_uni
    return math.log(max(p, 1e-12))


def sequence_logp(tokens: list[str], prev: str = BOS, side: str = VI) -> float:
    """Điểm trôi chảy của một chuỗi token, nối tiếp sau `prev`."""
    if not tokens:
        return 0.0
    s = 0.0
    p = prev
    for t in tokens:
        s += logp(p, t, side)
        p = t
    return s


def is_ready(side: str = VI) -> bool:
    return bool(_CACHES[side]["uni"])


def stats(side: str = VI) -> dict:
    cache = _CACHES[side]
    return {
        "unigrams": len(cache["uni"]),
        "bigrams": len(cache["bi"]),
        "tokens": cache["total"],
    }
