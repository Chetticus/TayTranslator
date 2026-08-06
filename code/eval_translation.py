"""
Đánh giá chất lượng dịch Tày -> Việt trên tập KIỂM TRA TÁCH RIÊNG.

Vì sao cần file này: các số liệu cũ (`tay_test_sentences_full_summary.json` báo
coverage 93.7%, `test_excel_translation_verified.json` báo 50% khớp) đều đo trên
chính những câu ví dụ đã được nạp vào chỉ mục, nên chỉ chứng minh "tra được thứ
vừa nạp vào". Ở đây các câu kiểm tra được GỠ khỏi chỉ mục trước khi đo, nên hệ
thống buộc phải ghép nghĩa mức từ như với câu mới hoàn toàn.

Cách chạy (từ thư mục code/):
    python eval_translation.py                 # đo lớp tra từ điển, nhanh
    python eval_translation.py --n 300         # đổi cỡ mẫu
    python eval_translation.py --llm --n 40    # đo cả Ollama (chậm)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from translation_api.excel_glossary import (
    _CACHE,
    _CACHES,
    _ensure_index,
    _norm,
    _norm_loose,
    _split_definition,
    translate_with_excel_glossary,
)

EXCEL_PATH = Path(
    os.getenv(
        "EXCEL_GLOSSARY_PATH",
        str(Path(__file__).resolve().parents[1] / "tu_dien_viet_tay_nung_parsed.xlsx"),
    )
)
_PUNCT_RE = re.compile(r"[.,!?;:()\[\]\"'«»…]")
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "2"))


def _clean(s: str) -> str:
    return _PUNCT_RE.sub(" ", (s or "").lower()).strip()


def _tokens(s: str) -> list[str]:
    return _clean(s).split()


def chrf(hyp: str, ref: str, max_n: int = 6, beta: float = 2.0) -> float:
    """chrF: F-score trên n-gram ký tự — hợp với ngôn ngữ ít dữ liệu hơn BLEU."""
    h = _clean(hyp).replace(" ", "")
    r = _clean(ref).replace(" ", "")
    if not h or not r:
        return 0.0
    precisions, recalls = [], []
    for n in range(1, max_n + 1):
        hg = Counter(h[i:i + n] for i in range(len(h) - n + 1))
        rg = Counter(r[i:i + n] for i in range(len(r) - n + 1))
        if not hg or not rg:
            continue
        overlap = sum((hg & rg).values())
        precisions.append(overlap / max(1, sum(hg.values())))
        recalls.append(overlap / max(1, sum(rg.values())))
    if not precisions:
        return 0.0
    p = sum(precisions) / len(precisions)
    r_ = sum(recalls) / len(recalls)
    if p + r_ == 0:
        return 0.0
    b2 = beta ** 2
    return (1 + b2) * p * r_ / (b2 * p + r_)


def token_f1(hyp: str, ref: str) -> float:
    h, r = Counter(_tokens(hyp)), Counter(_tokens(ref))
    if not h or not r:
        return 0.0
    overlap = sum((h & r).values())
    if overlap == 0:
        return 0.0
    p = overlap / sum(h.values())
    rc = overlap / sum(r.values())
    return 2 * p * rc / (p + rc)


def build_reference_map(pairs: list[tuple[str, str]], direction: str) -> dict[str, list[str]]:
    """
    Gom MỌI bản dịch được coi là đúng cho cùng một câu nguồn.

    Chấm điểm với một đáp án duy nhất là quá khắt khe: "lời nói bóng bẩy" chỉ
    được 0.43 so với "Câu văn bóng bẩy" dù cả hai đều là bản dịch hợp lệ. Chính
    kho ngữ liệu đã chứa nhiều cách dịch khác nhau cho cùng một câu, nên gom lại
    là cách mở rộng đáp án mà không cần gán nhãn tay.
    """
    refs: dict[str, set[str]] = {}
    for tay, vi in pairs:
        src, tgt = (vi, tay) if direction == "vi2tay" else (tay, vi)
        key = _norm(src)
        if key and tgt:
            refs.setdefault(key, set()).add(tgt.strip())
    return {k: sorted(v) for k, v in refs.items()}


def best_chrf(hyp: str, refs: list[str]) -> float:
    return max((chrf(hyp, r) for r in refs), default=0.0)


def best_f1(hyp: str, refs: list[str]) -> float:
    return max((token_f1(hyp, r) for r in refs), default=0.0)


def matches_any(hyp: str, refs: list[str]) -> bool:
    h = _clean(hyp)
    return any(h == _clean(r) for r in refs)


def load_example_pairs(excel_path: Path) -> list[tuple[str, str]]:
    """Lấy toàn bộ cặp ví dụ (Tày, Việt) từ từ điển."""
    df = pd.read_excel(excel_path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    pairs: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        head = str(row.get("headword", "") or "").strip()
        raw = str(row.get("definition_raw", "") or "")
        if not head or not raw:
            continue
        _glosses, examples = _split_definition(raw, head)
        for vi, tay in examples:
            if len(_tokens(tay)) >= 2 and _tokens(vi):
                pairs.append((tay, vi))
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200, help="số câu kiểm tra")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--llm", action="store_true", help="đo cả bước Ollama (chậm)")
    ap.add_argument(
        "--direction", choices=["tay2vi", "vi2tay"], default="tay2vi",
        help="vi2tay là chiều gốc của từ điển, ít mơ hồ hơn",
    )
    ap.add_argument("--out", default="eval_report.json")
    args = ap.parse_args()
    direction = args.direction

    if not EXCEL_PATH.exists():
        print(f"Không thấy từ điển: {EXCEL_PATH}", file=sys.stderr)
        return 1

    pairs = load_example_pairs(EXCEL_PATH)
    rng = random.Random(args.seed)
    rng.shuffle(pairs)
    sample = pairs[: args.n]
    # `load_example_pairs` trả (tày, việt). Chiều vi2tay thì đảo lại: nguồn là
    # tiếng Việt, đích là tiếng Tày.
    test = [(vi, tay) for tay, vi in sample] if direction == "vi2tay" else list(sample)
    ref_map = build_reference_map(pairs, direction)

    # Một câu Tày có thể có nhiều bản dịch tiếng Việt hợp lệ. LM, mô hình căn
    # chỉnh và bảng cụm đều loại trừ theo PHÍA VIỆT, nên phải bỏ TẤT CẢ các bản
    # đó — giữ lại một bản thay thế cũng là rò rỉ đáp án.
    tay_to_vi = build_reference_map(pairs, "tay2vi")
    held_out_vi: set[str] = set()
    for tay, vi in sample:
        for alt in tay_to_vi.get(_norm(tay), [vi]):
            held_out_vi.add((alt or "").strip().lower())

    multi = sum(1 for src, _t in test if len(ref_map.get(_norm(src), [])) > 1)
    print(f"Chiều dịch: {direction}")
    print(f"Tổng cặp ví dụ: {len(pairs)}   |   dùng kiểm tra: {len(test)}")
    print(f"Câu kiểm tra có nhiều hơn một đáp án hợp lệ: {multi}/{len(test)}")

    _ensure_index(EXCEL_PATH, direction)
    cache = _CACHES[direction]
    index = cache["index"]
    loose = cache["loose"]

    # Gỡ chính các câu kiểm tra khỏi chỉ mục: chỉ xóa mục sinh ra từ câu ví dụ
    # (kind == "phrase"), giữ nguyên nghĩa mức từ — đúng tình huống gặp câu mới.
    removed = 0
    for tay, _vi in test:
        # Phải gỡ ở CẢ hai lớp: nếu chỉ gỡ lớp giữ dấu thì lớp bỏ dấu vẫn khớp
        # nguyên câu và điểm đo sẽ đẹp giả tạo.
        for bucket, key in ((index, _norm(tay)), (loose, _norm_loose(tay))):
            lst = bucket.get(key)
            if not lst:
                continue
            keep = [c for c in lst if c.get("kind") != "phrase"]
            if len(keep) != len(lst):
                removed += 1
            if keep:
                bucket[key] = keep
            else:
                bucket.pop(key, None)
    print(f"Đã gỡ {removed} mục câu-ví-dụ khỏi chỉ mục trước khi đo.")

    # Mô hình ngôn ngữ cũng phải KHÔNG được thấy câu đích của tập kiểm tra.
    # Nếu bỏ bước này, bộ giải mã Viterbi tái tạo gần đúng câu đáp án và chrF
    # nhảy từ 0.395 lên 0.548 — một con số hoàn toàn giả.
    from translation_api import align, lm, phrases  # noqa: PLC0415

    lm_side = lm.TAY if direction == "vi2tay" else lm.VI
    lm.build(EXCEL_PATH, exclude_vi=held_out_vi, lock=True, side=lm_side)
    print(f"LM ({lm_side}) dựng không có {len(held_out_vi)} câu đích kiểm tra: {lm.stats(lm_side)}")

    # Mọi thành phần học từ kho ngữ liệu đều phải bị chặn khỏi tập kiểm tra —
    # nếu không thì lại lặp đúng lỗi rò rỉ đã mắc hai lần trước.
    align.build(EXCEL_PATH, exclude_vi=held_out_vi, lock=True)
    print(f"Mô hình căn chỉnh dựng không có câu kiểm tra: {align.stats()}")

    phrases.build(EXCEL_PATH, exclude_vi=held_out_vi, lock=True)
    print(f"Bảng cụm trích không có câu kiểm tra: {phrases.stats()}\n")

    from translation_api.retriever import retrieve  # noqa: PLC0415

    def clean_examples(query: str, gold: str, k: int) -> list[dict]:
        """
        Truy xuất ví dụ nhưng CHẶN rò rỉ đáp án.

        Kho ví dụ chứa chính câu đang chấm (đôi khi ở dạng bẩn còn ký hiệu '~:'),
        nên loại theo khóa chính xác là chưa đủ — phải bỏ cả những cặp có phần
        tiếng Việt trùng đáp án.
        """
        hits = retrieve(
            query, EXCEL_PATH, k=k + 6, exclude={_norm(query)}, direction=direction
        )
        out, gq, gg = [], _clean(query), _clean(gold)
        for h in hits:
            if _clean(h["vi"]) == gg:
                continue
            if gq and gq in _clean(h["tay"]):
                continue
            out.append(h)
            if len(out) >= k:
                break
        return out

    rows = []
    for tay, vi in test:
        refs = ref_map.get(_norm(tay)) or [vi]
        base = translate_with_excel_glossary(tay, EXCEL_PATH, direction=direction)
        hyp = base["translation"]

        # Arm: tra từ điển + chọn nghĩa theo ngữ cảnh truy xuất (KHÔNG dùng LLM)
        ex = clean_examples(tay, vi, RETRIEVE_K)
        ctx_base = translate_with_excel_glossary(
            tay, EXCEL_PATH, context_pairs=ex, direction=direction
        )
        hyp_ctx = ctx_base["translation"]

        rows.append(
            {
                "tay": tay,
                "ref": vi,
                "refs": refs,
                "hyp_lookup": hyp,
                "hyp_ctx": hyp_ctx,
                "coverage": base["coverage"],
                "passthrough": base["passthrough_tokens"],
                "context_picks": ctx_base.get("context_picks", 0),
                "chrf": best_chrf(hyp, refs),
                "f1": best_f1(hyp, refs),
                "chrf_ctx": best_chrf(hyp_ctx, refs),
                "f1_ctx": best_f1(hyp_ctx, refs),
            }
        )

    def summarize(key_hyp: str, key_chrf: str, key_f1: str, label: str) -> dict:
        n = len(rows)
        avg_chrf = sum(r[key_chrf] for r in rows) / max(1, n)
        avg_f1 = sum(r[key_f1] for r in rows) / max(1, n)
        exact = sum(1 for r in rows if matches_any(r[key_hyp], r["refs"])) / max(1, n)
        print(f"--- {label} ---")
        print(f"  chrF trung bình      : {avg_chrf:.3f}")
        print(f"  token-F1 trung bình  : {avg_f1:.3f}")
        print(f"  khớp tuyệt đối       : {exact:.1%}")
        return {"chrf": avg_chrf, "token_f1": avg_f1, "exact_match": exact}

    avg_cov = sum(r["coverage"] for r in rows) / max(1, len(rows))
    n_pass = sum(r["passthrough"] for r in rows)
    print(f"coverage trung bình (chỉ tính tra được thật): {avg_cov:.3f}")
    print(f"token giữ nguyên vì trùng hình thức tiếng Việt: {n_pass}\n")

    report = {
        "excel": str(EXCEL_PATH),
        "n_test": len(rows),
        "seed": args.seed,
        "avg_coverage": avg_cov,
        "lookup": summarize("hyp_lookup", "chrf", "f1", "Chỉ tra từ điển (không LLM)"),
        "lookup_ctx": summarize(
            "hyp_ctx", "chrf_ctx", "f1_ctx", "Tra từ điển + chọn nghĩa theo ngữ cảnh (không LLM)"
        ),
    }
    n_picks = sum(r["context_picks"] for r in rows)
    print(f"  số lần ngữ cảnh đổi lựa chọn nghĩa: {n_picks}\n")
    report["context_picks_total"] = n_picks

    if args.llm:
        import main as app_main  # noqa: PLC0415

        model = app_main.resolve_ollama_model()

        def run_arm(use_rag: bool, key: str, label: str) -> None:
            print(f"\nĐang chạy Ollama ({model}) — {label} — {len(rows)} câu...")
            for i, r in enumerate(rows, 1):
                ex = clean_examples(r["tay"], r["ref"], app_main.RETRIEVE_K) if use_rag else []
                # Arm có truy xuất dùng đúng đường đi của app: ngữ cảnh vừa dùng
                # để chọn nghĩa, vừa làm ví dụ few-shot cho mô hình.
                base = translate_with_excel_glossary(
                    r["tay"], EXCEL_PATH, context_pairs=ex if ex else None
                )
                meta = app_main._build_meta(base)
                r[key + "_nex"] = len(ex)
                try:
                    if meta["coverage"] < app_main.LOW_COVERAGE_THRESHOLD:
                        out = base["translation"]
                    else:
                        style = (
                            "editor"
                            if meta["coverage"] >= app_main.HIGH_COVERAGE_THRESHOLD
                            else "guided_guess"
                        )
                        out = app_main.translate_tay_to_vi_ollama_with_glossary(
                            r["tay"], base["glossary"], meta, style=style, examples=ex
                        )
                except RuntimeError as e:
                    out = base["translation"]
                    if i == 1:
                        print(f"  (Ollama lỗi, dùng bản ghép từ điển: {e})")
                r["hyp_" + key] = out
                r["chrf_" + key] = best_chrf(out, r["refs"])
                r["f1_" + key] = best_f1(out, r["refs"])
                if i % 10 == 0:
                    print(f"  {i}/{len(rows)}")

        run_arm(False, "llm", "KHÔNG truy xuất")
        report["llm"] = summarize("hyp_llm", "chrf_llm", "f1_llm", f"LLM không truy xuất ({model})")

        run_arm(True, "rag", "CÓ truy xuất")
        report["rag"] = summarize("hyp_rag", "chrf_rag", "f1_rag", f"LLM + truy xuất ({model})")

        avg_ex = sum(r.get("rag_nex", 0) for r in rows) / max(1, len(rows))
        print(f"  ví dụ truy xuất trung bình mỗi câu: {avg_ex:.1f}")
        report["avg_examples"] = avg_ex
        report["llm_model"] = model

    out_path = Path(__file__).resolve().parent / args.out
    out_path.write_text(
        json.dumps({"summary": report, "cases": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nĐã ghi báo cáo: {out_path}")

    print("\nVí dụ (6 câu đầu):")
    for r in rows[:6]:
        print(f"  Tày : {r['tay']}")
        print(f"  Đúng: {r['ref']}")
        print(f"  Tra : {r['hyp_lookup']}   (chrF {r['chrf']:.2f}, cov {r['coverage']:.2f})")
        if "hyp_llm" in r:
            print(f"  LLM : {r['hyp_llm']}   (chrF {r['chrf_llm']:.2f})")
        if "hyp_rag" in r:
            print(f"  RAG : {r['hyp_rag']}   (chrF {r['chrf_rag']:.2f}, {r.get('rag_nex', 0)} ví dụ)")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
