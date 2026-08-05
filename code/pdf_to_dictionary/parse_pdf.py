import re
try:
    from pdfminer.high_level import extract_text
except ImportError:  # pragma: no cover
    extract_text = None


def extract_raw_text(pdf_path: str) -> str:
    """Trích xuất văn bản thô từ file PDF."""
    if extract_text is None:
        raise RuntimeError("Thiếu dependency `pdfminer.six`. Hãy chạy: pip install -r requirements.txt")
    return extract_text(pdf_path)


def parse_entries(raw: str) -> list[dict]:
    """
    Phân tích các từ vựng từ văn bản thô.
    MVP: giả định dòng dạng 'headword: nghĩa; ví dụ || ví dụ'
    Sau có thể tinh chỉnh regex theo PDF thật.
    """
    entries = []
    for line in raw.splitlines():
        if ":" in line:
            head, body = line.split(":", 1)
            head = re.sub(r"\s+", " ", head.strip())
            body = re.sub(r"\s+", " ", body.strip())
            if head and body:
                entries.append({
                    "headword_tay": head,
                    "meaning_vi": body,
                    "variants": "[]",
                    "senses": '[{"vi": "%s"}]' % body.replace('"', '\\"'),
                    "source_page": None
                })
    return entries
