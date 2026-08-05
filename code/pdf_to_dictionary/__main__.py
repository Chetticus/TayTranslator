# Chạy: python -m pdf_to_dictionary data/pdf/your_dictionary.pdf
import sys
from pdf_to_dictionary.parse_pdf import extract_raw_text, parse_entries
from pdf_to_dictionary.db import init_db, import_entries


def main(pdf_path: str):
    """Xử lý file PDF từ điển và chuyển thành SQLite database."""
    raw = extract_raw_text(pdf_path)
    entries = parse_entries(raw)
    con = init_db()
    import_entries(con, entries)
    print(f"Đã nhập {len(entries)} từ vựng từ {pdf_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Sử dụng: python -m pdf_to_dictionary <đường_dẫn_file_pdf>")
        sys.exit(1)
    main(sys.argv[1])
