"""
Học xác suất dịch mức từ từ dữ liệu (IBM Model 1, huấn luyện bằng EM).

Vì sao cần: mọi điểm số chọn nghĩa cho tới giờ đều do người đặt tay — trọng số
tần suất, mức thưởng ngữ cảnh, ngưỡng. Chúng được dò bằng cách quét tham số rồi
đọc bảng kết quả, tức là tối ưu thủ công, không phải học.

Ở đây ước lượng P(từ_việt | từ_tày) trực tiếp từ 14.179 cặp câu song ngữ. Bài
toán: biết CÂU nào ứng với câu nào, nhưng không biết TỪ nào ứng với từ nào.
Thuật toán EM giải bằng cách lặp:

  E-bước: với tham số hiện tại, tính kỳ vọng mỗi cặp từ khớp nhau bao nhiêu
  M-bước: chuẩn hóa các kỳ vọng đó thành bộ tham số mới

Khởi tạo đều rồi lặp; những cặp từ hay cùng xuất hiện sẽ dần chiếm xác suất.
Đây là dịch máy thống kê cổ điển, nền tảng trước thời neural — chạy trên CPU
trong vài giây và không cần thư viện ngoài.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

_TOKEN_RE = re.compile(r"[^\s.,!?;:()\[\]\"'«»…]+")

_CACHE: dict = {
    "path": None,
    "mtime": None,
    "t": {},        # (tay, vi) -> P(vi | tay)
    "best": {},     # tay -> [(vi, p), ...] đã xếp hạng
    "locked": False,
    "iters": 0,
    "pairs": 0,
}

NULL = "<null>"


def _tokens(text: str) -> list[str]:
    return [t for t in (x.strip("-–—") for x in _TOKEN_RE.findall((text or "").lower())) if t]


def build(
    excel_path: Path,
    exclude_vi: set[str] | None = None,
    iterations: int = 6,
    lock: bool = False,
    min_prob: float = 1e-3,
) -> None:
    """
    Huấn luyện IBM Model 1 bằng EM.

    `exclude_vi` bắt buộc phải dùng khi đánh giá: nếu mô hình được học trên chính
    câu đích của tập kiểm tra thì điểm số sẽ giả — đúng như bài học từ mô hình
    ngôn ngữ và từ tập kiểm tra ban đầu.
    """
    excel_path = Path(excel_path)
    from .retriever import _iter_example_pairs  # tránh vòng import

    drop = exclude_vi or set()
    corpus: list[tuple[list[str], list[str]]] = []
    seen: set[tuple[str, str]] = set()
    for tay, vi in _iter_example_pairs(excel_path):
        key = ((tay or "").strip().lower(), (vi or "").strip().lower())
        if not key[0] or not key[1] or key in seen or key[1] in drop:
            continue
        seen.add(key)
        f_toks, e_toks = _tokens(tay), _tokens(vi)
        if f_toks and e_toks:
            corpus.append(([NULL] + f_toks, e_toks))

    # Khởi tạo đều: mỗi từ Việt ban đầu có thể sinh ra từ bất kỳ từ Tày nào cùng câu.
    pairs_seen: set[tuple[str, str]] = set()
    for f_toks, e_toks in corpus:
        for f in f_toks:
            for e in e_toks:
                pairs_seen.add((f, e))
    if not pairs_seen:
        _CACHE.update(path=str(excel_path), t={}, best={}, locked=lock, iters=0, pairs=0)
        return

    e_per_f: dict[str, set[str]] = {}
    for f, e in pairs_seen:
        e_per_f.setdefault(f, set()).add(e)
    t: dict[tuple[str, str], float] = {
        (f, e): 1.0 / len(es) for f, es in e_per_f.items() for e in es
    }

    for _ in range(iterations):
        count: dict[tuple[str, str], float] = {}
        total_f: dict[str, float] = {}
        for f_toks, e_toks in corpus:
            for e in e_toks:
                # Chuẩn hóa trên mọi từ Tày có thể sinh ra `e` trong câu này.
                s_total = sum(t.get((f, e), 0.0) for f in f_toks) or 1e-12
                for f in f_toks:
                    p = t.get((f, e), 0.0)
                    if p <= 0.0:
                        continue
                    c = p / s_total
                    count[(f, e)] = count.get((f, e), 0.0) + c
                    total_f[f] = total_f.get(f, 0.0) + c
        t = {k: v / total_f[k[0]] for k, v in count.items() if total_f.get(k[0], 0.0) > 0.0}

    best: dict[str, list[tuple[str, float]]] = {}
    for (f, e), p in t.items():
        if f == NULL or p < min_prob:
            continue
        best.setdefault(f, []).append((e, p))
    for f in best:
        best[f].sort(key=lambda x: -x[1])
        del best[f][8:]

    _CACHE.update(
        path=str(excel_path), mtime=excel_path.stat().st_mtime, t=t, best=best,
        locked=lock, iters=iterations, pairs=len(corpus),
    )


def ensure_model(excel_path: Path) -> None:
    excel_path = Path(excel_path)
    if _CACHE["locked"]:
        return
    mtime = excel_path.stat().st_mtime
    if _CACHE["path"] == str(excel_path) and _CACHE["mtime"] == mtime:
        return
    build(excel_path)


def prob(tay_word: str, vi_word: str) -> float:
    """P(từ Việt | từ Tày) đã học được."""
    return _CACHE["t"].get(((tay_word or "").lower(), (vi_word or "").lower()), 0.0)


def score_pair(tay_phrase: str, vi_phrase: str) -> float:
    """
    Điểm log trung bình cho một ứng viên nghĩa.

    Lấy khớp tốt nhất giữa từng từ tiếng Việt và các từ Tày trong cụm, rồi trung
    bình theo số từ để cụm dài không bị phạt oan.
    """
    f_toks, e_toks = _tokens(tay_phrase), _tokens(vi_phrase)
    if not f_toks or not e_toks:
        return 0.0
    total = 0.0
    for e in e_toks:
        p = max((prob(f, e) for f in f_toks), default=0.0)
        total += math.log(max(p, 1e-6))
    return total / len(e_toks)


def is_ready() -> bool:
    return bool(_CACHE["t"])


def stats() -> dict:
    return {
        "pairs_trained_on": _CACHE["pairs"],
        "iterations": _CACHE["iters"],
        "translation_probs": len(_CACHE["t"]),
        "tay_words_with_candidates": len(_CACHE["best"]),
    }


def top_translations(tay_word: str, k: int = 5) -> list[tuple[str, float]]:
    return _CACHE["best"].get((tay_word or "").lower(), [])[:k]
