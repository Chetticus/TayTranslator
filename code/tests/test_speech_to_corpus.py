from speech_to_corpus.pairs import gpt_make_pairs


def test_pairs_format():
    """Test định dạng cặp câu được tạo bởi GPT."""
    data = gpt_make_pairs("Xin chào. Hôm nay học chăm.")
    assert isinstance(data, list)
    if len(data) > 0:
        assert isinstance(data[0], dict)
        assert "tay" in data[0]
        assert "vi" in data[0]


def test_empty_transcript():
    """Test với transcript rỗng."""
    data = gpt_make_pairs("")
    assert isinstance(data, list)
