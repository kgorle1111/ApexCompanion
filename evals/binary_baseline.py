"""A/B baseline: a yes/no prompt vs the shipped describe-then-categorize pipeline.

Two yes/no prompts: "fair" lists the same working/distracted coverage as the shipped category map (the headline
comparison); "original" is the narrower first-version rubric (entertainment and social media only).

Runs the chosen prompt over the clear-cut (non-ambiguous) cases of evals/labels.json and evals/labels2.json,
compares with the shipped results in evals/results.json and evals/results_labels2.json, prints a table and a
summary, and updates that prompt's entry in evals/results_binary_baseline.json (the other entry is kept).
labels2.json is the blind batch (captured after tuning).

Usage: .venv/bin/python evals/binary_baseline.py [--prompt fair|original] [--images-root DIR]
The screenshots are git-ignored; point --images-root at an evals/ dir that has web/ and web2/.
"""

import argparse
import json
import re
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS.parent))  # gemma.py lives at the repo root

_REPLY = 'Reply ONLY JSON: {"state":"working" or "distracted","reason":"<8 words describing what is on screen>"}'
PROMPTS = {
    "fair": (
        "Look at this screenshot of a student laptop. Working = coding, reading docs or articles, notes, messaging, "
        "news, or an educational video. Distracted = entertainment video, social media, shopping, gaming, a feed of "
        "recommended videos/images/posts, or sports. Ignore ads, banners and pop-ups. " + _REPLY
    ),
    "original": (
        "Look at this screenshot of a student laptop. Coding, docs, notes and educational videos count as working; "
        "entertainment and social media count as distracted. " + _REPLY
    ),
}
OUT = EVALS / "results_binary_baseline.json"
# (labels file, shipped results file, is the blind batch)
BATCHES = [("labels.json", "results.json", False), ("labels2.json", "results_labels2.json", True)]


def parse_state(raw: str) -> str:
    """Same fail-open as shipped: anything not clearly "distracted" counts as working."""
    m = re.search(r'"state"\s*:\s*"(working|distracted)"', raw, re.I)
    return m.group(1).lower() if m else "working"


def parse_reason(raw: str) -> str:
    m = re.search(r'"reason"\s*:\s*"([^"]*)', raw)
    return m.group(1) if m else ""


def summarize(rows: list[dict], key: str) -> dict:
    distracted = [r for r in rows if r["label"] == "distracted"]
    return {
        "n": len(rows),
        "correct": sum(r[key] == r["label"] for r in rows),
        "distracted_n": len(distracted),
        "distracted_caught": sum(r[key] == "distracted" for r in distracted),
        "false_roasts": [r["file"] for r in rows if r["label"] == "working" and r[key] == "distracted"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default="fair", help="fair = same coverage as shipped")
    ap.add_argument("--images-root", type=Path, default=EVALS, help="evals/ dir holding web/ and web2/ screenshots")
    args = ap.parse_args()

    cases = []
    for labels_name, results_name, blind in BATCHES:
        shipped = {c["file"]: c["pred"] for c in json.loads((EVALS / results_name).read_text())["cases"]}
        for c in json.loads((EVALS / labels_name).read_text()):
            if not c.get("ambiguous"):
                cases.append(
                    {"file": c["file"], "label": c["label"], "blind": blind, "shipped_state": shipped[c["file"]]}
                )

    missing = [c["file"] for c in cases if not (args.images_root / c["file"]).is_file()]
    if missing:
        print(f"ERROR: {len(missing)} screenshots missing under {args.images_root}: {missing[:3]}...")
        return 1

    import gemma  # heavy import after cheap checks

    prompt = PROMPTS[args.prompt]
    gemma.load_model()
    print(f"prompt: {args.prompt}")
    hdr = f"{'file':34} {'label':10} {'binary':10} {'shipped':10}  binary reason"
    print(hdr + "\n" + "-" * len(hdr))
    for c in cases:
        raw = gemma._run(prompt, str(args.images_root / c["file"]), max_tokens=60, temperature=0.0)
        c["binary_state"] = parse_state(raw)
        c["binary_reason"] = parse_reason(raw)
        c["binary_raw"] = raw[:200]
        flag = "X" if c["binary_state"] != c["label"] else " "
        print(
            f"{flag}{c['file'][-33:]:33} {c['label']:10} {c['binary_state']:10} {c['shipped_state']:10}  {c['binary_reason'][:60]}"
        )

    blind = [c for c in cases if c["blind"]]
    summary = {
        name: {"binary": summarize(rows, "binary_state"), "shipped": summarize(rows, "shipped_state")}
        for name, rows in (("overall", cases), ("blind_batch_only", blind))
    }
    print("\n== summary (clear-cut cases) ==")
    for name, s in summary.items():
        for arm in ("binary", "shipped"):
            x = s[arm]
            print(
                f"{name:17} {arm:8} correct {x['correct']}/{x['n']}  distracted caught "
                f"{x['distracted_caught']}/{x['distracted_n']}  false roasts {len(x['false_roasts'])} {x['false_roasts']}"
            )

    variants = json.loads(OUT.read_text()).get("variants", {}) if OUT.is_file() else {}
    variants[args.prompt] = {"prompt": prompt, "summary": summary, "cases": cases}
    OUT.write_text(
        json.dumps(
            {
                "model": f"{gemma.MODEL_ID}@{gemma.MODEL_REVISION}",
                "max_tokens": 60,
                "temperature": 0.0,
                "shipped_source": [r for _, r, _ in BATCHES],
                "variants": dict(sorted(variants.items())),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nwrote {args.prompt!r} to {OUT.relative_to(EVALS.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
