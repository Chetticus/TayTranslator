from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
import os
import re
import json
import unicodedata
from datetime import datetime, timezone

import requests

from translation_api.excel_glossary import (
    _CACHE,
    _ensure_index,
    translate_with_excel_glossary,
)
from translation_api.retriever import corpus_size, retrieve
from translation_api.stt import stt_from_b64


class ChatIn(BaseModel):
    message: str


class SttApiIn(BaseModel):
    audio_b64: str
    model_name: str | None = None
    language: str | None = None
    initial_prompt: str | None = None


app = FastAPI(title="Tày → Việt · Chat UI")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "").strip()
WHISPER_STT_MODEL = os.getenv("WHISPER_STT_MODEL", "base").strip() or "base"

# Ưu tiên model to hơn (dịch tốt hơn hẳn model 3B), nhưng chỉ chọn model CÓ THẬT.
_PREFERRED_OLLAMA_MODELS = (
    "qwen2.5:14b-instruct",
    "qwen2.5:7b-instruct",
    "gemma3:12b",
    "gemma3:4b",
    "qwen2.5:3b-instruct",
)
_RESOLVED_MODEL: str | None = None


def _installed_ollama_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [m.get("name", "") for m in (r.json().get("models") or []) if m.get("name")]
    except requests.RequestException:
        return []


def resolve_ollama_model(force: bool = False) -> str | None:
    """
    Chọn model Ollama thực sự đang có.

    Trước đây mặc định là 'qwen2.5:3b-instruct'; nếu máy không cài model đó thì
    MỌI lần gọi đều lỗi và hệ thống âm thầm rơi về bản ghép từ điển thô, khiến
    người dùng tưởng đã dịch. Nay chọn theo model đã cài và báo rõ khi thiếu.
    """
    global _RESOLVED_MODEL
    if _RESOLVED_MODEL and not force:
        return _RESOLVED_MODEL

    installed = _installed_ollama_models()
    if not installed:
        _RESOLVED_MODEL = OLLAMA_MODEL or None
        return _RESOLVED_MODEL

    def _has(name: str) -> str | None:
        for got in installed:
            if got == name:
                return got
        # Chấp nhận biến thể tag (vd cấu hình 'qwen2.5:7b-instruct' khớp bản '...-q4_K_M')
        for got in installed:
            if got.startswith(name):
                return got
        return None

    if OLLAMA_MODEL:
        exact = _has(OLLAMA_MODEL)
        if exact:
            _RESOLVED_MODEL = exact
            return _RESOLVED_MODEL

    for want in _PREFERRED_OLLAMA_MODELS:
        got = _has(want)
        if got:
            _RESOLVED_MODEL = got
            return _RESOLVED_MODEL

    _RESOLVED_MODEL = installed[0]
    return _RESOLVED_MODEL

# Whisper không có mã "Tày"; mặc định language=vi + initial_prompt mẫu để hạn chế phiên âm sang en.
_DEFAULT_STT_INITIAL_PROMPT = (
    "mốc slẩy. pjom slấy slon tạy. hẹn rặp lại. rồ lẻn khảu mà. ỏ mẻ mà dá. mầư tố hêt pện rứ. rối chêp."
)


def _default_whisper_stt_language() -> str | None:
    """Mặc định vi; đặt WHISPER_STT_LANGUAGE=auto để Whisper tự đoán."""
    raw = os.getenv("WHISPER_STT_LANGUAGE")
    if raw is None:
        return "vi"
    s = raw.strip().lower()
    if s in ("", "auto", "none", "null"):
        return None
    return raw.strip()


def _chat_stt_initial_prompt() -> str | None:
    """Gợi ý kiểu chữ Tày (Latin) cho Whisper; WHISPER_STT_INITIAL_PROMPT=__none__ để tắt."""
    raw = os.getenv("WHISPER_STT_INITIAL_PROMPT")
    if raw is None:
        return _DEFAULT_STT_INITIAL_PROMPT
    s = raw.strip()
    if s in ("", "__none__", "-"):
        return None
    return s


