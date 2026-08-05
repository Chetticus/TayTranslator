import json
import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env để chạy được khi gọi như module/pytest
load_dotenv()

_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=_API_KEY) if _API_KEY else None
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


def gpt_make_pairs(transcript: str) -> list[dict]:
    """Nhờ GPT cắt transcript thành cặp {tay, vi} ngắn gọn (≤20 từ)."""
    if client is None:
        return [{"tay": transcript[:120], "vi": "(thiếu OPENAI_API_KEY)"}]
    sys = "Bạn là biên tập viên dữ liệu Tày–Việt. Trả về JSON list [{tay, vi}] các câu ≤20 từ."
    usr = f"Transcript Tày (thô):\n{transcript}\nHãy chia thành cặp câu Tày–Việt ngắn gọn."
    
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": usr}
            ]
        )
        txt = resp.choices[0].message.content
        data = json.loads(txt)
        return [d for d in data if isinstance(d, dict) and "tay" in d and "vi" in d]
    except Exception:
        return [{"tay": transcript[:120], "vi": "(chưa rõ)"}]
