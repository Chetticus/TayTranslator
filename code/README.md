# Tày → Vietnamese Translator

A dictionary-grounded translation system for **Tày**, a Tai-Kadai language spoken by
roughly 1.8 million people in northern Vietnam. Tày has no machine translation
support, no Whisper language code, and no pretrained models — the only usable
resource is a digitised Vietnamese–Tày–Nùng dictionary.

This system turns that dictionary into a working translator by combining
**lexical lookup** with **retrieval of similar example sentences**.

---

## Quick start

```bash
python -m venv venv
venv\Scripts\activate
pip install -r code/requirements.txt
cd code
uvicorn main:app --port 8000
```

Run the tests (they assert real translations, not return types):

```bash
python -m pytest tests/ -v
```

Open <http://127.0.0.1:8000/>. Check <http://127.0.0.1:8000/api/health> to confirm
the dictionary loaded.

The dictionary (`tu_dien_viet_tay_nung_parsed.xlsx`) must sit in the project root,
or set `EXCEL_GLOSSARY_PATH`.

---

## How translation works

```
Tày input
   ↓
[1] Preprocess         strip dictionary artefacts (~: markers, trailing glosses)
   ↓
[2] Retrieve           find the 5 most similar Tày sentences among 14,179
                       aligned example pairs (IDF token overlap + char 3-grams)
   ↓
[3] Lexical match      longest-phrase-first over a 26,436-entry index,
                       tone-sensitive, with a tone-insensitive fallback layer
   ↓
[4] Sense selection    a Tày word maps to many Vietnamese words; score each
                       candidate by retrieved evidence weighted by similarity
   ↓
[5] Viterbi decoding   choose the whole SEQUENCE of senses, balancing dictionary
                       score against a bigram model of Vietnamese fluency
   ↓
[6] LLM edit           OPTIONAL, off by default — see "Why the LLM is off"
   ↓
Vietnamese + coverage, confidence, glossary, retrieved evidence
```

Step 4 is what makes this more than a lookup table. The source dictionary is
Vietnamese→Tày, so **inverting it makes almost every word ambiguous**: `mẻ` is the
Tày gloss for *mẹ, vợ, cái, gái, bà, nái, đẻ…*. Frequency alone picks "cái".
Retrieved context showing `ớ, mé mà dá! → ha, mẹ đã về` picks "mẹ".

---

## Evaluation

**All accuracy numbers that predate this evaluation are invalid.** The previous
test set (`tay_test_sentences_full.txt`) was extracted from the same spreadsheet
the lookup index is built from — 61.6% of its lines were verbatim index keys. It
reported **93.7% coverage** for a system that could not translate a single unseen
word.

`eval_translation.py` fixes this by removing every test sentence from **both**
index layers before scoring, so the system must compose the translation from
word-level entries as it would for genuinely new input. Retrieval is likewise
blocked from returning the gold answer.

```bash
python eval_translation.py --n 500          # lookup layers, fast
python eval_translation.py --n 80 --llm     # adds the two LLM arms (slow)
```

Metrics are **chrF** (character n-gram F-score, standard for low-resource MT),
token-F1, and exact match.

### Results — 500 held-out sentences, no LLM

| Arm | chrF | token-F1 | Exact |
|---|---|---|---|
| Original code (before fixes) | 0.104 | 0.077 | 0.0% |
| Lookup only | 0.386 | 0.486 | 12.4% |
| **Lookup + context + Viterbi decoding** | **0.400** | **0.508** | **13.0%** |

Context changes ~660 sense decisions per 500 sentences.

### Sequence decoding with a Vietnamese language model

Sense selection originally chose each phrase **independently**, so every word was
individually defensible while the sentence was nonsense. A bigram language model
is estimated from the Vietnamese side of the corpus (5,185 unigrams / 34,251
bigrams), and Viterbi decoding picks the sequence maximising
`dictionary score + LM_WEIGHT × fluency`.

Sweep over `LM_WEIGHT` (500 held-out sentences):

| weight | chrF *with* context | chrF *without* context |
|---|---|---|
| 0.00 | 0.3954 | 0.3688 |
| **0.10** | **0.4003** | 0.3857 |
| 0.35 | 0.3974 | **0.3955** |
| 1.00 | 0.3930 | 0.3918 |

The two signals are largely **redundant** — they fix the same errors. Without
context the LM needs a heavy weight (0.35) to do the work; with context present
it only needs a nudge (0.10), and pushing harder damages phrases that were
already right. Hence the low default.

