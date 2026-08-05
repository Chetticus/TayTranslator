from translation_api.rag import lookup_terms


def test_lookup_no_error():
    """Test tra cứu từ không gây lỗi."""
    items = lookup_terms("mốc slẩy")
    assert isinstance(items, list)


def test_lookup_empty_query():
    """Test tra cứu với query rỗng."""
    items = lookup_terms("")
    assert isinstance(items, list)


def test_lookup_special_chars():
    """Test tra cứu với ký tự đặc biệt."""
    items = lookup_terms("test@#$%")
    assert isinstance(items, list)
