"""Runtime hardening: what keeps a broken, hung, duplicated or disk-starved coach from pretending to coach."""

import os
import subprocess
import time

import pytest
from test_loop import WORKING, run_main

import apex

# ---- the session log never kills a session


class FullDisk:
    def write(self, s):
        raise OSError(28, "No space left on device")

    def flush(self):
        raise OSError(28, "No space left on device")

    def close(self):
        raise OSError(28, "No space left on device")


def test_full_disk_warns_once_and_keeps_the_session(tmp_path, capsys):
    log = apex.EventLog(tmp_path / "s.jsonl", "abc")
    log.f.close()
    log.f = FullDisk()
    log.emit("check", n=1)
    log.emit("check", n=2)
    log.close()
    err = capsys.readouterr().err
    assert err.count("session log write failed") == 1 and "No space left" in err


# ---- every subprocess has a deadline


def fake_bin(tmp_path, monkeypatch, name, body="exec sleep 5"):
    """A real executable that shadows a system tool on PATH: real process, real hang."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tool = bin_dir / name
    tool.write_text(f"#!/bin/sh\n{body}\n")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")


def test_hung_screencapture_times_out(tmp_path, monkeypatch):
    fake_bin(tmp_path, monkeypatch, "screencapture")
    monkeypatch.setattr(apex, "SHOT_TIMEOUT_S", 0.3)
    t = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        apex.capture(str(tmp_path / "shot.jpg"))
    assert time.monotonic() - t < 3


def test_hung_sips_times_out(tmp_path, monkeypatch):
    fake_bin(tmp_path, monkeypatch, "screencapture", 'printf frame > "$4"')  # -x -t jpg PATH
    fake_bin(tmp_path, monkeypatch, "sips")
    monkeypatch.setattr(apex, "SHOT_TIMEOUT_S", 0.3)
    t = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        apex.capture(str(tmp_path / "shot.jpg"))
    assert time.monotonic() - t < 3


def test_hung_notification_is_swallowed(tmp_path, monkeypatch, capsys):
    fake_bin(tmp_path, monkeypatch, "osascript")
    monkeypatch.setattr(apex, "NOTIFY_TIMEOUT_S", 0.3)
    t = time.monotonic()
    apex.notify("Back to work.", "ApexCompanion")  # must return, not raise
    assert time.monotonic() - t < 3
    assert "notification timed out" in capsys.readouterr().err


def test_hung_say_is_killed_not_waited_on_forever(tmp_path, monkeypatch):
    fake_bin(tmp_path, monkeypatch, "say")
    monkeypatch.setattr(apex, "SAY_TIMEOUT_S", 0.3)
    voice = apex.Voice("Daniel", 200, mute=False)
    t = time.monotonic()
    voice.say("first")
    first = voice.proc
    voice.say("second")  # first is still "speaking"
    assert first.wait(timeout=2) == -9  # SIGKILLed
    voice.finish()  # the session-end wait
    assert voice.proc.wait(timeout=2) == -9
    assert time.monotonic() - t < 3


def test_session_end_does_not_wait_forever_on_say(monkeypatch, tmp_path):
    distracted = {**WORKING, "state": "distracted", "category": "entertainment"}
    seen = run_main(monkeypatch, tmp_path, checks=1, verdict=distracted, mute=False, hang_say=True)
    assert seen["say"] == ["Back to work."] and seen["killed"] == [True]
    assert seen["events"][-1]["event"] == "session_end"