> **Methodology warning.** The first version of this measurement showed chrF
> jumping 0.395 → 0.548. That was false: the LM had been trained on *all* example
> sentences, including the held-out targets, so Viterbi was reconstructing
> memorised answers. `eval_translation.py` now rebuilds the LM with the test
> targets excluded (`lm.build(..., exclude_vi=..., lock=True)`). Any component
> learning from the corpus must be held out too — not just the lookup index.

### Retrieval depth

`RETRIEVE_K` was swept rather than guessed. **Fewer examples is better:**

| K | 1 | **2** | 3 | 5 | 8 | 20 |
|---|---|---|---|---|---|---|
| chrF | 0.390 | **0.399** | 0.393 | 0.387 | 0.378 | 0.376 |

More retrieved sentences means more irrelevant evidence pushing wrong senses —
the same effect that makes pooled evidence harmful.

### Which evidence actually helps

Sense selection was tested with two kinds of evidence: **targeted** (only example
sentences that genuinely contain the word being disambiguated) and **pooled**
(any word appearing anywhere in the 5 retrieved sentences).

| targeted | pooled | chrF |
|---|---|---|
| off | off | 0.3691 |
| off | on | **0.3677** ← worse than no context at all |
| on | off | 0.3855 |
| **on** | **weak (0.5)** | **0.3868** |

Pooled evidence alone is *harmful* — a retrieved sentence about chickens can push
the wrong sense onto an unrelated word. All of the gain comes from per-word
targeted evidence. This is why `_evidence_for()` filters by word, not by sentence.

### Results — 80 held-out sentences, two models × four arms

| Arm | chrF | token-F1 | Exact |
|---|---|---|---|
| Lookup only | 0.388 | 0.474 | 13.8% |
| **Lookup + context** | **0.393** | **0.494** | **15.0%** |
| + `gemma3:4b` (4B) | 0.366 | 0.435 | 11.2% |
| + `gemma3:4b` with retrieved examples | 0.361 | 0.462 | 6.2% |
| + `qwen2.5:7b-instruct` (7B) | 0.371 | 0.454 | 12.5% |
| + `qwen2.5:7b-instruct` with retrieved examples | 0.375 | 0.472 | 13.8% |

### Why the LLM is off by default

**Neither local model beats deterministic lookup with context-based sense
selection.** Both were tested with and without retrieved few-shot examples, on
the same held-out set and seed.

Scaling from 4B to 7B does help, and the direction is informative:

| | 4B | 7B |
|---|---|---|
| LLM alone | 0.366 | 0.371 |
| LLM + retrieval | 0.361 | **0.375** |
| Does retrieval help the model? | **No** (−0.005) | **Yes** (+0.004) |

At 4B the model is too weak to use retrieved examples — they make it worse. At 7B
it starts benefiting from them. But the gain from doubling model size was ~0.014
chrF, and it needs ~0.018 more to reach 0.393. The 7B model ran fully GPU-resident
(4.9 GB of 8 GB VRAM, 100% GPU utilisation), so this is not a quantisation or
offloading artefact.

Failure modes remain visible at 7B — one output began with the English word
"Look", and the worst case (`mẻn slua khôm phêt`) was left completely unchanged.
The model does occasionally win: `hăn chèn lẻ tha đăm` improved from "nghe tiền
là phàm" (chrF 0.15) to "Nhìn thấy tiền là phàm" (0.39) using retrieved context.
It simply loses more often than it wins.

So the LLM stage is gated behind `USE_LLM=1`, off by default. This is a
measurement-driven decision, not a preference. The stage stays fully wired:

```bash
set USE_LLM=1
python eval_translation.py --n 80 --llm
```

`resolve_ollama_model()` auto-selects the largest installed preferred model.
**Do not re-enable the LLM without re-running the benchmark** — the bar to beat
is chrF 0.393.

---

### Fuzzy matching: helps coverage, not accuracy

Fuzzy matching (bounded edit distance, last resort only) was measured against
deliberately corrupted input:

| Corruption | | coverage | unknown/sentence | chrF |
|---|---|---|---|---|
| dropped character | off → on | 0.932 → **0.993** | 0.22 → **0.03** | 0.2972 → 0.2957 |
| swapped characters | off → on | 0.886 → **0.973** | 0.37 → **0.09** | 0.3076 → 0.3061 |
| missing tone marks | off → on | 0.995 → 0.999 | 0.02 → 0.01 | 0.3303 → 0.3299 |

