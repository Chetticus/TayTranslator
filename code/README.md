# Tày → Vietnamese Translator

A dictionary-grounded translation system for **Tày**, a Tai-Kadai language spoken by
roughly 1.8 million people in northern Vietnam. This implementation uses a
digitised Vietnamese–Tày–Nùng dictionary. Other translation tools exist; claims
of superiority require an independent comparison (see ../COMPARISON.md).

This system turns that dictionary into a working translator by combining
**lexical lookup** with **retrieval of similar example sentences**.

---

## Quick start

```bash
python -m venv venv
venv\Scripts\activate
pip install -r code/requirements-dev.txt
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
[1] Normalize         Unicode NFC and whitespace; retain user content
   ↓
[2] Retrieve           find the 2 most similar Tày sentences among 14,179
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

**Tày → Việt** (the harder direction: the dictionary must be inverted)

| Arm | chrF | token-F1 | Exact |
|---|---|---|---|
| Original code (before fixes) | 0.104 | 0.077 | 0.0% |
| Lookup only | 0.428 | 0.527 | 15.4% |
| **Lookup + context + Viterbi + mined phrases** | **0.441** | **0.544** | **16.2%** |

**Việt → Tày** (the dictionary's native direction)

| Arm | chrF | token-F1 | Exact |
|---|---|---|---|
| **Lookup + Viterbi + mined phrases** | **0.471** | **0.579** | **18.2%** |
| + retrieved-context sense selection | 0.463 | 0.574 | 16.2% |

### Multiple reference translations

Scoring against a single reference is unfairly harsh. "lời nói bóng bẩy" scores
0.43 against "Câu văn bóng bẩy" despite being a defensible translation of the
same Tày sentence.

The corpus already contains several Vietnamese renderings for some Tày sentences,
so `build_reference_map()` collects them and scoring takes the best match across
all of them — a standard multi-reference setup requiring no manual annotation.
39 of 500 Tày→Việt test sentences have more than one valid reference (11 of 500
in the other direction).

This raised Tày→Việt from 0.427 to **0.441**. It *lowered* Việt→Tày from 0.481 to
**0.471**, and that decrease is a correction rather than a regression: holding out
a test sentence now removes **every** Vietnamese rendering of it from the language
model, alignment model and phrase table. Previously an alternate rendering could
remain in training, which is the same leakage this project has now caught three
times.

### Where the remaining error is

Failure modes on 400 held-out sentences:

| Mode | Share |
|---|---|
| **Wrong sense chosen** | **49.2%** |
| Mostly wrong | 35.8% |
| Exactly right | 14.0% |
| Right words, wrong order | 0.8% |
| Word missing from dictionary | 0.2% |

Word order and coverage are effectively solved. Roughly 85% of remaining error is
choosing the wrong meaning — which is why five separate disambiguation signals
were tried, and why they all saturate: the information needed to choose is not
present in a dictionary whose examples show words in isolation rather than in
discourse context.

```bash
python eval_translation.py --n 500 --direction vi2tay
```

Việt→Tày scores materially higher, which is expected: each Vietnamese headword
has only a few Tày glosses, whereas inverting the dictionary makes almost every
Tày word ambiguous.

The reversal on the second row is the interesting part — **retrieved context
*hurts* the native direction**. When lookup is already unambiguous, context only
adds noise, so the API skips retrieval for `vi2tay`. Same redundancy pattern seen
with the LLM, the language model and the alignment model.

### Mined phrase table

Many Tày compounds do not decompose: `mẻn slua` means "thất bại" as a unit, so
word-by-word assembly produces "ăn thua". `translation_api/phrases.py` recovers
these by **phrase extraction from word alignments** — the standard statistical MT
technique. It uses the IBM Model 1 alignment to link words, then keeps every
contiguous span pair consistent with that alignment and seen at least twice.

1,170 Tày phrases extracted, and they are real non-decomposable compounds:

| Tày phrase | Vietnamese | seen |
|---|---|---|
| `kin phuối` | ăn nói | 62 |
| `slửa khóa` | quần áo | 60 |
| `tua cần` | con người | 42 |
| `rườn lảng` | nhà cửa | 31 |
| `khen kha` | chân tay | 22 |

This was the largest single gain after the original data-layer repair:
**chrF 0.400 → 0.423**. Thresholds were swept rather than guessed (minimum count
1→0.4199, **2→0.4235**, 3→0.4208, 5→0.4134). Mined phrases score 18, deliberately
below the 20 given to verbatim dictionary examples: mined phrases are *inferred*,
dictionary examples are *attested*, so attested evidence wins ties.

Note this gives the alignment model a real job even though it is disabled for
sense scoring — it turned out to be the wrong tool for ranking senses and the
right tool for finding phrases.

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

### Learned translation probabilities (IBM Model 1)

`translation_api/align.py` trains IBM Model 1 with Expectation-Maximization on
the 14,179 sentence pairs, learning P(vietnamese | tày) from data rather than
from hand-designed frequency rules. Six iterations, ~3 seconds, CPU only.

The learned probabilities are visibly better than the heuristic they replace:

| Tày | learned by EM | hand-tuned heuristic |
|---|---|---|
| `mẻ` | **mẹ** (0.71), vợ (0.10), bà (0.09) | "cái" ✗ |
| `slương` | **thương** (0.25) | "bộ" ✗ |
| `pỏ` | **bố** (0.37), cha (0.32) | "ba" |
| `cáy` | gà (0.97) | gà |
| `nặm` | nước (1.00) | nước |

But end-to-end it does not help, and the reason is informative:

| | chrF | token-F1 |
|---|---|---|
| **with** retrieved context, alignment off | **0.4003** | 0.5082 |
| with retrieved context, alignment on | 0.3923 | 0.5083 |
| **without** context, alignment off | 0.3857 | 0.4863 |
| without context, alignment on | 0.3867 | **0.5034** |

Without context the learned model beats the hand-tuned rule (+0.017 token-F1),
confirming it does its job. With context present it adds nothing and costs chrF —
the two signals fix the same errors. Disabled by default (`ALIGN_MODEL=1` to
enable). Its training data is held out during evaluation, exactly like the LM.

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

### Calibration: validated, not asserted

`calibration_report.py` checks whether reported confidence tracks real quality on
held-out data, and writes `calibration.svg`.

The first attempt **failed this check**. Confidence separated `high` from
`medium` by whether any multi-word phrase matched — a signal whose correlation
with chrF measures **−0.010**, i.e. none. The two buckets were indistinguishable:

| | old rule | **current rule** |
|---|---|---|
| high | 0.405 (n=324) | **0.632** (n=94) |
| medium | 0.403 (n=154) | 0.453 (n=260) |
| low | 0.307 (n=22) | 0.289 (n=146) |
| high − low | +0.098 | **+0.343** |

Feature correlations with chrF, measured on 500 held-out sentences:

| feature | correlation |
|---|---|
| ambiguous-span fraction | **−0.234** |
| weak-match fraction | −0.155 |
| context-chosen fraction | +0.092 |
| coverage | +0.027 |
| phrase fraction *(old signal)* | −0.010 |

Confidence is now `risk = 0.6 × ambiguity + 0.4 × weak_matches`, and the buckets
separate monotonically on both chrF and token-F1. A test enforces this.

Note that coverage is nearly useless as a discriminator here: 497 of 500 held-out
sentences score 100% coverage, including ones translated badly. Coverage answers
"did I find these words", not "did I pick the right meanings".

### Calibration guards

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
| `ALIGN_MODEL` | `0` | Learned IBM Model 1 translation probabilities |
| `ALIGN_WEIGHT` | `0.60` | Weight on learned probabilities when enabled |
| `MINED_PHRASES` | `1` | Phrase table extracted from word alignments |
| `MINED_PHRASE_SCORE` | `18.0` | Rank of mined phrases (below attested examples at 20) |
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

Every module here is used by the running application or its evaluation. Earlier
work has been removed rather than left lying around; it remains in git history if
anyone wants to see it.

Removed, and why:

- `translation_api/{main,main_simple}.py` — a second FastAPI app querying three
  SQLite databases that were never populated, so it returned nothing
- `translation_api/rag.py` — despite the name, `fetch_examples()` never received
  the query and returned random rows; superseded by `retriever.py`
- `translation_api/{offline_translate,nlp_gpt,tts}.py` — an unreferenced duplicate
  matcher, an unused OpenAI path, and a text-to-speech helper never wired to
  anything (and Vietnamese-only, so of no use for Tày output)
- `pdf_to_dictionary/`, `speech_to_corpus/` — ingestion pipelines that were never
  successfully run. The PDF parser assumed one entry per line, which the
  multi-column scan does not satisfy; the speech pipeline asked a model to invent
  Vietnamese for Tày audio it could not understand and wrote the guesses to the
  corpus as if they were data
- The old test files, which asserted return *types* and stayed green while the
  system could not translate anything
- `tay_viet_system_diagram.png` — depicted an architecture the project no longer
  has; see the diagram in [TECHNICAL.md](../TECHNICAL.md) instead
- `simple_code/`, `api_example/` — earlier Vietnamese→Tày prototypes on the OpenAI
  Assistants API. Neither is runnable: `simple_code/` depends on file IDs from an
  account it cannot access, and its prompt contains reversed Tày mappings
  (gà/vịt swapped). Shipping broken code carrying incorrect linguistic data
  would be worse than describing the approach in prose.
