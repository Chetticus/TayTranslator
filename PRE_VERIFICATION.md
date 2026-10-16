# Before speaker verification

## Latest local checks — October 13, 2026

- `scripts/verify.ps1`: **88 Python tests passed**, **3 JavaScript interaction tests
  passed**, and `git diff --check` passed. Chat-page JavaScript syntax also checked.
- Local API readiness reported true. Lowercase name preservation, punctuation-only
  input, explicit preservation and HTTP 422 on invalid direction were smoke-tested.
- All 13 local diagnostic requests returned outputs, saved with a version manifest
  in ignored `code/benchmark_runs/preverification-local.jsonl`. This is response
  availability, **not 100% accuracy**. No competitor requests were made for this run.
- Browser visual QA has not been completed. No public deployment or new training run.

## Implemented, mechanically testable

- NFC Unicode lookup, retained punctuation and literal values (URLs, email, dates,
  emoji, codes); phrase lookup cannot cross a protected span or punctuation boundary.
- Name-introduction heuristic for Vietnamese family names, including lowercase input.
  It is bounded and stops at common conjunctions/verbs, **not general named-entity
  recognition**. Ambiguous names need `protected_terms`; the UI exposes this override.
- Both translation directions accept explicit keep-unchanged phrases. Preserved tokens
  remain separate from dictionary coverage, not counted as successfully translated.
- API limits: 2,000 characters, 200 whitespace-delimited words, validated direction,
  up to 20 protected phrases of at most 100 characters; empty/control-character input
  rejected. Old clients passing `direction: null` must omit it or use a valid value.
- Unknown-input logging is off by default. `LOG_UNKNOWN_TERMS=1` explicitly enables
  raw-text collection; obtain consent and define retention before using it. This does
  not delete previously collected files. The chat UI still keeps browser-local history.
- Optional forward-only LLM editor is bypassed for reverse direction and protected
  content. Confidence remains a heuristic, **not a calibrated probability**.
- Benchmark runs record source, dictionary, lexicon, runtime and selected configuration
  fingerprints. Resume rejects changed configuration or legacy unversioned runs. Restart
  the server after source/data changes; do not alter an engine during a benchmark.
- Blinded review exports/imports and validated aggregation; a preflight tool rejects
  unreviewed/uncleared training rows, duplicates and normalized held-out overlap.

## Run locally

From the repository root (Python 3.12 tested):

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r code/requirements-dev.txt
.venv/Scripts/python.exe -m uvicorn main:app --app-dir code --host 127.0.0.1 --port 8000
```

Only `requirements-core.txt` is needed to serve text translation. The original
`requirements.txt` additionally includes speech dependencies. No model download or
external API key is needed for text mode. Run `./scripts/verify.ps1` for Python tests,
review-page JS interaction tests (Node required) and whitespace checks. These are
mechanical/regression tests, not a claim of correctness on arbitrary Tày sentences.

Keep the existing pilot and review page unchanged: they measure the **older engine**.
After deciding a release candidate is frozen, collect into a new filename and generate
new blinded materials. Do not combine ratings of old and new outputs.

## Training preflight

`code/training_gate.py` is a validator, not a model trainer. It takes proposed training
JSONL plus frozen holdout JSONL (`direction`, `text`, as in comparison_cases.jsonl).
Supply **all** validation/test holdouts, including the diagnostic cases already examined.
Each training row must record this schema; values below are a template, not permission:

```json
{
  "id": "unique-id",
  "direction": "vi2tay",
  "source": "source sentence",
  "target": "speaker-approved translation",
  "provenance": {
    "kind": "synthetic",
    "origin": "teacher system and version / source",
    "training_allowed": false,
    "permission_evidence": ""
  },
  "reviews": []
}
```

Review entries require `reviewer_id`, `dialect`, and boolean `approved`. At least two
distinct reviewers must approve and no unresolved negative review may remain. Record
permission evidence only after obtaining it; the program checks attestations, not
their truth. Preserve earlier reviews when adjudicating; do not change votes merely
to pass this check. This conservative gate rejects even unchanged-name examples.

```powershell
.venv/Scripts/python.exe code/training_gate.py --train proposed_training.jsonl --holdout code/comparison_cases.jsonl independent_holdout.jsonl
```

Passing the gate is not evidence of translation quality, valid legal rights, or absence
of semantic near-duplicates. No teacher dataset has been approved and no new model has
been trained. Keep identifying user text out of externally collected datasets.

## Still required before claims or public release

1. Independent speakers define the dialect(s), write untouched reference examples,
   review outputs, and resolve disagreements. Extend beyond this tiny diagnostic pilot.
2. Clarify source-dictionary and teacher-output permissions; keep provenance separate
   for human, dictionary-derived and synthetic material.
3. Freeze the engine and evaluate on an independent split. Do not tune repeatedly on
   the final test set. Report coverage and meaning/fluency/error rates separately.
4. Hosting needs a chosen provider/domain, TLS, request-size/rate limits, abuse controls,
   privacy/retention decisions, and concurrency/load testing. Local validation limits
   alone are **not** public-service protection. Nothing has been deployed publicly.
5. Browser visual/accessibility QA remains outstanding where browser automation is
   unavailable. English support now uses local models via Vietnamese; it still needs
   its own evaluation because errors can compound. See [English setup](ENGLISH.md).
