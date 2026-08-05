import whisper

def transcribe_wav(path: str, model_name: str = "base") -> str:
    """Nhận diện tiếng nói Tày → văn bản (dạng thô)."""
    model = whisper.load_model(model_name)
    result = model.transcribe(path, language=None)  # để Whisper tự đoán
    return result["text"].strip()
