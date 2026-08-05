from pdf_to_dictionary.parse_pdf import parse_entries


def test_parse_entries():
    """Test phân tích các từ vựng từ văn bản thô."""
    raw = "mốc slẩy: bụng dạ rối bời\nải chải: làm rất chăm"
    entries = parse_entries(raw)
    assert len(entries) >= 2
    assert entries[0]["headword_tay"] == "mốc slẩy"
    assert "bụng dạ rối bời" in entries[0]["meaning_vi"]


def test_parse_entries_empty():
    """Test với văn bản rỗng."""
    entries = parse_entries("")
    assert isinstance(entries, list)
    assert len(entries) == 0


def test_parse_entries_no_colon():
    """Test với văn bản không có dấu hai chấm."""
    raw = "chỉ là văn bản thường\nkhông có định dạng từ điển"
    entries = parse_entries(raw)
    assert len(entries) == 0
