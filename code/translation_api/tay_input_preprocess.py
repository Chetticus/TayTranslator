from __future__ import annotations

import re
import unicodedata

_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"\S+")


def _norm_token(text: str) -> str:
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _SPACE_RE.sub(" ", text)
    return text


def _strip_viet_gloss_after_question(s: str, common_viet_norms: frozenset[str]) -> str:
    """Bỏ đoạn sau '?' nếu toàn bộ token trông giống từ Việt trong bảng dùng chung (gloss trong dòng ví dụ)."""
    if "?" not in s or not common_viet_norms:
        return s
    q = s.index("?")
    head = s[: q + 1].rstrip()
    tail = s[q + 1 :].strip()
    if not tail:
        return head
    words = _TOKEN_RE.findall(tail)
    if not words:
        return head
    if all(_norm_token(w) in common_viet_norms for w in words):
        return head
    return s


def preprocess_tay_input(text: str, common_viet_norms: frozenset[str] | None = None) -> str:
    """
    Làm sạch dòng hỗn hợp (câu Tày + gloss tiếng Việt + ký hiệu ~:).

    - Nếu có '~:' ưu tiên nối phần trước (đã tỉa gloss sau '?') với phần sau '~:'.
    - Gỡ bỏ khoảng trắng quanh ':' từng phần (tránh dính mẫu "VI : TAY" lẫn vào một dòng).
    """
    t = (text or "").strip()
    if not t:
        return t

    norms = common_viet_norms or frozenset()

    m = re.match(r"^(.*?)(\s*~\s*:\s*)(.*)$", t, flags=re.DOTALL)
    if m:
        left, _, right = m.group(1).strip(), m.group(2), m.group(3).strip()
        left = _strip_viet_gloss_after_question(left, norms)
        t = f"{left} {right}".strip() if right else left
    else:
        t = re.sub(r"\s*~\s*:?\s*", " ", t)

    t = _strip_viet_gloss_after_question(t, norms)
    t = re.sub(r"\s+:\s+", " ", t)
    t = _SPACE_RE.sub(" ", t).strip()
    return t