It reliably converts unknowns into guesses, but the guesses are about as wrong as
the gaps they replace — chrF drifts slightly *down*. It is kept on because a
flagged low-confidence guess is more useful than `[unknown]` for a learner, and
because every fuzzy match is labelled as such in the UI. Disable with
`FUZZY_MATCH=0`. Note that missing tone marks need no fuzzy matching at all — the
tone-insensitive index layer already covers the most common typing error.

### Calibration

The system must never report confidence it hasn't earned. Three guards:

1. Words kept only because they *look* Vietnamese are counted separately
   (`passthrough_tokens`) and never inflate coverage.
2. If more than half a sentence relies on tone-insensitive or fuzzy matches,
   confidence is capped at **low**.
3. **Input with no tone marks is capped at low confidence** regardless of
   coverage. This catches a genuinely nasty case: `khoi pay thieo` (undiacriticized)
   matches real but *different* Tày words exactly, producing "hòa mèm thêu" at
   100% coverage. Only input-level detection catches it.

| Input | Output | Coverage | Confidence |
|---|---|---|---|
| `ỏ mẻ mà dá` | a mẹ đã về ✓ | 1.00 | high |
| `kin khẩu` | ăn cơm ✓ | 1.00 | high |
| `ruơn` (tone dropped) | nhà ✓ | 1.00 | low |
| `khoi pay thieo` (no tones) | hòa mèm thêu ✗ | 1.00 | **low** + warning |

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `EXCEL_GLOSSARY_PATH` | `../tu_dien_viet_tay_nung_parsed.xlsx` | Dictionary source |
| `USE_LLM` | `0` | Enable the Ollama editing pass |
| `RETRIEVE_K` | `2` | Example sentences retrieved per query |
| `FUZZY_MATCH` | `1` | Edit-distance fallback for misspellings |
| `LM_DECODE` | `1` | Viterbi sequence decoding with the Vietnamese bigram LM |
| `LM_WEIGHT` | `0.10` | How much fluency outweighs dictionary score |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | *(auto)* | Override model selection |
| `LOW_COVERAGE_THRESHOLD` | `0.35` | Below this, skip the LLM entirely |
| `HIGH_COVERAGE_THRESHOLD` | `0.70` | Above this, LLM may only copy-edit |
| `WHISPER_STT_MODEL` | `base` | Speech-to-text model |

---

## Honest limitations

- **Word order is not modelled.** Output is glosses in source order. `mẻn slua
  khôm phêt` → "ăn thua khổ cực" (gold: "Thất bại cay đắng"). Fixing this needs
  a generator, and no local model tested so far helps.
- **Sense selection is still wrong often.** Context changes 732 decisions per 500
  sentences, but isolated words remain ambiguous.
- **Speech input is a hack.** Whisper has no Tày code; it runs as `language=vi`
  with a Tày-orthography prompt. Treat transcripts as rough.
- **No Tày text-to-speech.** `tts.py` uses gTTS, which speaks Vietnamese only.
- **Evaluation examples come from one dictionary**, so they skew toward short
  idiomatic phrases rather than natural conversation.

## Repository notes

Active code is `main.py`, `translation_api/{excel_glossary,retriever,tay_input_preprocess,stt}.py`,
and `eval_translation.py`.

Present but not used by the running app, kept for reference:

- `translation_api/main.py`, `main_simple.py` — a second FastAPI app that queries
  `db/*.db`; those databases were never populated, so it returns nothing
- `translation_api/rag.py` — despite the name, `fetch_examples()` never receives
  the query and returns random rows; superseded by `retriever.py`
- `translation_api/offline_translate.py` — unreferenced duplicate of the matcher
- `pdf_to_dictionary/`, `speech_to_corpus/` — ingestion pipelines that were never
  successfully run

Excluded from the repository (see `.gitignore`):

- `simple_code/`, `api_example/` — earlier Vietnamese→Tày prototypes on the
  OpenAI Assistants API. Neither is runnable: `simple_code/` depends on file IDs
  belonging to an account it cannot access, and its prompt contains reversed Tày
  mappings. Shipping broken code with incorrect linguistic data would be worse
  than describing the approach in prose.
- The empty `db/` schemas, the dictionary-derived test corpora, and the ad-hoc
  scripts that produced the discredited accuracy figures.
