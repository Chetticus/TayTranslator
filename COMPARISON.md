# Independent translator comparison

This is a small diagnostic pilot, not a representative accuracy estimate or training-data collector.
The 13 authored Vietnamese cases (10 remote-safe, three local-only) cover names, negation, questions, numbers, punctuation,
ambiguity, missing accents and literal text. Native speakers must supply independent
reference translations, specify their dialect, and add Tày-to-Vietnamese cases.

From the repository root, with the local server running:

```powershell
.venv/Scripts/python.exe code/compare_translators.py collect --remote --out code/benchmark_runs/pilot.jsonl
.venv/Scripts/python.exe code/compare_translators.py blind --results code/benchmark_runs/pilot.jsonl --out code/benchmark_runs/review.jsonl --key code/benchmark_runs/private_key.jsonl
```

Remote requests are explicit, spaced at least three seconds apart, capped at 50 cases,
and stopped on any remote HTTP/response error. Existing case hashes are skipped on rerun,
including failed cases: use a new output filename for an intentional fresh run. Do not
change model configuration mid-run. Save the Git revision/configuration alongside each run.
New runs also write a `.manifest.json` containing engine/content fingerprints; changed
configuration cannot resume into an existing run. Older pilot files without manifests
remain historical artifacts: start a new filename after an engine change.
Latency measures the HTTP request, excluding pacing. Raw responses stay in ignored files.

The observed website uses `exact[0].target` and otherwise displays the original input.
We record that fallback as `no_exact`, not a successful translation. Suggestions are not
sentence translations. An unchanged name or number is not necessarily a failure, either.

Give reviewers only review.jsonl, not the private key or raw records. A/B order is randomized
per case. This is label blinding, not a guarantee reviewers cannot recognize system style.
Each speaker should independently fill reviewer/dialect, meaning and fluency (1–5),
critical_error (true/false), and notes. Meaning: 1=wrong, 3=partly correct, 5=fully preserved.
Fluency: 1=unnatural/unintelligible, 3=understandable with issues, 5=natural for that dialect.
Flag lost negation, altered names/numbers, and invented meaning. Leave ratings empty for
no output or inability to judge; report those separately as availability/coverage failures.
Use two independent speakers and adjudicate disagreements. Report sample sizes, coverage,
meaning, fluency and critical errors separately, including per-category results. Do not
call output agreement, round-trip consistency, or dictionary overlap “accuracy.”

## Browser review (offline-capable)

Generate a self-contained review page, with no system identities or network requests:

```powershell
.venv/Scripts/python.exe code/review_benchmark.py page --review code/benchmark_runs/review.jsonl --out code/benchmark_runs/review-site/index.html
```

Open the generated HTML in a browser, or serve only its directory locally. Share only
this HTML with reviewers, not the key or raw results. Each reviewer uses a unique stable
pseudonymous ID and specifies their dialect. Scores remain in page memory: export before
closing, then use the file import to resume. There is deliberately no shared-browser
autosave that might expose one reviewer's answers to another. Incomplete exports are allowed.
The optional correction is **not an independent reference**: the reviewer already saw A/B.

Aggregate each reviewer's latest export (do not include older exports from that reviewer):

```powershell
.venv/Scripts/python.exe code/review_benchmark.py summarize --review code/benchmark_runs/review.jsonl --key code/benchmark_runs/private_key.jsonl --ratings code/benchmark_runs/reviewer-01.jsonl code/benchmark_runs/reviewer-02.jsonl --out code/benchmark_runs/summary.json
```

The report separates output availability from human scores, gives rating counts and category
breakdowns, and flags score spreads of at least two points or conflicting critical-error
judgments for adjudication. Missing scores remain missing, not zero. Paired differences
compare only the same case judged by the same person for both systems. They are descriptive,
not a statistical superiority claim. Review dialect disagreements before pooling scores.
The tool rejects duplicate reviews, changed cases/outputs, invalid scores and ratings on
missing outputs. Treat the private key and template as a matched pair; keep both unchanged.

Before a larger study, freeze an independently authored, balanced holdout set. Never train
on it, its references, or collected teacher outputs for those inputs. A small diagnostic
set deliberately overrepresents failures and cannot estimate everyday user accuracy.

Training on a website's outputs is black-box sequence-level distillation/synthetic parallel
data generation; model weights are unnecessary. Check collection/training/redistribution
permission with the operator before scaling. Public access and robots rules do not settle
those questions. Do not submit private user text. Keep provenance and separate synthetic
outputs from speaker-verified examples; teacher errors can be inherited by the student.
