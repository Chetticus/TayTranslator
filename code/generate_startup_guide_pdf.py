# -*- coding: utf-8 -*-
"""Sinh file PDF hướng dẫn cài đặt và khởi chạy hệ thống.

Chạy từ thư mục code:
    python generate_startup_guide_pdf.py
    (cần: pip install fpdf2)

File ra: ../HUONG_DAN_KHOI_DONG_HE_THONG.pdf
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
OUT_PDF = ROOT / "HUONG_DAN_KHOI_DONG_HE_THONG.pdf"
ARIAL = Path(r"C:\Windows\Fonts\arial.ttf")
ARIAL_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")


def _add_fonts(pdf: FPDF) -> None:
    if not ARIAL.is_file():
        raise FileNotFoundError(f"Không tìm thấy font: {ARIAL}")
    pdf.add_font("ArialVI", "", str(ARIAL))
    pdf.add_font("ArialVI", "B", str(ARIAL_BOLD if ARIAL_BOLD.is_file() else ARIAL))


def _title(pdf: FPDF, text: str) -> None:
    pdf.set_font("ArialVI", "B", 16)
    pdf.multi_cell(0, 10, text)
    pdf.ln(4)


def _h2(pdf: FPDF, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("ArialVI", "B", 13)
    pdf.multi_cell(0, 9, text)
    pdf.ln(1)


def _p(pdf: FPDF, text: str) -> None:
    pdf.set_font("ArialVI", "", 11)
    pdf.multi_cell(0, 6, text)
    pdf.ln(1)


def _code(pdf: FPDF, text: str) -> None:
    pdf.set_font("ArialVI", "", 10)
    pdf.multi_cell(0, 5, text)
    pdf.ln(1)


def build_pdf() -> Path:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    _add_fonts(pdf)

    _title(pdf, "Hướng dẫn cài đặt và khởi động hệ thống")
    _p(pdf, "Dự án: Tày – Việt (chat Tày → Việt, STT Whisper, từ điển Excel).")
    _p(
        pdf,
        "Tài liệu hướng dẫn cài đặt môi trường (Python, FFmpeg, thư viện, Ollama), "
        "cách tạo venv, chạy ứng dụng, và lưu ý về model Whisper (không nằm trong file zip bàn giao).",
    )

    _h2(pdf, "1. Gói mã nguồn / file ZIP bàn giao")
    _p(
        pdf,
        "File ZIP do script export_project_zip.py tạo ra không gồm: thư mục venv, __pycache__, .git, "
        "các thư mục cache công cụ, file .env / config.env (tránh lộ khóa cục bộ). Model Whisper không đóng gói trong zip — khi chạy STT lần đầu, "
        "OpenAI Whisper sẽ tải trọng số về thư mục cache của người dùng (thường là "
        "%USERPROFILE%\\.cache\\whisper trên Windows), cần Internet và vài trăm MB trở lên tùy model.",
    )

    _h2(pdf, "2. Cài Python")
    _p(pdf, "• Tải Python 3.10 hoặc mới hơn từ https://www.python.org/downloads/windows/")
    _p(pdf, "• Khi cài, nên bật tùy chọn “Add python.exe to PATH” (Thêm Python vào PATH).")
    _p(pdf, "• Kiểm tra: mở PowerShell mới, chạy: python --version")

    _h2(pdf, "3. Cài FFmpeg (bắt buộc cho STT / Whisper)")
    _p(
        pdf,
        "Whisper dùng ffmpeg để đọc file âm thanh (webm, mp3, …). Nếu thiếu ffmpeg, STT sẽ lỗi.",
    )
    _p(pdf, "Cách phổ biến trên Windows:")
    _p(pdf, "• Tải bản ZIP “essentials” hoặc “full” từ trang build FFmpeg (ví dụ gyan.dev/ffmpeg/builds/).")
    _p(pdf, "• Giải nén vào thư mục cố định (ví dụ C:\\ffmpeg hoặc D:\\ffmpeg).")
    _p(
        pdf,
        "• Thêm thư mục …\\bin (chứa ffmpeg.exe) vào biến môi trường PATH của người dùng hoặc hệ thống; "
        "đóng mở lại PowerShell.",
    )
    _p(pdf, "• Kiểm tra: ffmpeg -version")
    _p(pdf, "• Có thể dùng winget/chocolatey nếu môi trường của bạn hỗ trợ: ví dụ winget install FFmpeg.")

    _h2(pdf, "4. Tạo môi trường ảo (venv) và cài thư viện Python")
    _p(pdf, "Trong PowerShell, cd vào thư mục gốc dự án (nơi có thư mục code và file requirements):")
    _code(pdf, "cd D:\\BkStar\\Tay-Viet")
    _p(pdf, "Tạo venv (một lần):")
    _code(pdf, "python -m venv venv")
    _p(pdf, "Kích hoạt venv:")
    _code(pdf, r".\venv\Scripts\Activate.ps1")
    _p(pdf, "Nâng pip (khuyến nghị) và cài dependency cho luồng chính trong thư mục code:")
    _code(pdf, "python -m pip install --upgrade pip\npip install -r code\\requirements.txt")
    _p(
        pdf,
        "File code/requirements.txt gồm fastapi, uvicorn, openai-whisper, gTTS, pandas, openpyxl, … "
        "Cài đặt có thể mất vài phút và tải các gói PyTorch/Whisper khá lớn.",
    )
    _p(
        pdf,
        "Để sinh lại file PDF hướng dẫn này trên máy dev: pip install fpdf2 rồi chạy python code\\generate_startup_guide_pdf.py",
    )

    _h2(pdf, "5. Cài Ollama (khuyến nghị — dịch có ngữ cảnh)")
    _p(pdf, "• Tải Ollama cho Windows tại https://ollama.com và cài đặt.")
    _p(pdf, "• Mở terminal và kéo model mặc định dùng trong code (ví dụ):")
    _code(pdf, "ollama pull qwen2.5:3b-instruct")
    _p(pdf, "• Đảm bảo Ollama đang chạy (thường tự khởi động dịch vụ). Ứng dụng mặc định gọi http://127.0.0.1:11434")

    _h2(pdf, "6. Từ điển Excel")
    _p(
        pdf,
        "Cần có file tu_dien_viet_tay_nung_parsed.xlsx ở thư mục gốc dự án (cùng cấp với thư mục code). "
        "Nếu đặt chỗ khác, đặt biến EXCEL_GLOSSARY_PATH trỏ tới đường dẫn đầy đủ (xem mục 10).",
    )

    _h2(pdf, "7. Kiểm tra nhanh trước khi chạy web")
    _p(pdf, "• python --version")
    _p(pdf, "• ffmpeg -version")
    _p(pdf, "• ollama list (nếu dùng Ollama)")
    _p(pdf, "• Đã kích hoạt venv và pip install -r code\\requirements.txt xong không lỗi")

    _h2(pdf, "8. Khởi động giao diện chat (luồng chính)")
    _p(pdf, "Kích hoạt venv (nếu chưa), sau đó:")
    _code(pdf, r"cd D:\BkStar\Tay-Viet\code")
    _code(
        pdf,
        r"..\venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8000 --reload",
    )
    _p(pdf, "Mở trình duyệt: http://127.0.0.1:8000/")
    _p(
        pdf,
        "Dùng chat: nhập chữ Tày rồi Enter để dịch. Nút micro: bấm bắt đầu / bấm dừng để gửi STT; "
        "chữ nhận dạng được chèn vào ô nhập — Enter để dịch. Dừng server: Ctrl+C trong cửa sổ uvicorn.",
    )

    _h2(pdf, "9. STT (Whisper) — lưu ý")
    _p(
        pdf,
        "Whisper không có mã “Tày”. Ứng dụng mặc định dùng language=vi và initial_prompt mẫu để hạn chế "
        "phiên âm sang tiếng Anh. Ghi âm micro thật khó hơn thử bằng máy đọc chữ; có thể thử "
        "WHISPER_STT_MODEL=small hoặc WHISPER_STT_LANGUAGE=auto (mục 10).",
    )

    _h2(pdf, "10. API dịch tách (tùy chọn)")
    _code(
        pdf,
        r"cd D:\BkStar\Tay-Viet\code"
        "\n"
        r"..\venv\Scripts\uvicorn.exe translation_api.main:app --host 127.0.0.1 --port 8001 --reload",
    )
    _p(pdf, "Ví dụ: GET /health, POST /stt, POST /tts, POST /translate.")

    _h2(pdf, "11. Biến môi trường (PowerShell — đặt trước khi chạy uvicorn)")
    _code(
        pdf,
        '$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"\n'
        '$env:OLLAMA_MODEL="qwen2.5:3b-instruct"\n'
        '$env:WHISPER_STT_MODEL="base"\n'
        '$env:WHISPER_STT_LANGUAGE="vi"',
    )
    _p(pdf, "Whisper tự đoán ngôn ngữ:")
    _code(pdf, '$env:WHISPER_STT_LANGUAGE="auto"')
    _p(pdf, "Đường dẫn từ điển tùy chỉnh:")
    _code(
        pdf,
        r'$env:EXCEL_GLOSSARY_PATH="D:\BkStar\Tay-Viet\tu_dien_viet_tay_nung_parsed.xlsx"',
    )
    _p(
        pdf,
        "Tinh chỉnh STT: WHISPER_STT_CARRY_INITIAL_PROMPT=0; WHISPER_STT_CONDITION_PREV=1 (xem mã translation_api/stt.py).",
    )

    _h2(pdf, "12. Xử lý sự cố thường gặp")
    _p(pdf, "• STT lỗi: kiểm tra ffmpeg trong PATH; mở terminal mới sau khi sửa PATH.")
    _p(pdf, "• Cổng 8000 bận: đổi --port 8010 và mở đúng URL cổng mới.")
    _p(pdf, "• Ollama không kết nối: kiểm tra dịch vụ và tên model.")
    _p(pdf, "• Micro: cấp quyền cho trình duyệt; dùng localhost.")

    _h2(pdf, "13. Tạo lại file ZIP bàn giao (tùy dev)")
    _p(pdf, "Trong thư mục code:")
    _code(pdf, "python export_project_zip.py")
    _p(pdf, "Sinh file Tay-Viet-export-YYYYMMDD.zip ở thư mục gốc dự án (đã loại venv, cache, .env / config.env).")

    _h2(pdf, "14. Tái tạo file PDF này")
    _code(pdf, "pip install fpdf2\npython generate_startup_guide_pdf.py")

    pdf.ln(2)
    _p(pdf, "Hãy thay các đường dẫn ví dụ ổ D: bằng đường dẫn thực tế trên máy bạn.")

    pdf.output(str(OUT_PDF))
    return OUT_PDF


if __name__ == "__main__":
    print(build_pdf())