EXCEL_GLOSSARY_PATH = Path(os.getenv("EXCEL_GLOSSARY_PATH", str(Path(__file__).resolve().parents[1] / "tu_dien_viet_tay_nung_parsed.xlsx")))
LOW_COVERAGE_THRESHOLD = float(os.getenv("LOW_COVERAGE_THRESHOLD", "0.35"))
HIGH_COVERAGE_THRESHOLD = float(os.getenv("HIGH_COVERAGE_THRESHOLD", "0.70"))
UNKNOWN_LOG_PATH = Path(os.getenv("UNKNOWN_LOG_PATH", str(Path(__file__).resolve().parent / "unknown_terms_log.jsonl")))
# Quét trên 500 câu tách riêng: LẤY ÍT ví dụ lại tốt hơn. chrF theo K là
# 1:0.390  2:0.399  3:0.393  5:0.387  8:0.378  20:0.376 — càng nhiều câu truy
# xuất càng nhiều nhiễu đẩy sai nghĩa, đúng như kết quả "bằng chứng gộp chung
# còn hại hơn không dùng ngữ cảnh".
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "2"))

# Bước biên tập bằng LLM MẶC ĐỊNH TẮT — quyết định dựa trên số đo, không phải
# sở thích. Đo trên tập kiểm tra tách riêng (eval_translation.py, n=80):
#
#   tra từ điển + chọn nghĩa theo ngữ cảnh : chrF 0.393  (tốt nhất)
#   thêm gemma3:4b                         : chrF 0.366
#   thêm gemma3:4b + ví dụ truy xuất       : chrF 0.361
#   thêm qwen2.5:7b-instruct               : chrF 0.371
#   thêm qwen2.5:7b-instruct + ví dụ       : chrF 0.375
#
# Cả hai model local đều THUA lớp tra từ điển. Model 7B chạy trọn trên GPU
# (4.9/8 GB VRAM) nên không phải do thiếu tài nguyên. Tăng từ 4B lên 7B chỉ được
# ~0.014 chrF, còn thiếu ~0.018 nữa mới hòa.
# Muốn thử lại: đặt USE_LLM=1 rồi chạy `python eval_translation.py --n 80 --llm`
# và chỉ tin khi vượt được 0.393.
USE_LLM = os.getenv("USE_LLM", "0").strip().lower() in ("1", "true", "yes", "on")

_UI_TEMPLATE = Path(__file__).resolve().parent / "templates" / "tay_chat.html"

_WORD_RE = re.compile(r"\S+")


_DICT_SOURCES = ("dict", "dict-loose", "dict-fuzzy")
# Khớp bỏ dấu / gần đúng chỉ là PHỎNG ĐOÁN: "khoi pay thieo" (gõ không dấu) vẫn
# khớp đủ token nhưng ra kết quả sai hoàn toàn. Nếu phần lớn câu dựa vào các
# khớp yếu này thì không được phép báo độ tin cậy cao.
_WEAK_SOURCES = ("dict-loose", "dict-fuzzy")

# Hiệu chỉnh độ tin cậy. Bản đầu chia high/medium theo "câu có khớp được cụm dài
# nào không" — đo ra tương quan với chrF chỉ -0.010, tức là VÔ NGHĨA, và hai
# nhóm high/medium gần như trùng nhau (0.405 so với 0.403).
#
# Hai tín hiệu thật sự dự báo được (500 câu tách riêng):
#   tỉ lệ cụm đa nghĩa  -0.234
#   tỉ lệ khớp yếu      -0.155
#
# Sau khi đổi sang risk = 0.6*đa_nghĩa + 0.4*khớp_yếu:
#   high  chrF 0.564 | medium 0.441 | low 0.304   (khoảng cách +0.260)
_CONF_W_AMBIGUITY = 0.6
_CONF_W_WEAK = 0.4
_CONF_HIGH_RISK = 0.25
_CONF_MED_RISK = 0.60


