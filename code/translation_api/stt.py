import base64
import os
import tempfile


_WHISPER_MODELS: dict[str, object] = {}


def _env_flag(name: str, *, default_on: bool) -> bool:
    """Đọc biến môi trường 0/1, true/false; default_on khi biến chưa đặt."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default_on
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _get_whisper_model(model_name: str):
    """Lazy-load Whisper so text translation works without speech dependencies."""
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError(
            "Speech input is unavailable. Install openai-whisper and put ffmpeg on PATH."
        ) from exc

    model = _WHISPER_MODELS.get(model_name)
    if model is None:
        model = whisper.load_model(model_name)
        _WHISPER_MODELS[model_name] = model
    return model


def stt_from_b64(
    audio_b64: str,
    model_name: str = "base",
    language: str | None = None,
    *,
    initial_prompt: str | None = None,
    max_audio_bytes: int = 8 * 1024 * 1024,
) -> str:
    """Chuyển đổi âm thanh base64 thành văn bản (webm/wav/mp3/... — ffmpeg đọc theo nội dung)."""
    try:
        audio = base64.b64decode(audio_b64)
    except Exception as e:
        return f"STT Error: audio_b64 không hợp lệ ({e})"

    if len(audio) > max_audio_bytes:
        return f"STT Error: file âm thanh quá lớn (>{max_audio_bytes} bytes)"

    # Trên Windows, NamedTemporaryFile(delete=True) giữ file đang mở → ffmpeg/Whisper không đọc được.
    fd, path = tempfile.mkstemp(suffix=".bin")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        model = _get_whisper_model(model_name)
        decode_kw: dict = {}
        if (language or "").strip():
            decode_kw["language"] = (language or "").strip()
        ip = (initial_prompt or "").strip()
        if ip:
            decode_kw["initial_prompt"] = ip
            # Với micro thật: giữ prompt qua các cửa sổ 30s giúp bám chữ Tày; tắt bằng WHISPER_STT_CARRY_INITIAL_PROMPT=0
            decode_kw["carry_initial_prompt"] = _env_flag(
                "WHISPER_STT_CARRY_INITIAL_PROMPT", default_on=True
            )
        # Giảm lặp / “bắt bừa” khi nhiễu hoặc đoạn ngắn; bật lại bằng WHISPER_STT_CONDITION_PREV=1
        decode_kw["condition_on_previous_text"] = _env_flag(
            "WHISPER_STT_CONDITION_PREV", default_on=False
        )
        r = model.transcribe(path, **decode_kw)
        return (r.get("text") or "").strip()
    except Exception as e:
        return f"STT Error: {str(e)}"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
