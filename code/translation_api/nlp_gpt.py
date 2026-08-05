import os
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=_API_KEY) if _API_KEY else None
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


def translate_with_context(tay_text: str, dict_items: list, examples: list, mode: str = "default") -> str:
    """Dịch văn bản Tày sang Việt với ngữ cảnh từ từ điển và ví dụ."""
    if client is None:
        return "Lỗi dịch thuật: thiếu OPENAI_API_KEY (hãy tạo `.env` từ `env.example` và điền key)."
    sys = ("Bạn dịch Tày→Việt, ưu tiên nghĩa trong danh sách từ điển nếu đúng ngữ cảnh. "
           "Đầu ra ngắn gọn gồm: Translation và Glossary.")
    
    ctx_dict = "\n".join([f"- {i['tay']} → {i['vi']}" for i in dict_items]) or "(trống)"
    ctx_ex = "\n".join([f"- {e['tay']} → {e['vi']}" for e in examples]) or "(trống)"
    
    usr = f"""Câu Tày: {tay_text}

Từ điển (tham chiếu):
{ctx_dict}

Ví dụ câu tương tự:
{ctx_ex}

Chế độ: {mode}
"""
    
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": usr}
            ]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Lỗi dịch thuật: {str(e)}"
