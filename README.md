# Tày → Vietnamese Translator

A translation system for **Tày**, a Tai-Kadai language spoken by roughly 1.8
million people in northern Vietnam, built from a single digitised dictionary and
evaluated on held-out data.

This implementation derives its translation resources from one Vietnamese→Tày
dictionary and combines lexical lookup with sentence retrieval and statistical
decoding. Other public tools exist, including taynung.com; this project does not
claim to be the first or to outperform them. Independent speaker evaluation is
pending. See [the comparison protocol](COMPARISON.md).

---

## Results

Historical development measurements on **500 held-out dictionary sentences**,
removed from the index before scoring. These are not native-speaker accuracy
scores, not a comparison against taynung.com, and not a fresh measurement of the
current working tree. See [pre-verification readiness](PRE_VERIFICATION.md).

**Tày → Việt** — the harder direction, since the dictionary must be inverted:

| Stage | chrF | token-F1 | Exact |
|---|---|---|---|
| Early version | 0.104 | 0.077 | 0.0% |
| Repaired lexical layer | 0.369 | 0.479 | 10.8% |
| + retrieval-based sense selection | 0.386 | 0.486 | 12.4% |
| + Viterbi decoding with a Vietnamese LM | 0.400 | 0.508 | 13.0% |
| + phrase table mined from word alignments | 0.427 | 0.532 | 14.4% |
| **+ multi-reference scoring** | **0.441** | **0.544** | **16.2%** |

**Việt → Tày** — the dictionary's native direction, and materially easier:

| Stage | chrF | token-F1 | Exact |
|---|---|---|---|
| **Lookup + Viterbi + mined phrases** | **0.471** | **0.579** | **18.2%** |

Token coverage on unseen input: **99.9%**. Published low-resource MT at this data
scale typically reports chrF 0.30–0.50.

---

## Quick start

Optional offline **English ↔ Tày**, via Vietnamese: see [English setup and limitations](ENGLISH.md).

```bash
python -m venv venv
venv\Scripts\activate
pip install -r code/requirements-dev.txt
cd code
uvicorn main:app --port 8000
```

Open <http://127.0.0.1:8000/>, or check `/api/health` to confirm the dictionary
loaded. The app runs **fully offline** — no API keys, no network.

Run the tests:

```bash
cd code
python -m pytest tests/ -v
```

### Deploy on Railway

The repository includes a root `requirements.txt`, Python version pin, and
`railpack.json`, so Railway can detect and deploy it without Docker.

1. Leave the service **Root Directory empty** so the build includes both
   `code/` and the dictionary workbook at the repository root.
2. Use Railway's **Railpack** builder. Clear any old build or start command
   overrides; the checked-in Railpack configuration installs dependencies,
   downloads the local English models during the image build, and starts the
   FastAPI server on Railway's assigned port.
3. Set the health-check path to `/api/health`.
4. Generate a public domain under **Settings → Networking**.

After deployment, open `https://YOUR-DOMAIN/api/health` and confirm that `ok`,
`dictionary_ok`, and `english.ready` are all `true`.

Reproduce the evaluation:

```bash
python code/eval_translation.py --n 500
```

---

## How it works

```
Tày input
  → clean input
  → retrieve 2 most similar sentences from 14,179 aligned pairs
  → longest-phrase-first match over a 26,436-entry index
  → pick senses using retrieved evidence, weighted by similarity
  → Viterbi-decode the whole sequence against a Vietnamese bigram model
  → optional LLM edit (off by default — it measurably hurts)
→ Vietnamese + coverage + confidence + glossary + retrieved evidence
```

The hard problem is that the dictionary runs Vietnamese→Tày while the tool
translates Tày→Vietnamese. Inverting it makes almost every word ambiguous — `mẻ`
is the listed translation of *mẹ, vợ, cái, gái, bà, nái, đẻ*. Retrieved context
and sentence-level fluency are what resolve it.

---

## Selected findings

Full detail and evidence in **[TECHNICAL.md](TECHNICAL.md)**. For a
plain-language description, see **[OVERVIEW.md](OVERVIEW.md)**.

- **Local LLMs lose to deterministic lookup.** Both `gemma3:4b` and
  `qwen2.5:7b-instruct` scored *below* the dictionary layer across 8 measured
  configurations. The LLM stage is wired but disabled by default.
- **Evaluation leakage, caught twice.** An early harness reported 93.7% coverage
  for a system that could not translate a single unseen word — the test set had
  been drawn from the training data. Later, adding a language model appeared to
  jump chrF 0.395 → 0.548, which turned out to be the LM having memorised the
  held-out targets. Any component that learns from the corpus has to be held out,
  not just the index.
- **Fewer retrieved examples beat more** (K=2 > K=5 > K=20), and pooled context
  is *worse than no context at all*. Retrieved context even *hurts* the
  Việt→Tày direction, where lookup is already unambiguous — the same redundancy
  pattern that ruled out the LLM and the learned alignment model.
- **A learned model can be right and still not help.** IBM Model 1 trained with
  EM recovers better word translations than the hand-written rule (`mẻ` → mẹ at
  0.71, where the heuristic chose "cái"), but adds nothing on top of retrieved
  context. It found its real use elsewhere: mining the phrase table.
- **Nearly all remaining error is sense selection.** On 400 held-out sentences:
  49% wrong sense, 36% mostly wrong, 14% exactly right — but only **0.8%** are
  right-words-wrong-order and **0.2%** have a word missing from the dictionary.
  Word order and coverage are solved; meaning is not.
- **Calibration matters more than the score.** The system caps confidence when it
  is relying on guesses — including for input typed without tone marks, which
  matches real but different Tày words and produces confident nonsense.

---

## Repository

| Path | Contents |
|---|---|
| **[OVERVIEW.md](OVERVIEW.md)** | Plain-language description — start here if you don't code |
| **[TECHNICAL.md](TECHNICAL.md)** | Architecture, methodology, all nine measured findings |
| [HOW_TRANSLATION_WORKS.md](HOW_TRANSLATION_WORKS.md) | Step-by-step input-to-output explanation, English bridge, and demo guide |
| [code/README.md](code/README.md) | Runtime detail, configuration, full benchmark tables |
| [DATA.md](DATA.md) | Data provenance and licensing |
| `code/` | Application, retrieval, decoding, evaluation harness, tests |

---

## Development notes

Built with substantial AI assistance (Claude). The data-layer repair, retrieval
layer, language-model decoder, evaluation harness and interface were developed in
collaboration with an AI coding assistant; the direction, experimental decisions
and interpretation of results are my own.

Source dictionary scans are excluded from this repository — see
[DATA.md](DATA.md). The MIT licence covers the code only, not the dictionary
content.
