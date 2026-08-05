import sqlite3
import time
import json
import pathlib

DB = pathlib.Path("db/corpus.db")


def init_db():
    """Khởi tạo database corpus song ngữ."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS parallel_corpus(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tay TEXT,
        vi TEXT,
        tags TEXT,
        source TEXT,
        created_at REAL
    );""")
    return con


def insert_pairs(con, pairs: list[dict], source: str):
    """Chèn các cặp câu song ngữ vào database."""
    cur = con.cursor()
    for p in pairs:
        cur.execute(
            "INSERT INTO parallel_corpus(tay,vi,tags,source,created_at) VALUES (?,?,?,?,?)",
            (p["tay"], p["vi"], json.dumps([], ensure_ascii=False), source, time.time())
        )
    con.commit()
