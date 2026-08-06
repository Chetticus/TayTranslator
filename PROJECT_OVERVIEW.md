# Tày → Vietnamese Translator

A working translation system for **Tày**, a Tai-Kadai language spoken by roughly
1.8 million people in northern Vietnam, built from a single digitised dictionary
and evaluated with a held-out test methodology.

---

## 1. The problem

Tày is effectively invisible to modern NLP:

- No machine translation system supports it
- Whisper (speech recognition) has no Tày language code
- No pretrained language model has meaningful Tày competence
- The only substantial digital resource is one Vietnamese→Tày–Nùng dictionary

Standard approaches don't apply. There is no parallel corpus to train on and no
Tày-capable model to start from. Everything the system knows has to be extracted
from one dictionary — and the system has to be honest about the limits that
imposes.

A second constraint makes it harder. The dictionary runs **Vietnamese → Tày**,
but the tool translates **Tày → Vietnamese**. Inverting a bilingual dictionary
makes almost every word ambiguous: the Tày word `mẻ` is the listed translation of
*mẹ, vợ, cái, gái, bà, nái, đẻ* and more. Choosing correctly requires context.

---

## 2. What the system does

A local web application. You type or speak Tày; it returns Vietnamese together
with a full account of how confident it is and why.

```
Tày input
   ↓
[1] Preprocess       clean dictionary artefacts and mixed-format input
   ↓
[2] Retrieve         2 most similar Tày sentences from 14,179 aligned pairs
                     (IDF-weighted token overlap + character 3-grams)
   ↓
[3] Lexical match    longest-phrase-first over 26,436 entries; tone-sensitive,
                     with tone-insensitive and edit-distance fallback layers
   ↓
[4] Sense selection  score each candidate meaning by retrieved evidence,
                     weighted by how similar the retrieved sentence is
   ↓
[5] Viterbi decoding choose the whole SEQUENCE of meanings, balancing dictionary
                     score against a bigram model of Vietnamese fluency
   ↓
[6] LLM edit         OPTIONAL — disabled by default, on measured evidence
   ↓
Vietnamese + coverage + confidence + glossary + retrieved evidence
```

**Steps 4 and 5 are the core ideas.** Steps 2 and 4 make this retrieval-augmented
rather than a lookup table: the retrieved sentences don't decorate the output,
they decide which sense wins. Seeing `ớ, mé mà dá! → ha, mẹ đã về` is what makes
`mẻ` resolve to "mẹ" rather than the statistically more common "cái".

Step 5 makes the choices interact. Before it, each phrase picked its sense in
isolation — every word individually defensible, the sentence as a whole nonsense.
Viterbi decoding over a Vietnamese bigram model fixes cases like `te pây dá lò?`,
which the decoder resolves to "nó đi rồi à" (the reference translation) by
preferring `dá → rồi` over the individually higher-scoring `dá → đã`.

### Data built from the dictionary

| Asset | Size |
|---|---|
| Source dictionary rows parsed | 18,788 |
| Lookup index entries | 26,436 (2,903 single-word, 23,533 multi-word) |
| Aligned Tày–Vietnamese sentence pairs | 14,179 |
| Index build time | ~2 s once, then ~2 ms per query |

### Interface

A single-page web app (vanilla JavaScript, no build step) that shows, for every
translation: a confidence badge, a coverage bar, the retrieved sentences with
similarity scores, and a word-by-word table marking which senses were chosen by
context and which words could not be translated at all.

Speech input runs through Whisper. Since Whisper has no Tày code, it is invoked
as Vietnamese with a Tày-orthography prompt — a documented workaround, not a
solution.

---

## 3. Results

Measured on **500 held-out sentences**, removed from the index before scoring so
the system must compose translations as it would for genuinely new input.

| Stage | chrF | token-F1 | Exact match |
|---|---|---|---|
| Early version | 0.104 | 0.077 | 0.0% |
| Repaired lexical layer | 0.369 | 0.479 | 10.8% |
| + retrieval-based sense selection | 0.386 | 0.486 | 12.4% |
| **+ Viterbi decoding with a Vietnamese LM** | **0.400** | **0.508** | **13.0%** |

Token coverage on unseen sentences: **99.9%**.

Published machine translation for low-resource languages at this data scale
typically reports chrF in the 0.30–0.50 range, so this sits inside the normal
band — while being built from a single dictionary rather than a parallel corpus.

