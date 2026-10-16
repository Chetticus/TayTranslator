import copy
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from translation_api import english_bridge as bridge


@pytest.fixture
def fake_bridge(monkeypatch):
    monkeypatch.setattr(bridge, 'status', lambda: {'ready':True})
    monkeypatch.setattr(bridge, '_translate_text', lambda text, pair: text.strip().lower())


def test_name_and_literals_preserved(fake_bridge):
    result = bridge.translate('My name is Nguyen Hai Nam. Email me at Nam@example.com on 12/10/2026.', 'en_vi')
    assert 'Nguyen Hai Nam' in result['text']
    assert 'Nam@example.com' in result['text']
    assert '12/10/2026' in result['text']


def test_spaces_between_multiple_protected_values(fake_bridge):
    result = bridge.translate('Alice AND Bob.', 'en_vi', ['Alice','Bob'])
    assert result['text'] == 'Alice and Bob.'


def test_unknown_markers_not_reinterpreted(fake_bridge):
    assert bridge.translate('word [ZZZX] word', 'vi_en')['text'] == 'word [ZZZX] word'


def test_missing_model_returns_explicit_503(monkeypatch):
    monkeypatch.setattr(bridge, 'status', lambda: {'ready':False, 'setup':'Install model'})
    with pytest.raises(HTTPException) as caught:
        main.translate(main.ChatIn(message='Hello', direction='en2tay'))
    assert caught.value.status_code == 503


@pytest.mark.parametrize('direction', ['en2tay','tay2en'])
def test_pivot_routing_and_honest_metadata(monkeypatch, direction):
    calls = []
    monkeypatch.setattr(bridge, 'status', lambda: {'ready':True})
    def neural(text, pair, terms):
        calls.append(pair)
        return {'text':'xin chào' if pair=='en_vi' else 'hello', 'preserved_terms':[], 'segmented_for_preservation':False}
    monkeypatch.setattr(bridge, 'translate', neural)
    def dictionary(payload, allow_llm):
        calls.append(payload.direction)
        assert allow_llm is False
        return {'reply':'TAY' if payload.direction=='vi2tay' else 'xin chào', 'glossary':[], 'meta':{'confidence':'high','coverage':1}}
    monkeypatch.setattr(main, '_translate_dictionary', dictionary)
    result = main.translate(main.ChatIn(message='input', direction=direction))
    assert calls == (['en_vi','vi2tay'] if direction=='en2tay' else ['tay2vi','vi_en'])
    assert result['meta']['confidence'] == 'low'
    assert result['meta']['pivot_text'] == 'xin chào'
    assert result['meta']['direction'] == direction


def test_model_tokens_are_not_silently_truncated(monkeypatch):
    class Tokenizer:
        def encode(self, *args, **kwargs): return ['x'] * 401
    monkeypatch.setattr(bridge, '_load', lambda pair: (None, Tokenizer(), ''))
    with pytest.raises(bridge.EnglishInputError, match='400'):
        bridge._translate_text('long input', 'en_vi')


def test_argos_space_markers_are_removed(monkeypatch):
    class Tokenizer:
        def encode(self, *args, **kwargs): return ['Hello']
        def decode(self, pieces): return '▁Xin▁chào'
    class Translator:
        def translate_batch(self, *args, **kwargs):
            class Result: hypotheses = [['▁Xin','▁chào']]
            return [Result()]
    monkeypatch.setattr(bridge, '_load', lambda pair: (Translator(), Tokenizer(), ''))
    assert bridge._translate_text('Hello', 'en_vi') == 'Xin chào'


@pytest.mark.skipif(not bridge.status()['ready'], reason='Optional local English models not installed')
def test_real_local_models_smoke():
    for text, pair in [('Hello, I drink water.', 'en_vi'), ('Tôi uống nước.', 'vi_en')]:
        result = bridge.translate(text, pair)
        assert result['text'] and result['text'] != text
        assert '▁' not in result['text']
