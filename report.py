"""Summarize ApexCompanion session logs: focus, roasts, errors, and per-stage latency (p50/p95).

Usage: python report.py [--dir LOGS] [--all] [--json]
Default dir: ./logs, or ~/Library/Application Support/ApexCompanion/logs for the packaged app.
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

APP_LOGS = Path.home() / "Library/Application Support/ApexCompanion/logs"
STAGES = ("rules_s", "capture_s", "classify_s", "roast_s", "total_s")


def read_events(path: Path) -> list[dict]:
    events = []
    for raw in path.read_text(errors="replace").splitlines():
        try:
            e = json.loads(raw)
        except json.JSONDecodeError:
            continue  # a line cut off by a hard kill; skip it rather than lose the session
        if not isinstance(e, dict):
            continue
        if "event" not in e:  # pre-schema logs: check rows had "state", failures had "error"
            e["event"] = "error" if "error" in e else "check"
        events.append(e)
    return events


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1]


def summarize(events: list[dict]) -> dict:
    checks = [e for e in events if e["event"] == "check"]
    errors = [e for e in events if e["event"] == "error"]
    start = next((e for e in events if e["event"] == "session_start"), {})
    ready = next((e for e in events if e["event"] == "model_ready"), {})
    end = next((e for e in events if e["event"] == "session_end"), {})
    n = len(checks)
    working = sum(c.get("state") == "working" for c in checks)
    latency = {}
    for stage in STAGES:
        vals = [c["timing"][stage] for c in checks if isinstance(c.get("timing"), dict) and stage in c["timing"]]
        if stage == "classify_s" and not vals:  # pre-schema logs only recorded the classify latency
            vals = [c["latency_s"] for c in checks if c.get("category") != "rule" and "latency_s" in c]
        if vals:
            latency[stage] = {"p50": round(pct(vals, 50), 3), "p95": round(pct(vals, 95), 3), "n": len(vals)}
    return {
        "session": start.get("session") or (events[0].get("session") if events else None),
        "started": events[0]["t"] if events else None,
        "persona": start.get("persona"),
        "mode": start.get("mode"),
        "duration_s": end.get("duration_s") or (round(events[-1]["t"] - events[0]["t"], 1) if len(events) > 1 else 0),
        "checks": n,
        "focus_pct": round(100 * working / n, 1) if n else None,
        "roasts": sum(c.get("action") == "roast" for c in checks),
        "praise": sum(c.get("action") == "praise" for c in checks),
        "rule_decided": sum(bool(c.get("rule")) for c in checks),
        "guard_fired": sum(bool(c.get("guarded")) for c in checks),
        "unparsed": sum(c.get("category") == "unparsed" for c in checks),
        "errors": len(errors),
        "errors_by_stage": dict(Counter(e.get("stage", "unknown") for e in errors)),
        "latency": latency,
        "load_s": ready.get("load_s"),
        "peak_rss_mb": end.get("peak_rss_mb") or ready.get("rss_mb"),
        "ended_cleanly": bool(end),
    }


def render(s: dict) -> str:
    def rate(k: int) -> str:
        return f"{k} ({100 * k / s['checks']:.1f}%)" if s["checks"] else str(k)

    lat = " · ".join(f"{k[:-2]} {v['p50']:.2f}/{v['p95']:.2f}s" for k, v in s["latency"].items()) or "none"
    errs = ", ".join(f"{k} {v}" for k, v in s["errors_by_stage"].items())
    lines = [
        f"session {s['session'] or '?'} · {s['persona'] or '?'} · {s['mode'] or '?'} · {s['duration_s'] / 60:.1f} min"
        + ("" if s["ended_cleanly"] else " · did not end cleanly"),
        f"checks {s['checks']} · focused {s['focus_pct'] if s['focus_pct'] is not None else '?'}% · roasts {s['roasts']}"
        f" · praise {s['praise']} · rule-decided {rate(s['rule_decided'])} · word filter fired {s['guard_fired']}",
        f"errors {rate(s['errors'])}"
        + (f": {errs}" if errs else "")
        + f" · unparsed model output {rate(s['unparsed'])}",
        f"latency p50/p95: {lat}",
    ]
    if s["load_s"] or s["peak_rss_mb"]:
        lines.append(f"model load {s['load_s']}s · peak memory {s['peak_rss_mb']} MB")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, help="log directory (default: ./logs, else the app's log folder)")
    ap.add_argument("--all", action="store_true", help="every session, not just the latest")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    log_dir = args.dir or (Path(__file__).parent / "logs" if (Path(__file__).parent / "logs").is_dir() else APP_LOGS)
    files = sorted(log_dir.glob("session-*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        print(f"no session logs in {log_dir}", file=sys.stderr)
        return 1
    summaries = [summarize(read_events(f)) for f in (files if args.all else files[-1:])]
    if args.json:
        print(json.dumps(summaries if args.all else summaries[0], indent=2))
    else:
        print("\n\n".join(render(s) for s in summaries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
