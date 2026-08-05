import sqlite3
import pathlib

DB = pathlib.Path("db/dictionary.db")


def init_db():
    """Khởi tạo database từ điển với FTS5."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    # FTS5 để tìm kiếm fuzzy/FTS
    con.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS dictionary USING fts5(
        headword_tay, meaning_vi, variants, senses, source_page, content=''
    );""")
    return con


def import_entries(con, entries: list[dict]):
    """Nhập các từ vựng vào database từ điển."""
    cur = con.cursor()
    cur.execute("DELETE FROM dictionary;")
    cur.executemany("""INSERT INTO dictionary(headword_tay, meaning_vi, variants, senses, source_page)
                       VALUES (?,?,?,?,?)""",
                    [(e["headword_tay"], e["meaning_vi"], e["variants"], e["senses"], e["source_page"])
                     for e in entries])
    con.commit()