**Metrics used:** chrF (character n-gram F-score, standard for low-resource MT),
token-F1, and exact match. Character-level scoring is used because word-level
metrics like BLEU are unstable on short sentences and rich morphology.

---

## 4. Evaluation methodology

An early version of the test harness reported **93.7% coverage**. That number was
wrong, and finding out why drove most of the engineering that followed.

The test set had been extracted from the same spreadsheet the lookup index was
built from — **61.6% of test lines were verbatim index keys**. The system was
being asked to retrieve values it had just stored. A further ~18% of the reported
"coverage" was untranslated Tày echoed back and counted as success.

Real performance on genuinely unseen input was **chrF 0.104**.

`eval_translation.py` replaces this. It removes every test sentence from **both**
index layers before scoring, and blocks the retrieval stage from returning the
gold answer — including near-duplicates that differ only in formatting.

```bash
python eval_translation.py --n 500          # lexical layers, fast
python eval_translation.py --n 80 --llm     # adds the two LLM arms
```

---

## 5. Engineering decisions, and the evidence behind them

Nine findings, most of them *against* intuition, because measurement
contradicted expectation.

### 5.1 Local language models lose to deterministic lookup

The design assumed an LLM would clean up dictionary output. Two models were
tested across four configurations on the same held-out set and seed (n=80):

| Arm | chrF | token-F1 | Exact |
|---|---|---|---|
| Lookup only | 0.388 | 0.474 | 13.8% |
| **Lookup + context** | **0.393** | **0.494** | **15.0%** |
| + `gemma3:4b` | 0.366 | 0.435 | 11.2% |
| + `gemma3:4b` with retrieved examples | 0.361 | 0.462 | 6.2% |
| + `qwen2.5:7b-instruct` | 0.371 | 0.454 | 12.5% |
| + `qwen2.5:7b-instruct` with retrieved examples | 0.375 | 0.472 | 13.8% |

Scaling the model helps, and the direction is the interesting part:

| | 4B | 7B |
|---|---|---|
| LLM alone | 0.366 | 0.371 |
| LLM + retrieval | 0.361 | **0.375** |
| Retrieval helps the model? | **No** (−0.005) | **Yes** (+0.004) |

At 4B the model is too weak to exploit retrieved examples — they actively hurt.
At 7B it begins to benefit. But doubling model size bought ~0.014 chrF and it
needs ~0.018 more just to break even with the dictionary. The 7B ran fully
GPU-resident (4.9 GB of 8 GB VRAM, 100% utilisation), so this is not an
offloading or quantisation artefact.

The model does sometimes win — `hăn chèn lẻ tha đăm` improved from "nghe tiền là
phàm" (chrF 0.15) to "Nhìn thấy tiền là phàm" (0.39) using retrieved context. It
simply loses more often than it wins, and still produces artefacts (one output
began with the English word "Look").

**Decision:** the LLM stage is gated behind `USE_LLM=1`, off by default, with the
benchmark it must beat recorded in the code. The stage remains fully wired.

**The finding is itself a result:** for this language pair and data scale, a
well-constructed retrieval-and-lookup system outperforms local generative models
up to 7B — supported by 8 measured configurations rather than assumption.

### 5.2 A component that learns from the corpus must be held out too

Adding the Vietnamese language model made chrF jump **0.395 → 0.548**. That
result was false. The LM had been estimated from *all* example sentences —
including the held-out targets — so Viterbi was reconstructing memorised answers
rather than translating. One output scored chrF 0.85 by near-verbatim recall.

`eval_translation.py` now rebuilds the LM with the test targets excluded before
scoring. The honest gain is **+0.005**, not +0.15.

This is the same failure as the original 93.7% figure, appearing in a new
component. Removing test sentences from the lookup index is not sufficient once
any part of the system learns statistics from the corpus.

### 5.3 The language model and retrieved context are redundant

| `LM_WEIGHT` | chrF *with* context | chrF *without* context |
|---|---|---|
| 0.00 | 0.3954 | 0.3688 |
| **0.10** | **0.4003** | 0.3857 |
| 0.35 | 0.3974 | **0.3955** |
| 1.00 | 0.3930 | 0.3918 |

Both signals fix largely the same errors. Without context the LM must carry the
load (best weight 0.35); with context present it only needs a light touch (0.10),
and weighting it harder damages phrases that were already correct.

