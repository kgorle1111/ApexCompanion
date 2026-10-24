"""Real-screenshot eval for gemma.classify.

Exit 1 if (non-ambiguous) accuracy < 0.85, distracted recall < 0.85, or any false roast on a non-ambiguous case.

Usage: .venv/bin/python eval.py [--split all|tune|holdout]
Labels: evals/labels.json. Unlabeled images in evals/user/ are printed as "needs label".
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).parent
EVALS = ROOT / "evals"
IMG_EXT = {".jpg", ".jpeg", ".png"}
MIN_ACC = 0.85


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(p / 100 * (len(xs) - 1))))
    return xs[k]


def acc(rows: list[dict]) -> str:
    if not rows:
        return "n/a (0 cases)"
    ok = sum(r["correct"] for r in rows)
    return f"{ok}/{len(rows)} = {ok / len(rows):.3f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["all", "tune", "holdout"], default="all")
    ap.add_argument("--labels", default="labels.json", help="labels file inside evals/ (e.g. labels2.json)")
    args = ap.parse_args()

    labels = json.loads((EVALS / args.labels).read_text())
    labeled = {c["file"] for c in labels}
    user_dir = EVALS / "user"
    if user_dir.is_dir():
        for p in sorted(user_dir.iterdir()):
            rel = str(p.relative_to(EVALS))
            if p.suffix.lower() in IMG_EXT and rel not in labeled:
                print(f"needs label: evals/{rel}")

    cases = [c for c in labels if args.split == "all" or (c.get("holdout", False) == (args.split == "holdout"))]
    missing = [c["file"] for c in cases if not (EVALS / c["file"]).is_file()]
    if missing:
        print(f"ERROR: labeled files missing on disk: {missing}")
        return 1

    from gemma import classify, load_model  # heavy import after cheap checks

    load_model()
    rows = []
    hdr = f"{'file':34} {'label':10} {'pred':10} {'ok':3} {'category':20} {'lat':>5}  content"
    print(hdr + "\n" + "-" * len(hdr))
    for c in cases:
        r = classify(str(EVALS / c["file"]))
        row = {**c, "pred": r["state"], "category": r["category"], "app": r["app"], "content": r["content"],
               "latency_s": r["latency_s"], "raw": r["raw"], "correct": r["state"] == c["label"]}
        rows.append(row)
        flag = "" if row["correct"] else "X"
        amb = "~" if c.get("ambiguous") else " "
        print(f"{amb}{c['file'][-33:]:33} {c['label']:10} {r['state']:10} {flag:3} {r['category']:20} {r['latency_s']:5.2f}  {r['content'][:60]}")

    clear = [r for r in rows if not r.get("ambiguous")]
    held = [r for r in rows if r.get("holdout")]
    fr_all = [r for r in rows if r["label"] == "working" and r["pred"] == "distracted"]
    fr_clear = [r for r in fr_all if not r.get("ambiguous")]
    missed = [r for r in rows if r["label"] == "distracted" and r["pred"] == "working"]
    unparsed = [r for r in rows if r["category"] == "unparsed"]
    lats = [r["latency_s"] for r in rows]

    print("\n== summary ==")
    print(f"non-ambiguous accuracy: {acc(clear)}")
    print(f"held-out accuracy:      {acc(held)}   (non-ambiguous held-out: {acc([r for r in held if not r.get('ambiguous')])})")
    print(f"overall accuracy:       {acc(rows)}")
    print(f"confusion: working->working={sum(r['label']=='working' and r['pred']=='working' for r in rows)} "
          f"working->distracted(FALSE ROAST)={len(fr_all)} "
          f"distracted->distracted={sum(r['label']=='distracted' and r['pred']=='distracted' for r in rows)} "
          f"distracted->working(missed)={len(missed)}")
    print(f"FALSE ROASTS on non-ambiguous: {len(fr_clear)} {[r['file'] for r in fr_clear]}")
    print(f"unparsed (fail-open): {len(unparsed)}")
    if lats:
        print(f"latency p50={statistics.median(lats):.2f}s p95={pct(lats, 95):.2f}s max={max(lats):.2f}s n={len(lats)}")
    for r in rows:
        if not r["correct"]:
            print(f"  FAIL {r['file']} label={r['label']} cat={r['category']} raw={r['raw']!r}")

    clear_acc = sum(r["correct"] for r in clear) / len(clear) if clear else 0.0
    # Overall accuracy alone let a "never flag entertainment" regression pass (21/23); gate distracted recall too.
    clear_d = [r for r in clear if r["label"] == "distracted"]
    recall_d = sum(r["correct"] for r in clear_d) / len(clear_d) if clear_d else 1.0
    print(f"distracted recall (non-ambiguous): {recall_d:.3f} (min {MIN_ACC})")
    out = "results.json" if args.labels == "labels.json" else f"results_{Path(args.labels).stem}.json"
    (EVALS / out).write_text(json.dumps({
        "split": args.split,
        "non_ambiguous_accuracy": clear_acc,
        "distracted_recall_non_ambiguous": recall_d,
        "overall_accuracy": sum(r["correct"] for r in rows) / len(rows) if rows else 0.0,
        "holdout_accuracy": sum(r["correct"] for r in held) / len(held) if held else None,
        "false_roasts_non_ambiguous": [r["file"] for r in fr_clear],
        "false_roasts_all": [r["file"] for r in fr_all],
        "latency_p50": statistics.median(lats) if lats else None,
        "latency_p95": pct(lats, 95) if lats else None,
        "cases": rows,
    }, indent=2))

    if clear_acc < MIN_ACC or fr_clear or recall_d < MIN_ACC:
        print(f"\nRED: non-ambiguous accuracy {clear_acc:.3f} / distracted recall {recall_d:.3f} "
              f"(min {MIN_ACC}) / false roasts {len(fr_clear)}")
        return 1
    print("\nGREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
