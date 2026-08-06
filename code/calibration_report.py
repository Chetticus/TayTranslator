"""
Kiểm chứng lời khẳng định "hệ thống biết khi nào nó không biết".

Hệ thống gắn nhãn độ tin cậy cho từng bản dịch. Cho tới giờ đó mới chỉ là tuyên
bố. Ở đây đối chiếu độ tin cậy DỰ ĐOÁN với chất lượng THỰC ĐO trên tập kiểm tra
tách riêng: nếu hiệu chỉnh tốt, nhóm "high" phải có chrF cao hơn hẳn nhóm "low".

Nếu không đúng như vậy thì đó là một lỗi thật, không phải chuyện thẩm mỹ — người
dùng đang được bảo là tin tưởng những bản dịch không đáng tin.

Chạy (trong thư mục code/):
    python calibration_report.py --n 500
Xuất ra bảng số + biểu đồ SVG (không cần thư viện vẽ ngoài).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main as app_main  # noqa: E402
from eval_translation import (  # noqa: E402
    EXCEL_PATH,
    RETRIEVE_K,
    _clean,
    _norm,
    chrf,
    load_example_pairs,
    token_f1,
)
from translation_api import lm  # noqa: E402
from translation_api.excel_glossary import (  # noqa: E402
    _CACHE,
    _ensure_index,
    _norm_loose,
    translate_with_excel_glossary,
)
from translation_api.retriever import retrieve  # noqa: E402

CONF_ORDER = ["high", "medium", "low"]


def _hold_out(test: list[tuple[str, str]]) -> None:
    """Gỡ câu kiểm tra khỏi CẢ chỉ mục lẫn mô hình ngôn ngữ."""
    _ensure_index(EXCEL_PATH)
    index, loose = _CACHE["index"], _CACHE["loose"]
    for tay, _vi in test:
        for bucket, key in ((index, _norm(tay)), (loose, _norm_loose(tay))):
            lst = bucket.get(key)
            if not lst:
                continue
            keep = [c for c in lst if c.get("kind") != "phrase"]
            if keep:
                bucket[key] = keep
            else:
                bucket.pop(key, None)
    lm._CACHE["locked"] = False
    lm.build(EXCEL_PATH, exclude_vi={(vi or "").strip().lower() for _t, vi in test}, lock=True)


def _clean_examples(query: str, gold: str, k: int) -> list[dict]:
    hits = retrieve(query, EXCEL_PATH, k=k + 8, exclude={_norm(query)})
    out, gq, gg = [], _clean(query), _clean(gold)
    for h in hits:
        if _clean(h["vi"]) == gg or (gq and gq in _clean(h["tay"])):
            continue
        out.append(h)
        if len(out) >= k:
            break
    return out


def _svg(conf_rows: list[dict], cov_rows: list[dict], out_path: Path) -> None:
    """Vẽ SVG thủ công — không kéo thêm phụ thuộc chỉ để có một biểu đồ."""
    W, H, pad = 720, 300, 46
    bar_area = (W - 2 * pad) / 2 - 20
    colours = {"high": "#10b981", "medium": "#f59e0b", "low": "#f43f5e"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="system-ui,sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#0f1422"/>',
        f'<text x="{pad}" y="26" fill="#e7ecf7" font-size="15" font-weight="700">'
        "Do predicted confidence and coverage track real quality?</text>",
        f'<text x="{pad}" y="46" fill="#97a3bd" font-size="11">'
        "Mean chrF on held-out sentences. Higher bars to the left = well calibrated.</text>",
    ]

    def bars(rows, x0, title, key_label, colour_fn):
        parts.append(
            f'<text x="{x0}" y="76" fill="#97a3bd" font-size="11" font-weight="600">{title}</text>'
        )
        if not rows:
            return
        n = len(rows)
        bw = min(52, (bar_area - 10 * (n - 1)) / max(1, n))
        base_y = H - 52
        max_h = base_y - 92
        for i, r in enumerate(rows):
            h = max(2.0, (r["chrf"] / 0.8) * max_h)
            x = x0 + i * (bw + 10)
            y = base_y - h
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                f'rx="3" fill="{colour_fn(r)}"/>'
            )
            parts.append(
                f'<text x="{x + bw / 2:.1f}" y="{y - 5:.1f}" fill="#e7ecf7" font-size="10" '
                f'text-anchor="middle">{r["chrf"]:.2f}</text>'
            )
            parts.append(
                f'<text x="{x + bw / 2:.1f}" y="{base_y + 14:.1f}" fill="#97a3bd" font-size="10" '
                f'text-anchor="middle">{r[key_label]}</text>'
            )
            parts.append(
                f'<text x="{x + bw / 2:.1f}" y="{base_y + 27:.1f}" fill="#6a7590" font-size="9" '
                f'text-anchor="middle">n={r["n"]}</text>'
            )

    bars(conf_rows, pad, "By reported confidence", "label", lambda r: colours.get(r["label"], "#6366f1"))
    bars(cov_rows, pad + bar_area + 40, "By coverage band", "label", lambda r: "#6366f1")
    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--out", default="calibration.json")
    ap.add_argument("--svg", default="calibration.svg")
    args = ap.parse_args()

    pairs = load_example_pairs(EXCEL_PATH)
    rng = random.Random(args.seed)
    rng.shuffle(pairs)
    test = pairs[: args.n]
    _hold_out(test)
    print(f"Đánh giá hiệu chỉnh trên {len(test)} câu tách riêng.\n")

    rows = []
    for tay, vi in test:
        ex = _clean_examples(tay, vi, RETRIEVE_K)
        base = translate_with_excel_glossary(tay, EXCEL_PATH, context_pairs=ex)
        meta = app_main._build_meta(base)
        rows.append(
            {
                "tay": tay,
                "ref": vi,
                "hyp": base["translation"],
                "confidence": meta["confidence"],
                "coverage": meta["coverage"],
                "weak_tokens": meta["weak_tokens"],
                "no_diacritics": meta["no_diacritics"],
                "chrf": chrf(base["translation"], vi),
                "f1": token_f1(base["translation"], vi),
            }
        )

    def summarize(subset):
        if not subset:
            return {"n": 0, "chrf": 0.0, "f1": 0.0}
        return {
            "n": len(subset),
            "chrf": sum(r["chrf"] for r in subset) / len(subset),
            "f1": sum(r["f1"] for r in subset) / len(subset),
        }

    conf_rows = []
    print(f"{'confidence':>12} {'n':>5} {'mean chrF':>10} {'mean F1':>9}")
    for c in CONF_ORDER:
        s = summarize([r for r in rows if r["confidence"] == c])
        if s["n"]:
            print(f"{c:>12} {s['n']:>5} {s['chrf']:>10.3f} {s['f1']:>9.3f}")
        conf_rows.append({"label": c, **s})

    bands = [(0.0, 0.5, "<50%"), (0.5, 0.8, "50-80%"), (0.8, 0.999, "80-99%"), (0.999, 1.01, "100%")]
    cov_rows = []
    print(f"\n{'coverage':>12} {'n':>5} {'mean chrF':>10} {'mean F1':>9}")
    for lo, hi, label in bands:
        s = summarize([r for r in rows if lo <= r["coverage"] < hi])
        if s["n"]:
            print(f"{label:>12} {s['n']:>5} {s['chrf']:>10.3f} {s['f1']:>9.3f}")
        cov_rows.append({"label": label, **s})

    # Hiệu chỉnh đúng nghĩa là chrF phải giảm dần theo high -> medium -> low.
    present = [r for r in conf_rows if r["n"] > 0]
    monotonic = all(present[i]["chrf"] >= present[i + 1]["chrf"] for i in range(len(present) - 1))
    print(f"\nĐộ tin cậy giảm dần đúng thứ tự: {'ĐẠT' if monotonic else 'KHÔNG ĐẠT'}")
    if len(present) >= 2:
        print(f"Chênh lệch chrF giữa nhóm cao nhất và thấp nhất: "
              f"{present[0]['chrf'] - present[-1]['chrf']:+.3f}")

    here = Path(__file__).resolve().parent
    _svg(conf_rows, [r for r in cov_rows if r["n"]], here / args.svg)
    (here / args.out).write_text(
        json.dumps(
            {"n": len(rows), "seed": args.seed, "by_confidence": conf_rows,
             "by_coverage": cov_rows, "monotonic": monotonic, "cases": rows},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nĐã ghi: {here / args.out}  và  {here / args.svg}")
    return 0 if monotonic else 1


if __name__ == "__main__":
    raise SystemExit(main())