def _looks_undiacriticized(text: str) -> bool:
    """
    Câu Tày gõ trần không dấu -> mọi lựa chọn nghĩa đều là phỏng đoán.

    Chữ Tày dùng dấu thanh như tiếng Việt, nên câu không có dấu nào gần như chắc
    chắn là gõ thiếu. Nguy hiểm ở chỗ vài dạng không dấu lại TRÙNG từ Tày có
    thật ("khoi", "pay"), nên vẫn khớp chính xác và báo coverage 100% dù dịch
    sai hoàn toàn. Phát hiện ở mức đầu vào là cách duy nhất bắt được ca này.
    """
    decomposed = unicodedata.normalize("NFD", text or "")
    letters = [c for c in decomposed if c.isalpha()]
    if len(letters) < 3:
        return False
    return not any(unicodedata.combining(c) for c in decomposed)


def _build_meta(base: dict) -> dict:
    """
    Gom thống kê từ kết quả tra glossary.

    Chỉ các mục khớp thật trong từ điển mới được tính là "đã biết". Token giữ
    nguyên vì trùng hình thức tiếng Việt được đếm riêng — nếu gộp vào coverage
    thì một câu Tày chưa dịch được vẫn báo 100% và bị đẩy sang chế độ "editor".
    """
    glossary = base.get("glossary") or []
    total = int(base.get("total_tokens") or 0) or 1
    coverage = float(base.get("coverage") or 0.0)

    known_terms = [g for g in glossary if g.get("source") in _DICT_SOURCES]
    passthrough_terms = [g for g in glossary if g.get("source") == "common_viet"]
    weak_tokens = sum(
        len(_WORD_RE.findall(g.get("tay") or ""))
        for g in glossary
        if g.get("source") in _WEAK_SOURCES
    )
    weak_share = weak_tokens / max(1, total)

    # Tỉ lệ cụm phải chọn giữa nhiều nghĩa khả dĩ — tín hiệu dự báo chất lượng
    # mạnh nhất đo được (tương quan -0.234 với chrF trên 500 câu tách riêng).
    # Khớp trúng nguyên CỤM trong từ điển là tín hiệu chắc nhất hệ thống có
    # (điểm 20 so với 2-5 của nghĩa mức từ); các "phương án khác" của nó chỉ là
    # cách diễn đạt khác của cùng cụm đó, không phải mơ hồ thật. Nếu tính cả
    # chúng thì `kin khẩu` -> "ăn cơm" (đúng) lại bị gắn nhãn tin cậy thấp.
    ambiguous_share = (
        sum(1 for g in glossary if g.get("alternatives") and g.get("kind") != "phrase")
        / len(glossary)
        if glossary
        else 0.0
    )
    risk = _CONF_W_AMBIGUITY * ambiguous_share + _CONF_W_WEAK * weak_share

    no_diacritics = _looks_undiacriticized(base.get("preprocessed_input") or "")
    if coverage < LOW_COVERAGE_THRESHOLD or no_diacritics:
        confidence = "low"
    elif risk < _CONF_HIGH_RISK:
        confidence = "high"
    elif risk < _CONF_MED_RISK:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "total_tokens": total,
        "known_tokens": int(base.get("known_tokens") or 0),
        "passthrough_tokens": int(base.get("passthrough_tokens") or 0),
        "coverage": round(coverage, 3),
        "confidence": confidence,
        "weak_tokens": weak_tokens,
        "no_diacritics": no_diacritics,
        "known_terms": known_terms,
        "passthrough_terms": [t.get("tay") for t in passthrough_terms],
        "unknown_terms": base.get("unknown_terms") or [],
    }


