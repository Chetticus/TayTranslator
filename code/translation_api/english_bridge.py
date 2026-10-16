"""Offline Argos 1.9 models on CTranslate2. No network calls during inference."""
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import re
import threading

MODEL_ROOT = Path(__file__).resolve().parents[1] / 'models' / 'english'
_LOCK = threading.RLock()


class EnglishUnavailable(RuntimeError):
    pass


class EnglishInputError(ValueError):
    pass


def status():
    dependencies = all(importlib.util.find_spec(name) for name in ('ctranslate2', 'sentencepiece'))
    models = {}
    for pair in ('en_vi', 'vi_en'):
        root = MODEL_ROOT / pair
        ready = all((root / p).is_file() for p in ('installation.json', 'model/model.bin', 'sentencepiece.model', 'metadata.json'))
        models[pair] = {'installed': ready}
        if ready:
            try:
                models[pair]['archive_sha256'] = json.loads((root / 'installation.json').read_text(encoding='utf-8'))['archive_sha256']
            except (ValueError, KeyError, OSError):
                models[pair]['installed'] = False
    return {'ready': dependencies and all(m['installed'] for m in models.values()),
            'provider': 'argos-1.9-ctranslate2-local', 'offline': True, 'models': models,
            'setup': 'Install code/requirements-english.txt and run code/setup_english.py; restart the server.'}


@lru_cache(maxsize=2)
def _load(pair):
    if not status()['ready']:
        raise EnglishUnavailable(status()['setup'])
    try:
        import ctranslate2
        import sentencepiece
        root = MODEL_ROOT / pair
        metadata = json.loads((root / 'metadata.json').read_text(encoding='utf-8'))
        translator = ctranslate2.Translator(str(root / 'model'), device='cpu', compute_type='int8', inter_threads=1, intra_threads=4)
        tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(root / 'sentencepiece.model'))
        return translator, tokenizer, metadata.get('target_prefix', '')
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise EnglishUnavailable('Local English model could not load; rerun setup and check the runtime.') from exc


def _translate_text(text, pair):
    if not text.strip() or not any(c.isalpha() for c in text):
        return text
    translator, tokenizer, prefix = _load(pair)
    tokens = tokenizer.encode(text.strip(), out_type=str)
    if len(tokens) > 400:
        raise EnglishInputError('English mode supports at most 400 model tokens per segment. Please split the text.')
    result = translator.translate_batch([tokens], target_prefix=[[prefix]] if prefix else None,
        beam_size=4, length_penalty=0.2, replace_unknowns=True, max_input_length=0, max_decoding_length=512)[0]
    # Argos packages can emit space markers as literal decoded characters.
    output = tokenizer.decode(result.hypotheses[0]).replace('▁', ' ').replace('_', ' ')
    if prefix and output.startswith(prefix):
        output = output[len(prefix):]
    if not output.strip() or len(result.hypotheses[0]) >= 512:
        raise EnglishInputError('English translation was empty or hit its output limit. Please shorten the text.')
    return output.strip()


def preserved_spans(text, terms, pair):
    from .excel_glossary import _is_structured_literal, _PUNCT
    patterns = [re.escape(term.strip()) for term in terms if term.strip()]
    # Explicit introduction only; do not pretend this is general English NER.
    if pair == 'en_vi':
        name = re.search(r"\bmy name is\s+([^.!?,;\n]+)", text, re.IGNORECASE)
        if name:
            words = re.split(r'\s+(?:and|from|but)\s+', name.group(1), maxsplit=1, flags=re.IGNORECASE)[0].split()
            if 1 <= len(words) <= 5 and all(w.isalpha() for w in words):
                patterns.append(re.escape(' '.join(words)))
    for match in re.finditer(r'\S+', text):
        core = match.group().strip(_PUNCT)
        if core and _is_structured_literal(core):
            patterns.append(re.escape(core))
    # Carry unknown-word markers through the second stage, without inventing meaning.
    patterns += [re.escape(m.group()) for m in re.finditer(r'\[[^\[\]\n]+\]', text)]
    if not patterns:
        return []
    pattern = r'(?<!\w)(?:' + '|'.join(sorted(set(patterns), key=len, reverse=True)) + r')(?!\w)'
    return list(re.finditer(pattern, text, re.IGNORECASE))


def translate(text, pair, protected_terms=None):
    if pair not in ('en_vi', 'vi_en'):
        raise ValueError('Unsupported English bridge direction')
    if not status()['ready']:
        raise EnglishUnavailable(status()['setup'])
    spans = preserved_spans(text, protected_terms or [], pair)
    pieces, preserved, cursor = [], [], 0
    # Serializes first-load and caps CPU work under concurrent requests.
    with _LOCK:
        for span in spans:
            before = text[cursor:span.start()]
            translated = _translate_text(before, pair)
            if cursor and before[:1].isspace():
                pieces.append(' ')
            pieces.append(translated)
            if translated and before[-1:].isspace():
                pieces.append(' ')
            pieces.append(span.group())
            preserved.append(span.group())
            cursor = span.end()
        tail = text[cursor:]
        if pieces and tail[:1].isspace():
            pieces.append(' ')
        pieces.append(_translate_text(tail, pair))
    return {'text': re.sub(r'[ \t]+', ' ', ''.join(pieces)).strip(), 'preserved_terms': preserved,
            'segmented_for_preservation': bool(spans)}
