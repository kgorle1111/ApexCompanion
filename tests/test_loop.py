"""The live loop in apex.main, driven end to end with the model, screen, browser and speech stubbed out."""

import json
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
    seen["log"] = [json.loads(line) for line in log_path.read_text().splitlines()]
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
