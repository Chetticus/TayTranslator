"""Offline review-page export and validated aggregation of blinded human ratings."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from compare_translators import read_rows


def index_unique(rows, field):
    result = {}
    for row in rows:
        key = row[field]
        if key in result:
            raise ValueError(f"Duplicate {field}: {key}")
        result[key] = row
    return result


def export_page(review_path, out):
    rows = read_rows(review_path)
    if not rows:
        raise ValueError("No review cases")
    index_unique(rows, "case_hash")
    # Explicit allowlist: never embed the key, raw API responses or preexisting ratings.
    clean = [{"case_hash": r["case_hash"], "case": r["case"],
              "reviewer": "", "dialect": "", "reference_translation": "",
              **{label: {"output": r[label]["output"], "status": r[label]["status"],
                         "meaning_1_to_5": None, "fluency_1_to_5": None,
                         "critical_error": None, "notes": ""} for label in ("A", "B")}}
             for r in rows]
    data = json.dumps(clean, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    template = Path(__file__).with_name("templates").joinpath("benchmark_review.html").read_text(encoding="utf-8")
    destination = Path(out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(template.replace("__REVIEW_DATA__", data))


def summarize(template, key, submissions):
    originals = index_unique(template, "case_hash")
    mappings = index_unique(key, "case_hash")
    if set(originals) != set(mappings):
        raise ValueError("Review template and key have different cases")
    buckets = defaultdict(list)
    coverage = defaultdict(lambda: {"cases": 0, "outputs_available": 0})
    for h, row in originals.items():
        if {mappings[h][s] for s in ("A", "B")} != {"local", "taynung"}:
            raise ValueError("Invalid engine mapping")
        for side in ("A", "B"):
            engine = mappings[h][side]
            coverage[engine]["cases"] += 1
            coverage[engine]["outputs_available"] += int(row[side]["status"] == "ok")
    seen, raters = set(), set()
    for row in submissions:
        h = row["case_hash"]
        if h not in originals or row["case"] != originals[h]["case"]:
            raise ValueError("Unknown or modified case")
        reviewer, dialect = row.get("reviewer", "").strip(), row.get("dialect", "").strip()
        if not reviewer or not dialect:
            raise ValueError("Each submission needs a reviewer ID and dialect")
        if (reviewer, h) in seen:
            raise ValueError(f"Duplicate review by {reviewer}; include only their latest export")
        seen.add((reviewer, h))
        raters.add(reviewer)
        for side in ("A", "B"):
            score, expected = row[side], originals[h][side]
            if any(score.get(k) != expected[k] for k in ("output", "status")):
                raise ValueError("Output/status changed; ratings must match the frozen benchmark")
            for field in ("meaning_1_to_5", "fluency_1_to_5"):
                value = score.get(field)
                if value is not None and (type(value) is not int or not 1 <= value <= 5):
                    raise ValueError(f"Invalid {field}")
            critical = score.get("critical_error")
            if critical is not None and type(critical) is not bool:
                raise ValueError("Critical error must be true, false, or null")
            if expected["status"] != "ok" and any(score.get(k) is not None for k in
                    ("meaning_1_to_5", "fluency_1_to_5", "critical_error")):
                raise ValueError("Missing outputs cannot receive quality ratings")
            buckets[(h, mappings[h][side])].append(dict(score, reviewer=reviewer, dialect=dialect))

    def aggregate(items):
        result = {"case_reviewer_records": len(items)}
        for field in ("meaning_1_to_5", "fluency_1_to_5"):
            values = [r[field] for r in items if r.get(field) is not None]
            result[field] = {"n": len(values), "mean": round(mean(values), 3) if values else None}
        flags = [r["critical_error"] for r in items if r.get("critical_error") is not None]
        result["critical_error"] = {"n": len(flags), "flagged": sum(flags),
                                    "fraction": sum(flags) / len(flags) if flags else None}
        return result

    disagreements = []
    for (h, engine), records in buckets.items():
        reasons = []
        for field in ("meaning_1_to_5", "fluency_1_to_5"):
            values = [r[field] for r in records if r.get(field) is not None]
            if values and max(values) - min(values) >= 2:
                reasons.append(field)
        if len({r["critical_error"] for r in records if r.get("critical_error") is not None}) > 1:
            reasons.append("critical_error")
        if reasons:
            disagreements.append({"case_id": originals[h]["case"]["id"], "engine": engine,
                                  "reasons": reasons, "reviews": records})
    engines = {}
    for engine in ("local", "taynung"):
        records = [r for (_, e), rows in buckets.items() if e == engine for r in rows]
        categories = {r["case"].get("category", "uncategorized") for r in template}
        engines[engine] = {"coverage": coverage[engine], "quality": aggregate(records),
            "by_category": {category: aggregate([r for (h, e), rows in buckets.items()
                if e == engine and originals[h]["case"].get("category", "uncategorized") == category
                for r in rows]) for category in sorted(categories)}}
    paired = {}
    for field in ("meaning_1_to_5", "fluency_1_to_5"):
        deltas = []
        for h in originals:
            local = {r["reviewer"]: r for r in buckets[(h, "local")]}
            remote = {r["reviewer"]: r for r in buckets[(h, "taynung")]}
            for reviewer in local.keys() & remote.keys():
                a, b = local[reviewer].get(field), remote[reviewer].get(field)
                if a is not None and b is not None:
                    deltas.append(a - b)
        paired[field] = {"matched_case_reviewer_pairs": len(deltas),
                         "mean_local_minus_taynung": round(mean(deltas), 3) if deltas else None}
    return {"warning": "Diagnostic pilot, not population accuracy. Means pool nonmissing case-reviewer ratings; unequal reviewer coverage can bias comparisons.",
            "reviewers": len(raters), "submitted_case_reviews": len(seen),
            "paired_quality": paired, "engines": engines, "disagreements": disagreements}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    page = sub.add_parser("page")
    page.add_argument("--review", required=True)
    page.add_argument("--out", required=True)
    report = sub.add_parser("summarize")
    report.add_argument("--review", required=True)
    report.add_argument("--key", required=True)
    report.add_argument("--ratings", required=True, nargs="+")
    report.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.command == "page":
        export_page(args.review, args.out)
    else:
        result = summarize(read_rows(args.review), read_rows(args.key),
                           [r for path in args.ratings for r in read_rows(path)])
        with Path(args.out).open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
