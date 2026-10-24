import json

import report


def _write(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def _check(t, state, total, **kw):
    timing = {"rules_s": 0.01, "capture_s": 0.2, "classify_s": total - 0.21, "total_s": total}
    return {"t": t, "event": "check", "session": "s1", "state": state, "timing": timing, **kw}


def test_summary_counts_and_percentiles(tmp_path):
    events = [
        {"t": 0, "event": "session_start", "session": "s1", "persona": "whip", "mode": "screen"},
        {"t": 1, "event": "model_ready", "session": "s1", "load_s": 3.6, "rss_mb": 9000},
        _check(2, "working", 1.0),
        _check(3, "distracted", 1.2),
        _check(4, "distracted", 1.4, action="roast", guarded=True),
        _check(5, "working", 1.1, rule="github", category="rule"),
        {"t": 6, "event": "error", "session": "s1", "stage": "capture", "error": "RuntimeError()"},
        {"t": 7, "event": "session_end", "session": "s1", "duration_s": 7.0, "peak_rss_mb": 11200},
    ]
    s = report.summarize(events)
    assert (s["checks"], s["focus_pct"], s["roasts"], s["rule_decided"], s["guard_fired"]) == (4, 50.0, 1, 1, 1)
    assert s["errors_by_stage"] == {"capture": 1} and s["ended_cleanly"]
    assert s["latency"]["total_s"]["p50"] == 1.15 and s["latency"]["total_s"]["n"] == 4
    assert s["peak_rss_mb"] == 11200


def test_reads_pre_schema_logs_and_skips_truncated_lines(tmp_path):
    p = tmp_path / "session-old.jsonl"
    p.write_text(
        json.dumps({"t": 1, "state": "working", "category": "coding", "latency_s": 0.8})
        + "\n"
        + json.dumps({"t": 2, "error": "boom"})
        + "\n"
        + '{"t": 3, "state": "dis'  # cut off by a hard kill
    )
    s = report.summarize(report.read_events(p))
    assert (s["checks"], s["errors"], s["ended_cleanly"]) == (1, 1, False)
    assert s["latency"]["classify_s"]["p50"] == 0.8


def test_render_is_one_screen(tmp_path):
    s = report.summarize([_check(1, "working", 1.0)])
    out = report.render(s)
    assert "checks 1" in out and "latency p50/p95" in out and len(out.splitlines()) <= 6
