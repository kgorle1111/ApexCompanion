"""The live loop in apex.main, driven end to end with the model, screen, browser and speech stubbed out."""

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

import apex
import rules

WORKING = {"app": "VS Code", "content": "editing apex.py", "category": "coding", "state": "working", "latency_s": 0.1}


def run_main(monkeypatch, tmp_path, *, checks, shots=(), verdict=WORKING, front_app="Terminal", url="", sites=""):
    """Run main() for `checks` iterations. `shots` scripts screencapture: True writes a frame, False fails."""
    seen = {"screencapture": [], "classify": [], "roast_prompt": []}
    shots = list(shots)

    def fake_run(cmd, **kw):
        if cmd[0] == "screencapture":
            seen["screencapture"].append(cmd[-1])
            ok = shots.pop(0) if shots else True
            if ok:
                Path(cmd[-1]).write_bytes(b"\xff\xd8 frame")
            return subprocess.CompletedProcess(cmd, 0 if ok else 1)
        return subprocess.CompletedProcess(cmd, 0)  # sips

    def classify(path):
        seen["classify"].append((path, Path(path).exists()))
        return dict(verdict)

    fake_gemma = types.ModuleType("gemma")
    fake_gemma.MODEL_ID = "fake-model"
    fake_gemma.load_model = lambda: None
    fake_gemma.classify = classify
    fake_gemma.generate_text = lambda prompt, **kw: seen["roast_prompt"].append(prompt) or "Back to work."
    monkeypatch.setitem(sys.modules, "gemma", fake_gemma)
    monkeypatch.setattr(apex.subprocess, "run", fake_run)
    monkeypatch.setattr(apex, "warm_up", lambda g: None)
    monkeypatch.setattr(apex, "notify", lambda text, title: None)
    monkeypatch.setattr(apex, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(rules, "front_app", lambda: front_app)
    monkeypatch.setattr(rules, "front_url", lambda app: url)
    monkeypatch.setenv("APEX_SCREEN_OK", "1")

    sleeps = []

    def fake_sleep(s):  # one sleep per check, success or failure; Ctrl-C is main's normal exit
        sleeps.append(s)
        if len(sleeps) >= checks:
            raise KeyboardInterrupt

    monkeypatch.setattr(apex.time, "sleep", fake_sleep)
    sites_path = tmp_path / "sites.txt"
    sites_path.write_text(sites)
    argv = ["apex.py", "--mute", "--interval", "0", "--streak", "1", "--cooldown", "0", "--sites", str(sites_path)]
    monkeypatch.setattr(sys, "argv", argv)
    apex.main()
    (log_path,) = (tmp_path / "logs").glob("session-*.jsonl")
    seen["events"] = [json.loads(line) for line in log_path.read_text().splitlines()]
    seen["log"] = [e for e in seen["events"] if e["event"] in ("check", "error")]
    seen["log_path"] = log_path
    return seen


def test_capture_failure_raises_a_catchable_error(monkeypatch, tmp_path):
    monkeypatch.setattr(apex.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1))
    with pytest.raises(RuntimeError, match="screencapture failed"):
        apex.capture(str(tmp_path / "shot.jpg"))


def test_failed_capture_skips_one_check_not_the_session(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=2, shots=[False, True])
    assert len(seen["screencapture"]) == 2
    assert len(seen["classify"]) == 1
    assert "screencapture failed" in seen["log"][0]["error"]
    assert seen["log"][1]["state"] == "working"
    assert not Path(seen["screencapture"][0]).exists()  # no frame outlives its check


def test_on_screen_text_cannot_trigger_a_rule(monkeypatch, tmp_path):
    # A terminal printing "netflix" is still work: the model read it, but rules only see app + URL.
    terminal = {**WORKING, "app": "Netflix", "content": "curl https://netflix.com in a terminal"}
    sites = "[distracting]\nnetflix\n"
    seen = run_main(monkeypatch, tmp_path, checks=1, verdict=terminal, front_app="Terminal", sites=sites)
    assert (seen["log"][0]["state"], seen["log"][0]["rule"]) == ("working", None)


def test_on_screen_text_cannot_suppress_a_verdict(monkeypatch, tmp_path):
    # A "3Blue1Brown" link in a sidebar doesn't make the cat video next to it OK.
    cats = {"app": "YouTube", "content": "cat video, 3Blue1Brown in sidebar", "category": "entertainment"}
    cats |= {"state": "distracted", "latency_s": 0.1}
    url = "https://www.youtube.com/watch?v=cats"
    seen = run_main(
        monkeypatch, tmp_path, checks=1, verdict=cats, front_app="Safari", url=url, sites="[ok]\n3blue1brown\n"
    )
    assert (seen["log"][0]["state"], seen["log"][0]["rule"]) == ("distracted", None)


