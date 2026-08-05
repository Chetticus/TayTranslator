# API đơn giản không dùng STT/Whisper
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

from .rag import lookup_terms, fetch_examples, log_interaction
from .nlp_gpt import translate_with_context
from .tts import tts_b64


class TranslateIn(BaseModel):
    text: str
    mode: str = "default"


class TranslateOut(BaseModel):
    translation: str
    glossary: list | None = None


class TTSIn(BaseModel):
    text: str


app = FastAPI(title="Tay–Viet API (Translation API - Simple)")


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


@app.post("/tts")
def tts(payload: TTSIn):
    """Chuyển đổi văn bản thành âm thanh."""
    audio_b64 = tts_b64(payload.text)
    ok = not (isinstance(audio_b64, str) and audio_b64.startswith("TTS Error:"))
    return {"ok": ok, "audio_b64": audio_b64}

