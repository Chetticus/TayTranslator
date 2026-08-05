# Chạy: python -m speech_to_corpus data/audio/sample.wav
import sys
import pathlib
from speech_to_corpus.asr import transcribe_wav
from speech_to_corpus.pairs import gpt_make_pairs
from speech_to_corpus.db import init_db, insert_pairs


def main(audio_path: str):
    """Xử lý file âm thanh và chuyển thành corpus song ngữ."""
    text = transcribe_wav(audio_path, model_name="base")
    pairs = gpt_make_pairs(text)
    con = init_db()
    insert_pairs(con, pairs, source=pathlib.Path(audio_path).name)
    print(f"Đã nhập {len(pairs)} cặp câu từ {audio_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Sử dụng: python -m speech_to_corpus <đường_dẫn_file_audio>")
        sys.exit(1)
    main(sys.argv[1])
