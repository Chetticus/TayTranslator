# Run TayTranslator locally

This guide starts the same local web app used for development and testing. No API key is required. Tày ↔ Vietnamese translation uses the repository's Excel dictionary, while English ↔ Tày uses local translation models through Vietnamese.

## 1. Prerequisites

- Python 3.11 or 3.12 (64-bit recommended)
- About 1 GB of free disk space if you want the optional English feature
- Node.js only if you want to run the browser interaction tests
- An internet connection for the initial dependency and English-model downloads

Run all commands from the repository root—the folder containing `code`, `scripts`, and `tu_dien_viet_tay_nung_parsed.xlsx`.

## 2. Create the environment and install dependencies

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r code\requirements-dev.txt
```

### macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r code/requirements-dev.txt
```

The commands above are enough for the core Tày ↔ Vietnamese translator and automated tests.

## 3. Enable the English feature

English ↔ Tày is optional. It runs locally using English ↔ Vietnamese models and then the project's Vietnamese ↔ Tày dictionary.

### Windows PowerShell

```powershell
.venv\Scripts\python.exe -m pip install -r code\requirements-english.txt
.venv\Scripts\python.exe code\setup_english.py
```

### macOS or Linux

```bash
.venv/bin/python -m pip install -r code/requirements-english.txt
.venv/bin/python code/setup_english.py
```

The setup script downloads the models once into `code/models/english`. After that, English translation runs offline. The model folder is intentionally excluded from Git. If the models are absent, the main Tày ↔ Vietnamese translator still works, but English requests return a setup message.

## 4. Start the website

### Windows PowerShell

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --app-dir code --host 127.0.0.1 --port 8000
```

### macOS or Linux

```bash
.venv/bin/python -m uvicorn main:app --app-dir code --host 127.0.0.1 --port 8000
```

Keep that terminal open, then visit:

- Website: <http://127.0.0.1:8000/>
- Readiness report: <http://127.0.0.1:8000/api/health>

Stop the server with `Ctrl+C`.

The server is intentionally bound to `127.0.0.1`, so only this computer can access it. Use a proper deployment rather than exposing the development server directly to the internet.

## 5. Verify the installation

On Windows, the repository's complete verification command is:

```powershell
.\scripts\verify.ps1
```

It runs the Python suite, browser interaction checks, and a whitespace check. Node.js is needed for the browser interaction portion.

To run only the Python tests:

```powershell
.venv\Scripts\python.exe -m pytest code\tests -q
```

On macOS or Linux, use:

```bash
.venv/bin/python -m pytest code/tests -q
```

For a quick manual check, open the health endpoint and confirm:

- `ok` is `true`
- `dictionary_ok` is `true`
- `excel_exists` is `true`
- `english.ready` is `true` if you installed the English models

## Common problems

### Port 8000 is already in use

Start on another port:

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --app-dir code --host 127.0.0.1 --port 8001
```

Then open <http://127.0.0.1:8001/>.

### The dictionary is not found

Start the command from the repository root. By default, the app expects `tu_dien_viet_tay_nung_parsed.xlsx` there. To use a different file, set `EXCEL_GLOSSARY_PATH` before starting the server:

```powershell
$env:EXCEL_GLOSSARY_PATH = "C:\full\path\to\dictionary.xlsx"
```

### English translation says it is unavailable

Run the two commands in **Enable the English feature**, then restart the server. The model download is roughly 300 MB and needs network access only during setup.

### First translation is slower

The dictionary index and local English models load on first use. Later requests should be faster.

### Microphone input does not work

Audio transcription is experimental and is not required for text translation. It additionally needs `openai-whisper` and FFmpeg, and its Tày accuracy has not yet been speaker-validated.

## Optional settings

The normal tested defaults require no environment variables. Useful development overrides include:

- `USE_LLM=1`: try the optional Ollama editing stage. It is off by default because current evaluation results are worse than the dictionary-only path.
- `LOG_UNKNOWN_TERMS=1`: record untranslated terms to `code/unknown_terms_log.jsonl` for review. Do not enable this when handling private user text without consent.
- `EXCEL_GLOSSARY_PATH`: use a different dictionary workbook.

