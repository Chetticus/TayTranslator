from gtts import gTTS
import base64
import tempfile
import os


def tts_b64(text: str, lang: str = "vi") -> str:
    """Chuyển đổi văn bản thành âm thanh base64."""
    try:
        tts = gTTS(text=text, lang=lang)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name
        
        tts.save(temp_path)
        
        with open(temp_path, "rb") as audio_file:
            audio_data = base64.b64encode(audio_file.read()).decode()
        
        try:
            os.unlink(temp_path)
        except OSError:
            pass
            
        return audio_data
    except Exception as e:
        return f"TTS Error: {str(e)}"