### 5.4 Fewer retrieved examples beat more

| K | 1 | **2** | 3 | 5 | 8 | 20 |
|---|---|---|---|---|---|---|
| chrF | 0.390 | **0.399** | 0.393 | 0.387 | 0.378 | 0.376 |

Retrieval depth was swept rather than guessed. More retrieved sentences means
more irrelevant evidence pushing wrong senses — consistent with the finding
below that pooled evidence is actively harmful.

### 5.5 A learned model beat the hand-written rule — and still didn't help

`translation_api/align.py` trains **IBM Model 1 with Expectation-Maximization**
on the 14,179 sentence pairs, learning P(vietnamese | tày) from data instead of
from hand-designed frequency rules. The task is unsupervised: the algorithm knows
which *sentences* correspond but not which *words*, and recovers the word-level
correspondences by iterating. Six iterations, ~3 seconds, CPU only.

What it learned is markedly better than the rule it was written to replace:

| Tày | learned by EM | hand-tuned heuristic |
|---|---|---|
| `mẻ` | **mẹ** (0.71) | "cái" ✗ |
| `slương` | **thương** (0.25) | "bộ" ✗ |
| `pỏ` | **bố** (0.37), cha (0.32) | "ba" |
| `cáy` | gà (0.97) | gà |

End-to-end, though:

| | chrF | token-F1 |
|---|---|---|
| **with** retrieved context, alignment off | **0.4003** | 0.5082 |
| with retrieved context, alignment on | 0.3923 | 0.5083 |
| **without** context, alignment off | 0.3857 | 0.4863 |
| without context, alignment on | 0.3867 | **0.5034** |

Without context it beats the hand-tuned rule by +0.017 token-F1, confirming it
works. With context present it adds nothing and costs chrF. Disabled by default.

This is the third component to fail the same way — a real signal, redundant with
retrieved context. It suggests context-based disambiguation is close to
saturating what this dictionary can support, and that further gains need more
data rather than better scoring of the data already there.

### 5.6 Calibration had to be validated before it could be believed

The claim "the system knows when it doesn't know" was asserted for some time
before being checked. When checked, it **failed**.

Confidence separated `high` from `medium` by whether any multi-word phrase had
matched. Measured against held-out chrF, that signal correlates **−0.010** — it
carries no information, and the two buckets were indistinguishable (0.405 vs
0.403; `medium` actually scored *higher* on token-F1).

Correlation of observable signals with chrF, 500 held-out sentences:

| feature | correlation |
|---|---|
| ambiguous-span fraction | **−0.234** |
| weak-match fraction | −0.155 |
| context-chosen fraction | +0.092 |
| coverage | +0.027 |
| phrase fraction *(the signal in use)* | −0.010 |

Rebuilt as `risk = 0.6 × ambiguity + 0.4 × weak_matches`:

| | old | **new** |
|---|---|---|
| high | 0.405 | **0.574** |
| medium | 0.403 | 0.438 |
| low | 0.307 | 0.310 |
| high − low | +0.098 | **+0.264** |

Now monotonic on chrF *and* token-F1, enforced by a test. `calibration_report.py`
regenerates the figure.

Worth noting separately: **coverage barely discriminates at all.** 497 of 500
held-out sentences report 100% coverage, including badly translated ones.
Coverage answers "did I find these words", not "did I choose the right meanings"
— which is why the ambiguity signal matters more.

### 5.7 Pooled context is worse than no context

Sense selection was tested with two kinds of evidence: **targeted** (only example
sentences genuinely containing the word being disambiguated) and **pooled** (any
word appearing anywhere in the 5 retrieved sentences).

| targeted | pooled | chrF |
|---|---|---|
| off | off | 0.3691 |
| off | on | **0.3677** ← worse than no context at all |
| on | off | 0.3855 |
| **on** | **weak (0.5)** | **0.3868** |

Pooled evidence is *harmful* — a retrieved sentence about chickens pushes the
wrong sense onto an unrelated word. All the gain comes from per-word targeted
evidence, which is why `_evidence_for()` filters by word rather than by sentence.

### 5.8 Fuzzy matching fixes coverage, not accuracy

| Corruption | | coverage | unknown/sentence | chrF |
|---|---|---|---|---|
| dropped character | off → on | 0.932 → **0.993** | 0.22 → **0.03** | 0.2972 → 0.2957 |
| swapped characters | off → on | 0.886 → **0.973** | 0.37 → **0.09** | 0.3076 → 0.3061 |
| missing tone marks | off → on | 0.995 → 0.999 | 0.02 → 0.01 | 0.3303 → 0.3299 |

