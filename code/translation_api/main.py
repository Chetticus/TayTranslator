# Chạy: uvicorn translation_api.main:app --reload --port 8000
from fastapi import FastAPI
from pydantic import BaseModel
from .rag import lookup_terms, fetch_examples, log_interaction
from .nlp_gpt import translate_with_context
from .stt import stt_from_b64
from .tts import tts_b64
import time


class TranslateIn(BaseModel):
    text: str
    mode: str = "default"


class TranslateOut(BaseModel):
    translation: str
    glossary: list | None = None


class STTIn(BaseModel):
    audio_b64: str
    """Base64 nội dung nhị phân âm thanh (webm/wav/mp3...)."""

    model_name: str = "base"
    """tiny | base | small | medium | large — cân nhắc tốc độ/chất lượng."""

    language: str | None = None
    """Gợi ý ngôn ngữ cho Whisper (vd: vi). Để trống = tự đoán."""

    initial_prompt: str | None = None
    """Gợi ý văn bản (thường cùng kiểu chữ với đầu ra mong muốn)."""


class TTSIn(BaseModel):
    text: str


app = FastAPI(title="Tay–Viet API (Translation API)")


@app.get("/health")
def health():
    """Kiểm tra trạng thái API."""
    return {"ok": True, "ts": time.time()}


@app.get("/lookup")
def lookup(q: str):
    """Tra cứu từ trong từ điển."""
    return {"query": q, "items": lookup_terms(q)}


@app.post("/translate", response_model=TranslateOut)
def translate(payload: TranslateIn):
    """Dịch văn bản Tày sang Việt."""
    dict_items = lookup_terms(payload.text)
    examples = fetch_examples()
    out = translate_with_context(payload.text, dict_items, examples, payload.mode)
    log_interaction(payload.text, {"dict": dict_items, "ex": examples}, out)
    return {"translation": out, "glossary": dict_items}


@app.post("/stt")
def stt(payload: STTIn):
    """Chuyển đổi âm thanh thành văn bản."""
    text = stt_from_b64(
        payload.audio_b64,
        model_name=payload.model_name,
        language=payload.language,
        initial_prompt=payload.initial_prompt,
    )
    ok = not (isinstance(text, str) and text.startswith("STT Error:"))
    return {"ok": ok, "text": text}


@app.post("/tts")
def tts(payload: TTSIn):
    """Chuyển đổi văn bản thành âm thanh."""
    audio_b64 = tts_b64(payload.text)
    ok = not (isinstance(audio_b64, str) and audio_b64.startswith("TTS Error:"))
    return {"ok": ok, "audio_b64": audio_b64}