def test_rule_hit_skips_screenshot_and_model(monkeypatch, tmp_path):
    url = "https://www.reddit.com/r/funny/"
    seen = run_main(monkeypatch, tmp_path, checks=1, front_app="Safari", url=url, sites="[distracting]\nreddit\n")
    assert seen["screencapture"] == [] and seen["classify"] == []
    rec = seen["log"][0]
    assert (rec["state"], rec["rule"], rec["category"], rec["action"]) == ("distracted", "reddit", "rule", "roast")
    assert "Screen: Safari - www.reddit.com" in seen["roast_prompt"][0]  # the roast still names the site


def test_shorts_guard_needs_no_model(monkeypatch, tmp_path):
    url = "https://www.youtube.com/shorts/abc"
    seen = run_main(monkeypatch, tmp_path, checks=1, front_app="Google Chrome", url=url)
    assert seen["classify"] == []
    assert (seen["log"][0]["state"], seen["log"][0]["rule"]) == ("distracted", "youtube.com/shorts")


def test_rule_miss_still_asks_the_model(monkeypatch, tmp_path):
    url = "https://docs.python.org/3/"
    seen = run_main(monkeypatch, tmp_path, checks=1, front_app="Safari", url=url, sites="[distracting]\nreddit\n")
    assert len(seen["classify"]) == 1 and seen["classify"][0][1]  # the frame existed while it was read
    assert not Path(seen["classify"][0][0]).exists()


def test_log_keeps_host_only_and_content_only_on_roast(monkeypatch, tmp_path):
    url = "https://mail.example.com/inbox/secret-thread?q=diagnosis"
    seen = run_main(monkeypatch, tmp_path, checks=1, front_app="Safari", url=url)
    raw = seen["log_path"].read_text()
    rec = seen["log"][0]
    assert rec["host"] == "mail.example.com" and "url" not in rec
    assert "secret-thread" not in raw and "diagnosis" not in raw
    assert rec["action"] is None and rec["content"] is None
    assert "editing apex.py" not in raw


def test_log_keeps_content_when_roasted(monkeypatch, tmp_path):
    cats = {**WORKING, "content": "cat compilation", "category": "entertainment", "state": "distracted"}
    seen = run_main(monkeypatch, tmp_path, checks=1, verdict=cats, front_app="Safari", url="https://example.com/")
    assert (seen["log"][0]["action"], seen["log"][0]["content"]) == ("roast", "cat compilation")


def test_log_file_is_owner_only(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=1)
    assert seen["log_path"].stat().st_mode & 0o777 == 0o600


def test_screen_description_stays_out_of_redirected_stdout(monkeypatch, tmp_path, capsys):
    # The packaged app sends stdout to apex.log; only a live terminal should see what was on screen.
    seen_text = {**WORKING, "content": "private chat with Sam about rent"}
    run_main(monkeypatch, tmp_path, checks=1, verdict=seen_text)
    assert "private chat" not in capsys.readouterr().out


def test_every_event_carries_session_and_schema(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=2)
    kinds = [e["event"] for e in seen["events"]]
    assert kinds[:2] == ["session_start", "model_ready"] and kinds[-1] == "session_end"
    assert len({e["session"] for e in seen["events"]}) == 1 and all(e["schema"] == apex.SCHEMA for e in seen["events"])


def test_check_records_stage_timings(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=1)
    timing = seen["log"][0]["timing"]
    assert {"rules_s", "capture_s", "classify_s", "total_s"} <= timing.keys()
    assert timing["total_s"] >= timing["capture_s"] + timing["rules_s"] - 1e-3


def test_failed_check_names_its_stage(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=2, shots=[False, True])
    err = seen["log"][0]
    assert (err["event"], err["stage"]) == ("error", "capture")
    assert seen["events"][-1]["errors"] == 1


def test_old_logs_are_pruned(tmp_path):
    old, new = tmp_path / "session-old.jsonl", tmp_path / "session-new.jsonl"
    old.write_text(""), new.write_text("")
    os.utime(old, (0, 0))
    assert apex.prune_logs(tmp_path, keep_days=7) == 1
    assert not old.exists() and new.exists()
