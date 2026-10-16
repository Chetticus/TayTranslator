# English ↔ Tày (experimental, offline)

Installed and smoke-tested locally on October 13, 2026: both API directions and
both browser controls worked; Vietnamese intermediate text was inspected in the
UI. Full regression checks: 97 Python tests and 3 JavaScript interaction tests.
These are functionality checks, not a linguistic accuracy measurement.

The English routes use Vietnamese as a pivot:

- English → local English/Vietnamese model → dictionary Vietnamese/Tày step.
- Tày → dictionary Tày/Vietnamese step → local Vietnamese/English model.

These are **not direct English/Tày models** and have not been evaluated by Tày
speakers. Errors can accumulate in either step. The UI shows the intermediate
Vietnamese text and reports dictionary coverage only for the dictionary step.
Overall confidence is conservatively marked low, never inherited as high from
the dictionary alone. The optional Ollama editor is not used on English routes.

## Install once

```powershell
.venv/Scripts/python.exe -m pip install -r code/requirements-english.txt
.venv/Scripts/python.exe code/setup_english.py
.venv/Scripts/python.exe -m uvicorn main:app --app-dir code --host 127.0.0.1 --port 8000
```

Setup downloads two Argos 1.9 packages from the official package-index URLs.
The adapter runs their SentencePiece tokenizers and CTranslate2 models directly
on the CPU (int8, four threads), without the full Argos/Stanza/PyTorch dependency
stack. This lightweight adapter uses bounded text segments, not Argos's sentence
segmentation pipeline. Models and download archives stay under ignored
`code/models/english/`; they are not committed. Installation manifests record
download URLs, archive/file SHA256 hashes and upstream metadata. Hashes record
what was downloaded; they are not an independently signed upstream checksum.
Upstream README/license material is retained when supplied in the archives.
The package READMEs credit Jörg Tiedemann and Santhosh Thottingal, *OPUS-MT —
Building open translation services for the World* (EAMT 2020), and identify the
original OPUS models as CC-BY 4.0. The packages are third-party pretrained models,
not models trained by this project.

After setup, inference is local and contains no network calls. There is no paid
API and no automatic model download in response to a translation request. If
dependencies or models are missing, the API returns HTTP 503 with setup guidance;
it does not return a Vietnamese result labelled as English. `/api/health` includes
English model installation status (actual inference is verified by the smoke test).

Use `direction: "en2tay"` or `"tay2en"` on `/api/translate`. Existing `tay2vi`
and `vi2tay` remain unchanged. Both new directions also appear in the page selector.

Explicit keep-unchanged phrases, structured literals and unknown-word markers
are copied around model-translated segments. An English `my name is ...` introduction
also has a bounded name heuristic. This is not general name recognition: use the
keep-unchanged field for ambiguous names. Segmenting around preserved values can
reduce grammatical quality. Oversized token sequences are rejected instead of
silently truncated. Restart the server after changing models or dependencies.

Sources: [Argos model index](https://github.com/argosopentech/argospm-index/blob/main/index.json),
[Argos translation implementation](https://github.com/argosopentech/argos-translate/blob/master/argostranslate/translate.py),
[Argos tokenizer](https://github.com/argosopentech/argos-translate/blob/master/argostranslate/tokenizer.py),
[CTranslate2 runtime](https://opennmt.net/CTranslate2/python/ctranslate2.Translator.html).