Fuzzy matching reliably converts unknowns into guesses, but the guesses are about
as wrong as the gaps they replace — chrF drifts slightly *down*. It is kept on
because a flagged low-confidence guess helps a learner more than `[unknown]`, and
every fuzzy match is labelled as such in the interface. It is not claimed as an
accuracy improvement. Missing tone marks need no fuzzy matching at all: the
tone-insensitive index layer already covers the most common typing error.

### 5.9 Calibration guards

The original failure wasn't just poor translation — it was **confident** poor
translation. Untranslated Tày scored 100% coverage and "high confidence", which
told the pipeline to lock the output in. Three guards now prevent this:

1. Words kept only because they *look* Vietnamese are counted separately and
   never inflate coverage.
2. If more than half a sentence relies on tone-insensitive or fuzzy matches,
   confidence is capped at low.
3. Input with no tone marks is capped at low confidence regardless of coverage.

Guard 3 catches a genuinely subtle failure: `khoi pay thieo` typed without
diacritics matches real but *different* Tày words **exactly**, producing "hòa mèm
thêu" at 100% coverage. No source-level heuristic detects this — only noticing
that the input itself is under-specified.

| Input | Output | Coverage | Confidence |
|---|---|---|---|
| `ỏ mẻ mà dá` | a mẹ đã về ✓ | 1.00 | high |
| `kin khẩu` | ăn cơm ✓ | 1.00 | high |
| `ruơn` (tone dropped) | nhà ✓ | 1.00 | low |
| `khoi pay thieo` (no tones) | hòa mèm thêu ✗ | 1.00 | **low** + warning |

---

## 6. Honest limitations

- **Fine-grained sense disambiguation is the ceiling.** For `mẻn slua khôm phêt`
  ("Thất bại cay đắng"), the correct answer *"cay đắng"* **was present in the
  candidate list** — ranked third among three tied options, with retrieved
  context pointing at two other legitimate-but-wrong senses. Coverage is not the
  problem; choosing between near-synonyms is.
- **Word order is not modelled.** Output follows source order.
- **Speech input is a workaround**, and transcripts are rough.
- **No Tày speech output.** Text-to-speech is Vietnamese only.
- **Evaluation data comes from one dictionary**, skewing toward short idiomatic
  phrases rather than natural conversation.
- **One reference translation per sentence**, so chrF understates acceptable
  paraphrases.
- **Learned components exist but one is disabled.** The Vietnamese bigram model is
  active; the IBM Model 1 alignment model is trained and tested but off by
  default, being redundant with retrieved context.

---

## 7. Configuration

| Variable | Default | Purpose |
|---|---|---|
| `EXCEL_GLOSSARY_PATH` | `../tu_dien_viet_tay_nung_parsed.xlsx` | Dictionary source |
| `USE_LLM` | `0` | Enable the Ollama editing pass |
| `RETRIEVE_K` | `5` | Example sentences retrieved per query |
| `FUZZY_MATCH` | `1` | Edit-distance fallback for misspellings |
| `LOW_COVERAGE_THRESHOLD` | `0.35` | Below this, skip the LLM entirely |
| `HIGH_COVERAGE_THRESHOLD` | `0.70` | Above this, LLM may only copy-edit |
| `WHISPER_STT_MODEL` | `base` | Speech-to-text model |

The application runs **fully offline**. Ollama is not required while `USE_LLM=0`.

---

## 8. Running it

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cd code
uvicorn main:app --port 8000
```

Open <http://127.0.0.1:8000/>; check `/api/health` to confirm the dictionary
loaded.

---

## 9. Code map

| Path | Role |
|---|---|
| `code/main.py` | FastAPI app, pipeline orchestration, confidence calibration |
| `code/translation_api/excel_glossary.py` | Index construction, matching, sense selection |
| `code/translation_api/retriever.py` | Similar-sentence retrieval |
| `code/translation_api/tay_input_preprocess.py` | Input cleaning |
| `code/translation_api/stt.py` | Whisper speech-to-text |
| `code/templates/tay_chat.html` | Web interface |
| `code/eval_translation.py` | Held-out evaluation harness |

Superseded modules retained for reference are listed in `code/README.md`.

