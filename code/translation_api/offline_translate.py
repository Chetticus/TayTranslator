import re
import unicodedata
from functools import lru_cache

from .rag import lookup_terms


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    nfkd = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in nfkd if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text)
    return text


def _best_gloss_for_phrase(phrase: str) -> tuple[str | None, list[dict]]:
    items = lookup_terms(phrase, k=8)
    if not items:
        return None, []

    norm_phrase = _normalize(phrase)
    for item in items:
        if _normalize(item.get("tay", "")) == norm_phrase:
            return item.get("vi"), items

    return items[0].get("vi"), items


@lru_cache(maxsize=512)
def _cached_best_gloss(phrase: str) -> str | None:
    gloss, _ = _best_gloss_for_phrase(phrase)
    return gloss


def translate_tay_to_vi_offline(text: str, max_ngram: int = 4) -> dict:
    """
    Dịch offline theo từ điển:
    - Ưu tiên khớp cụm dài trước
    - Fallback về từng từ
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return {"translation": "", "glossary": []}

    words = clean_text.split()
    i = 0
    translated_parts: list[str] = []
    glossary: list[dict] = []

    while i < len(words):
        found = False
        max_size = min(max_ngram, len(words) - i)

        for size in range(max_size, 0, -1):
            phrase = " ".join(words[i:i + size])
            gloss = _cached_best_gloss(phrase)
            if gloss:
                translated_parts.append(gloss)
                glossary.append({"tay": phrase, "vi": gloss})
                i += size
                found = True
                break

        if not found:
            unknown = words[i]
            translated_parts.append(f"[{unknown}]")
            glossary.append({"tay": unknown, "vi": "(chưa có trong từ điển)"})
            i += 1

    return {
        "translation": " ".join(translated_parts),
        "glossary": glossary,
    }

