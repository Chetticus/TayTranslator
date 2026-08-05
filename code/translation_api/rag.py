import sqlite3
import json
import time
from pathlib import Path

# Không phụ thuộc current working directory khi chạy uvicorn/pytest
BASE_DIR = Path(__file__).resolve().parents[1]  # .../code
DB_DIR = BASE_DIR / "db"
DICT_DB = DB_DIR / "dictionary.db"
CORP_DB = DB_DIR / "corpus.db"
PROJ_DB = DB_DIR / "project.db"


def dict_conn():
    """Kết nối database từ điển."""
    return sqlite3.connect(DICT_DB)


def corpus_conn():
    """Kết nối database corpus."""
    return sqlite3.connect(CORP_DB)


def project_conn():
    """Kết nối database dự án."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(PROJ_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS interactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tay TEXT,
        context TEXT,
        output TEXT,
        created_at REAL
    );""")
    return con


def lookup_terms(q: str, k: int = 8) -> list[dict]:
    """Tra cứu từ trong từ điển."""
    con = dict_conn()
    cur = con.cursor()
    try:
        cur.execute("SELECT headword_tay, meaning_vi FROM dictionary WHERE dictionary MATCH ?", (q,))
        rows = cur.fetchall()
        return [{"tay": r[0], "vi": r[1]} for r in rows[:k]]
    except sqlite3.OperationalError:
        # Fallback nếu FTS5 chưa có dữ liệu
        return []


def fetch_examples(k: int = 5) -> list[dict]:
    """Lấy ví dụ ngẫu nhiên từ corpus."""
    con = corpus_conn()
    cur = con.cursor()
    try:
        cur.execute("SELECT tay, vi FROM parallel_corpus ORDER BY RANDOM() LIMIT ?", (k,))
        return [{"tay": r[0], "vi": r[1]} for r in cur.fetchall()]
    except sqlite3.OperationalError:
        # Fallback nếu table chưa tồn tại
        return []


def log_interaction(tay: str, context: dict, output: str):
    """Ghi log tương tác."""
    con = project_conn()
    cur = con.cursor()
    cur.execute("INSERT INTO interactions(tay, context, output, created_at) VALUES (?,?,?,?)",
                (tay, json.dumps(context, ensure_ascii=False), output, time.time()))
    con.commit()
