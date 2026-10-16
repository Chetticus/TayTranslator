"""Preflight only: refuse unreviewed/uncleared data and held-out source leakage."""
import argparse
import json
import re
import unicodedata

from compare_translators import read_rows


def normalized(text):
    return " ".join(re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFC", text).casefold()).split())


def check_training(rows, holdout):
    errors, seen_ids, seen_sources = [], set(), set()
    forbidden = {(c["direction"], normalized(c["text"])) for c in holdout}
    for row in rows:
        row_id = row.get("id")
        label = str(row_id or "<missing id>")
        def reject(message):
            errors.append({"id": label, "reason": message})
        if not isinstance(row_id, str) or not row_id or row_id in seen_ids:
            reject("Missing or duplicate ID")
        seen_ids.add(label)
        direction = row.get("direction")
        source, target = row.get("source"), row.get("target")
        if direction not in ("vi2tay", "tay2vi") or not isinstance(source, str) or not isinstance(target, str) or not source.strip() or not target.strip():
            reject("Invalid direction or empty source/target")
            continue
        source_key = (direction, normalized(source))
        inverse = "tay2vi" if direction == "vi2tay" else "vi2tay"
        if source_key in forbidden or (inverse, normalized(target)) in forbidden:
            reject("Overlaps a held-out input (including reverse direction)")
        if source_key in seen_sources:
            reject("Duplicate normalized training source")
        seen_sources.add(source_key)
        if normalized(source) == normalized(target):
            reject("Echoed input requires manual exclusion/review, not automatic training")
        provenance = row.get("provenance") or {}
        if not isinstance(provenance, dict) or provenance.get("kind") not in ("human", "synthetic") or not provenance.get("origin"):
            reject("Missing source provenance")
        if not isinstance(provenance, dict) or provenance.get("training_allowed") is not True or not provenance.get("permission_evidence"):
            reject("Training permission not documented")
        reviews = row.get("reviews") or []
        if not isinstance(reviews, list):
            reject("Reviews must be a list")
            continue
        approved = {r.get("reviewer_id") for r in reviews if isinstance(r, dict) and r.get("approved") is True and r.get("reviewer_id") and r.get("dialect")}
        if len(approved) < 2:
            reject("Requires two distinct approving speaker reviews with dialect recorded")
        if any(isinstance(r, dict) and r.get("approved") is False for r in reviews):
            reject("Unresolved negative review")
    if not rows:
        errors.append({"id": None, "reason": "Training dataset is empty"})
    if not holdout:
        errors.append({"id": None, "reason": "Holdout must be supplied"})
    return {"ready": not errors, "rows_checked": len(rows), "errors": errors,
            "limitations": "Checks recorded attestations and normalized overlap only, not actual permissions, review truthfulness, semantic duplicates or linguistic quality."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True)
    parser.add_argument("--holdout", required=True, nargs="+")
    args = parser.parse_args()
    result = check_training(read_rows(args.train), [c for p in args.holdout for c in read_rows(p)])
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()