def _append_unknown_terms_log(text: str, unknown_terms: list[str], coverage: dict) -> None:
    if not unknown_terms:
        return
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "input_tay": text,
        "unknown_terms": unknown_terms,
        "coverage": coverage.get("coverage"),
        "known_tokens": coverage.get("known_tokens"),
        "total_tokens": coverage.get("total_tokens"),
    }
    UNKNOWN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with UNKNOWN_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


_ALT_LEAK_RE = re.compile(r"\s*[\[(]\s*(?:nghĩa khác|hoặc)\s*:[^\])]*[\])]", re.IGNORECASE)


def _clean_llm_reply(raw: str) -> str:
    """
    Dọn phần thừa mô hình nhỏ hay chép lại.

    Model 3B/4B thường bê nguyên gợi ý '[nghĩa khác: ...]' trong prompt vào câu
    trả lời, hoặc trả về nhiều dòng phương án. Chỉ giữ dòng đầu và bỏ chú thích.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    text = _ALT_LEAK_RE.sub("", text)
    for line in (ln.strip() for ln in text.splitlines()):
        if line:
            return line.strip(" -*").strip()
    return text.strip()


def translate_tay_to_vi_ollama_with_glossary(
    text: str,
    glossary: list[dict],
    coverage: dict,
    style: str,
    examples: list[dict] | None = None,
) -> str:
    """
    Dịch Tày -> Việt bằng Ollama nhưng bị ràng buộc bởi glossary.
    Mục tiêu: tránh 'mượn âm' và suy đoán lung tung.
    """
    # Chỉ đưa các mục từ thật (không đưa unknown) để tránh nhiễu.
    # Từ điển gốc là Việt->Tày nên khi lật chiều, một từ Tày thường có nhiều
    # nghĩa Việt; đưa kèm phương án thay thế để mô hình chọn theo ngữ cảnh.
    known_terms = coverage.get("known_terms") or []
    lines: list[str] = []
    for t in known_terms:
        alts = [a for a in (t.get("alternatives") or []) if a and a != t.get("vi")]
        if alts:
            lines.append(f"- {t['tay']} => {t['vi']}   [nghĩa khác: {', '.join(alts)}]")
        else:
            lines.append(f"- {t['tay']} => {t['vi']}")
    glossary_lines = "\n".join(lines) or "(không có mục từ khớp)"

    untranslated = coverage.get("passthrough_terms") or []
    unknown = coverage.get("unknown_terms") or []
    gaps = [w for w in (list(untranslated) + list(unknown)) if w]
    gap_note = (
        "Các từ CHƯA tra được nghĩa (không được coi là tiếng Việt, đừng chép nguyên): "
        + ", ".join(gaps)
        + "\n"
    ) if gaps else ""

    cov_val = float(coverage.get("coverage") or 0.0)

    if style == "editor":
        full_cov_rule = ""
        if cov_val >= 0.999:
            full_cov_rule = (
                "Coverage ~100%: chỉ được sửa dấu câu và trật tự từ cho tự nhiên; "
                "tuyệt đối không thêm từ mới không xuất hiện trong glossary.\n"
            )
        style_rules = (
            "Mục tiêu: biên tập lại câu tiếng Việt tự nhiên từ glossary, KHÔNG đổi nghĩa.\n"
            + full_cov_rule
            + "Style-Guide: giữ nguyên đại từ và xưng hô đúng theo glossary "
            "(ví dụ glossary ghi mầư=>mày thì không đổi thành 'anh/chị').\n"
            "Nếu có nhiều khả năng, chọn diễn đạt thông dụng nhất nhưng vẫn bám sát glossary."
        )
    else:
        style_rules = (
            "Mục tiêu: suy luận thận trọng từ glossary.\n"
            "Nếu thiếu nghĩa thì giữ nguyên phần thiếu trong ngoặc vuông."
        )

    sys_rules = (
        "Bạn là trợ lý dịch ngôn ngữ Tày sang tiếng Việt.\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1) Không được dịch theo kiểu mượn âm/phiên âm (ví dụ 'sloong' -> 'sông' là SAI).\n"
        "2) Nếu glossary có nghĩa của từ/cụm, bắt buộc ưu tiên dùng nghĩa đó.\n"
        "3) Mục có '[nghĩa khác: ...]' nghĩa là từ đó nhiều nghĩa: hãy CHỌN MỘT nghĩa hợp ngữ cảnh nhất.\n"
        "   Tuyệt đối KHÔNG chép chuỗi '[nghĩa khác: ...]' hay dấu ngoặc đó vào bản dịch.\n"
        "4) Từ Tày chưa tra được nghĩa thì giữ trong ngoặc vuông, KHÔNG chép nguyên như thể đã là tiếng Việt.\n"
        "5) Chỉ trả về DUY NHẤT 1 câu tiếng Việt hoàn chỉnh: không giải thích, không liệt kê phương án.\n"
        f"6) {style_rules}\n"
    )
    # Câu ví dụ tương tự: cho mô hình thấy các từ này được dùng THẾ NÀO, thứ mà
    # bảng nghĩa đơn lẻ không thể hiện (chọn đúng nghĩa + trật tự từ tiếng Việt).
    ex_block = ""
    if examples:
        ex_lines = "\n".join(f"- {e['tay']} => {e['vi']}" for e in examples)
        ex_block = (
            "Câu ví dụ tương tự đã được dịch sẵn (dùng để chọn đúng nghĩa và "
            f"cách đặt câu, KHÔNG chép nguyên):\n{ex_lines}\n\n"
        )

    user = (
        f"Câu Tày: {text}\n\n"
        f"Glossary (Tày => Việt, ưu tiên cụm dài):\n{glossary_lines}\n\n"
        f"{ex_block}"
        f"{gap_note}"
        f"Coverage: {coverage.get('coverage')} ({coverage.get('known_tokens')}/{coverage.get('total_tokens')} token tra được)\n"
        "Bản dịch tiếng Việt:"
    )
    prompt = sys_rules + "\n\n" + user

    model = resolve_ollama_model()
    if not model:
        raise RuntimeError("Không tìm thấy model Ollama nào đang cài.")

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.05, "top_p": 0.8},
    }

    try:
        response = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        translated = _clean_llm_reply(data.get("response") or "")
        if not translated:
            raise RuntimeError("Ollama trả về rỗng.")
        return translated
    except requests.RequestException as e:
        raise RuntimeError(f"Không kết nối được Ollama ({e})") from e


@app.get("/", response_class=HTMLResponse)
def index():
    return _UI_TEMPLATE.read_text(encoding="utf-8")


@app.get("/favicon.svg")
def favicon():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect width="32" height="32" rx="6" fill="#3730a3"/>'
        '<text x="16" y="22" font-size="14" fill="#fff" '
        'text-anchor="middle" font-family="system-ui,sans-serif">T</text>'
        '</svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/health")
def health():
    """Cho biết từ điển và Ollama có sẵn sàng không, thay vì hỏng âm thầm."""
    installed = _installed_ollama_models()
    model = resolve_ollama_model(force=True)
    dict_ok, dict_keys, dict_err, n_examples = True, 0, None, 0
    try:
        _ensure_index(EXCEL_GLOSSARY_PATH)
        dict_keys = len(_CACHE.get("index") or {})
        n_examples = corpus_size(EXCEL_GLOSSARY_PATH)
    except Exception as e:  # từ điển hỏng thì cả hệ thống vô dụng
        dict_ok, dict_err = False, str(e)

    return {
        "ok": dict_ok and bool(model),
        "excel_path": str(EXCEL_GLOSSARY_PATH),
        "excel_exists": EXCEL_GLOSSARY_PATH.exists(),
        "dictionary_ok": dict_ok,
        "dictionary_keys": dict_keys,
        "retrieval_examples": n_examples,
        "dictionary_error": dict_err,
        "ollama_url": OLLAMA_BASE_URL,
        "ollama_reachable": bool(installed),
        "ollama_models": installed,
        "ollama_model_in_use": model,
    }


@app.post("/api/stt")
def api_stt(payload: SttApiIn):
    """Nhận diện giọng nói người dùng (âm thanh base64, thường là webm/opus từ trình duyệt)."""
    model = (payload.model_name or WHISPER_STT_MODEL).strip() or "base"
    if payload.language is not None and str(payload.language).strip():
        lang = str(payload.language).strip()
    else:
        lang = _default_whisper_stt_language()
    if payload.initial_prompt is not None:
        initial = (payload.initial_prompt or "").strip() or None
    else:
        initial = _chat_stt_initial_prompt()
    text = stt_from_b64(
        payload.audio_b64,
        model_name=model,
        language=lang,
        initial_prompt=initial,
    )
    ok = not (isinstance(text, str) and text.startswith("STT Error:"))
    return {"ok": ok, "text": text, "model": model, "language": lang}


@app.post("/api/translate")
def translate(payload: ChatIn):
    text = (payload.message or "").strip()
    if not text:
        return {"mode": "validation", "reply": "Vui lòng nhập câu tiếng Tày.", "glossary": []}

    # 1) Excel-first glossary (single source of truth) + từ Việt dùng chung + tiền xử lý dòng hỗn hợp
    first = translate_with_excel_glossary(text, EXCEL_GLOSSARY_PATH)
    preprocessed = (first.get("preprocessed_input") or text).strip()

    # 2) Truy xuất câu song ngữ tương tự trong kho 14k cặp ví dụ
    try:
        examples = retrieve(preprocessed, EXCEL_GLOSSARY_PATH, k=RETRIEVE_K)
    except Exception:
        examples = []

    # 3) Tra lại, lần này dùng ngữ cảnh vừa truy xuất để CHỌN NGHĨA.
    # Chỉ mục đã nằm sẵn trong cache nên lượt hai gần như miễn phí.
    if examples:
        base = translate_with_excel_glossary(
            text, EXCEL_GLOSSARY_PATH, context_pairs=examples
        )
    else:
        base = first

    glossary = base.get("glossary") or []
    cov = _build_meta(base)
    cov["context_picks"] = base.get("context_picks", 0)
    cov["examples"] = examples
    _append_unknown_terms_log(text, cov["unknown_terms"], cov)

    # 4) Bước LLM bị tắt theo mặc định (xem chú thích ở USE_LLM)
    if not USE_LLM:
        return {
            "mode": "dictionary-context",
            "reply": base.get("translation") or "",
            "glossary": glossary,
            "examples": examples,
            "meta": {**cov, "gate": "no-llm"},
        }

    # 5) Gate theo coverage
    if cov["coverage"] < LOW_COVERAGE_THRESHOLD:
        return {
            "mode": "glossary-only-low-coverage",
            "reply": base.get("translation") or "",
            "glossary": glossary,
            "examples": examples,
            "meta": {**cov, "gate": "low-coverage"},
        }

    style = "editor" if cov["coverage"] >= HIGH_COVERAGE_THRESHOLD else "guided_guess"
    # 6) Ollama chỉ để biên tập/suy luận có ràng buộc
    try:
        translated = translate_tay_to_vi_ollama_with_glossary(
            preprocessed, glossary, cov, style=style, examples=examples
        )
        return {
            "mode": f"ollama-{resolve_ollama_model()}",
            "reply": translated,
            "glossary": glossary,
            "examples": examples,
            "meta": {**cov, "gate": style},
        }
    except RuntimeError as e:
        # 7) Ollama fail -> trả bản glossary-only, nhưng nói rõ là chưa qua LLM
        return {
            "mode": "glossary-only-ollama-fallback",
            "reply": base.get("translation") or "",
            "glossary": glossary,
            "examples": examples,
            "meta": {**cov, "gate": "llm-error-fallback", "error": str(e)},
        }

