"""Content fingerprints for reproducibility; contains no input text or secrets."""
import hashlib
import os
import platform
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


ROOT = Path(__file__).resolve().parent
# Capture source at process startup, so editing disk files cannot relabel an old server.
_SOURCE = {p.relative_to(ROOT).as_posix(): file_hash(p) for p in
           [ROOT / "main.py", Path(__file__), *sorted((ROOT / "translation_api").rglob("*.py"))]}
_CONFIG = {name: os.getenv(name, default) for name, default in {
    "USE_LLM": "0", "LM_DECODE": "1", "LM_WEIGHT": "0.10", "MINED_PHRASES": "1",
    "MINED_PHRASE_SCORE": "18.0", "ALIGN_MODEL": "0", "ALIGN_WEIGHT": "0.60",
    "FUZZY_MATCH": "1", "RETRIEVE_K": "2", "LOW_COVERAGE_THRESHOLD": "0.35",
    "HIGH_COVERAGE_THRESHOLD": "0.70", "OLLAMA_MODEL": ""}.items()}
_RUNTIME = {"python": platform.python_version(), **{name: version(name) for name in ("pandas", "openpyxl", "pydantic", "fastapi")}}
for _name in ('ctranslate2', 'sentencepiece'):
    try:
        _RUNTIME[_name] = version(_name)
    except PackageNotFoundError:
        _RUNTIME[_name] = None


def fingerprint(dictionary_path):
    import json
    evidence = {"source_sha256": _SOURCE, "config": _CONFIG,
                "english_models": {pair: file_hash(ROOT / 'models/english' / pair / 'installation.json')
                    if (ROOT / 'models/english' / pair / 'installation.json').exists() else None
                    for pair in ('en_vi', 'vi_en')},
                "runtime": _RUNTIME,
                "lexicon_sha256": file_hash(os.getenv("COMMON_VIET_LEXICON_PATH", ROOT / "translation_api/data/common_viet_lexicon.json")) if Path(os.getenv("COMMON_VIET_LEXICON_PATH", ROOT / "translation_api/data/common_viet_lexicon.json")).exists() else None,
                "dictionary_sha256": file_hash(dictionary_path)}
    return {**evidence, "id": hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()}
