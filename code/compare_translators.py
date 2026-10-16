"""Small opt-in website benchmark. Outputs are NOT a training corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REMOTE = "https://admin.taynung.com/api/words/trans"


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def identity(case):
    return hashlib.sha256(json.dumps(case, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def parse_output(engine, data):
    if engine == "taynung":
        exact = data.get("exact") or []
        if not exact:
            # The website echoes the input in this situation. That is NOT a translation.
            return "no_exact", None
        target = exact[0].get("target")
    else:
        target = data.get("reply")
    if not isinstance(target, str) or not target.strip():
        raise ValueError("Response did not contain a nonempty translation")
    return "ok", target


def ensure_manifest(out, expected):
    path = Path(str(out) + ".manifest.json")
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["configuration"] != expected:
            raise ValueError("Run configuration changed. Use a new output file; do not mix engine versions.")
    else:
        if out.exists() and out.stat().st_size:
            raise ValueError("Legacy results have no manifest. Keep them unchanged and start a new run.")
        with path.open("x", encoding="utf-8") as handle:
            json.dump({"created_at": datetime.now(timezone.utc).isoformat(), "configuration": expected}, handle, ensure_ascii=False, indent=2)


def collect(args):
    cases = read_rows(args.cases)
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Case IDs must be unique")
    for c in cases:
        if c["direction"] not in ("vi2tay", "tay2vi") or not c["text"].strip():
            raise ValueError("Invalid direction or empty input")
        if len(c["text"].split()) > 20:
            raise ValueError("This comparison respects the website's 20-word UI limit")
    if args.remote and len(cases) > 50:
        raise ValueError("Pilot capped at 50 cases; arrange permission before scaling collection")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    health_response = requests.get(args.local.rstrip("/") + "/api/health", timeout=60)
    health_response.raise_for_status()
    health = health_response.json()
    if not health.get("ok") or not health.get("engine_fingerprint"):
        raise ValueError("Local server is not ready or lacks a version fingerprint; restart the updated server")
    ensure_manifest(out, {"cases_sha256": identity(cases), "local_url": args.local,
                         "remote_enabled": args.remote, "remote_url": REMOTE if args.remote else None,
                         "engine": health["engine_fingerprint"]})
    previous = read_rows(out) if out.exists() else []
    done = {(r["case_hash"], r["engine"]) for r in previous}
    engines = ["local", "taynung"] if args.remote else ["local"]
    with out.open("a", encoding="utf-8") as handle:
        for case in cases:
            for engine in engines:
                if engine == "taynung" and case.get("local_only"):
                    continue
                key = (identity(case), engine)
                if key in done:
                    continue
                record = dict(case=case, case_hash=key[0], engine=engine,
                              timestamp=datetime.now(timezone.utc).isoformat())
                stop = False
                start = time.monotonic()
                try:
                    if engine == "taynung":
                        time.sleep(max(3, args.delay))
                        field = "viet" if case["direction"] == "vi2tay" else "tay"
                        url, payload = REMOTE, {field: case["text"]}
                    else:
                        url, payload = args.local.rstrip("/") + "/api/translate", {
                            "message": case["text"], "direction": case["direction"]}
                    start = time.monotonic()
                    response = requests.post(url, json=payload, timeout=30,
                                             headers={"User-Agent": "TayTranslator-evaluation/0.1"})
                    record["http_status"] = response.status_code
                    response.raise_for_status()
                    record["raw"] = response.json()
                    record["status"], record["output"] = parse_output(engine, record["raw"])
                    record["echo"] = record["output"] == case["text"]
                except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                    record.update(status="error", output=None, error=str(exc))
                    # No automatic retries or attempts to circumvent server restrictions.
                    stop = engine == "taynung"
                record["seconds"] = round(time.monotonic() - start, 3)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                done.add(key)
                print(json.dumps([case["id"], engine, record["status"], record["output"]], ensure_ascii=True))
                if stop:
                    raise SystemExit("Remote collection stopped on an error; inspect the saved record")


def blind(args):
    grouped = {}
    for record in read_rows(args.results):
        grouped.setdefault(record["case_hash"], []).append(record)
    review, key = [], []
    rng = random.Random(args.seed)
    for case_hash, records in grouped.items():
        if len(records) != 2 or {r["engine"] for r in records} != {"local", "taynung"}:
            continue
        rng.shuffle(records)
        row = {"case_hash": case_hash, "case": records[0]["case"],
               "reviewer": "", "dialect": "", "reference_translation": ""}
        mapping = {"case_hash": case_hash}
        for label, record in zip(("A", "B"), records):
            row[label] = {"output": record["output"], "status": record["status"],
                          "meaning_1_to_5": None, "fluency_1_to_5": None,
                          "critical_error": None, "notes": ""}
            mapping[label] = record["engine"]
        review.append(row)
        key.append(mapping)
    for path, rows in ((args.out, review), (args.key, key)):
        with Path(path).open("x", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Prepared {len(review)} blinded pairs; keep the key away from reviewers")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect_parser = sub.add_parser("collect")
    collect_parser.add_argument("--cases", default=str(Path(__file__).with_name("comparison_cases.jsonl")))
    collect_parser.add_argument("--out", required=True)
    collect_parser.add_argument("--local", default="http://127.0.0.1:8000")
    collect_parser.add_argument("--remote", action="store_true", help="Explicitly query taynung.com")
    collect_parser.add_argument("--delay", type=float, default=3)
    collect_parser.set_defaults(func=collect)
    blind_parser = sub.add_parser("blind")
    blind_parser.add_argument("--results", required=True)
    blind_parser.add_argument("--out", required=True)
    blind_parser.add_argument("--key", required=True)
    blind_parser.add_argument("--seed", type=int, default=42)
    blind_parser.set_defaults(func=blind)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
