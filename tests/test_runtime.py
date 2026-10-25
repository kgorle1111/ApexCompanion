"""Runtime hardening: what keeps a broken, hung, duplicated or disk-starved coach from pretending to coach."""

import json
import os
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

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


# ---- one coach at a time


def test_second_coach_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    fd = apex.take_lock()
    try:
        with pytest.raises(SystemExit, match="already running; stop it from the menu bar first"):
            apex.take_lock()
    finally:
        os.close(fd)
    os.close(apex.take_lock())  # free again once the holder lets go


def test_lock_held_by_another_process_dies_with_it_even_on_sigkill(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, os, sys, time; fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT); "
            "fcntl.flock(fd, fcntl.LOCK_EX); print('locked', flush=True); time.sleep(30)",
            str(tmp_path / "apex.lock"),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        with pytest.raises(SystemExit, match="already running"):
            apex.take_lock()
    finally:
        holder.kill()
        holder.wait(timeout=5)
    os.close(apex.take_lock())  # no stale-pidfile cleanup needed


def test_running_coach_blocks_a_second_main(monkeypatch, tmp_path):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    fd = apex.take_lock()
    try:
        seen = run_main(monkeypatch, tmp_path, checks=1)
    finally:
        os.close(fd)
    assert "already running" in str(seen["exit"])
    assert seen["classify"] == [] and not (tmp_path / "logs").exists()  # refused before the model or a log


def test_lock_is_released_when_the_session_ends(monkeypatch, tmp_path):
    first = run_main(monkeypatch, tmp_path, checks=1)
    second = run_main(monkeypatch, tmp_path, checks=1)
    assert first["exit"] is None and second["exit"] is None


def test_replay_mode_takes_no_lock(monkeypatch, tmp_path):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    fd = apex.take_lock()
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8 frame")
    try:
        seen = run_main(monkeypatch, tmp_path, checks=5, args=["--image", str(img)])
    finally:
        os.close(fd)
    assert seen["exit"] is None and len(seen["classify"]) == 1


def test_startup_sweeps_frames_a_killed_coach_left_behind(monkeypatch, tmp_path):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    for name in ("apex_k1l13d.jpg", "apex_warmup.jpg", "holiday.jpg"):
        (tmp / name).write_bytes(b"\xff\xd8")
    seen = run_main(monkeypatch, tmp_path, checks=1)
    assert sorted(p.name for p in tmp.iterdir()) == ["apex.lock", "holiday.jpg"]
    assert seen["events"][0]["swept_frames"] == 2


def test_replay_mode_never_sweeps(monkeypatch, tmp_path):
    # No lock in replay mode, so a live screen coach may own that frame right now.
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    (tmp / "apex_live.jpg").write_bytes(b"\xff\xd8")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8 frame")
    run_main(monkeypatch, tmp_path, checks=1, args=["--image", str(img)])
    assert (tmp / "apex_live.jpg").exists()


# ---- broken-coach circuit breaker

UNPARSED = {"app": "", "content": "", "category": "unparsed", "state": "working", "latency_s": 0.1}
UNPARSED |= {"raw": "I cannot help with that", "raw_unparsed": "I cannot help with that"}


def test_six_failed_checks_in_a_row_stop_the_coach_loudly(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    seen = run_main(monkeypatch, tmp_path, checks=20, shots=[False] * 20, state_dir=sd)
    assert seen["exit"] == 3
    assert len(seen["screencapture"]) == apex.BREAKER  # stopped, not retrying forever
    st = seen["state"]
    assert (st["state"], st["stop_reason"]) == ("error", "error")
    assert "6 checks in a row failed" in st["last_line"] and "Screen Recording" in st["last_line"]
    assert seen["notify"] == [st["last_line"]]
    breaker = [e for e in seen["events"] if e.get("stage") == "breaker"]
    assert len(breaker) == 1 and "screencapture failed" in breaker[0]["error"]
    assert seen["events"][-1]["event"] == "session_end" and seen["events"][-1]["stop_reason"] == "error"


def test_unparsed_answers_trip_the_breaker(monkeypatch, tmp_path):
    # Unparsed fails open to "working": without the breaker a dead model reads as perfect focus.
    sd = tmp_path / "state"
    seen = run_main(monkeypatch, tmp_path, checks=20, verdict=UNPARSED, state_dir=sd)
    assert seen["exit"] == 3 and len(seen["classify"]) == apex.BREAKER
    assert seen["state"]["state"] == "error" and "model" in seen["state"]["last_line"]
    assert len(seen["state"]["last_line"]) <= 120
    breaker = [e for e in seen["events"] if e.get("stage") == "breaker"]
    assert "I cannot help with that" in breaker[0]["error"]


def test_failures_and_unparsed_answers_count_together(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=20, shots=[False] * 3, verdict=UNPARSED)
    assert seen["exit"] == 3 and len(seen["screencapture"]) == apex.BREAKER


def test_a_good_check_resets_the_breaker(monkeypatch, tmp_path):
    shots = [False] * 5 + [True] + [False] * 5
    seen = run_main(monkeypatch, tmp_path, checks=11, shots=shots, state_dir=tmp_path / "state")
    assert seen["exit"] is None and seen["state"]["state"] == "stopped"
    assert seen["events"][-1]["errors"] == 10


def test_a_rule_check_resets_the_breaker(monkeypatch, tmp_path):
    reddit, docs = "https://www.reddit.com/", "https://docs.python.org/"
    urls = [docs] * 5 + [reddit] + [docs] * 5
    seen = run_main(
        monkeypatch,
        tmp_path,
        checks=11,
        verdict=UNPARSED,
        front_app="Safari",
        url=urls,
        sites="[distracting]\nreddit\n",
    )
    assert seen["exit"] is None and len(seen["classify"]) == 10


def test_a_parsed_answer_resets_the_breaker(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=11, verdicts=[UNPARSED] * 5 + [WORKING] + [UNPARSED] * 5)
    assert seen["exit"] is None


def test_state_json_keeps_error_after_exit(monkeypatch, tmp_path):
    # The launcher reads state.json after exit code 3; "stopped" there would hide why.
    sd = tmp_path / "state"
    run_main(monkeypatch, tmp_path, checks=20, shots=[False] * 20, state_dir=sd)
    st = json.loads((sd / "state.json").read_text())
    assert st["state"] == "error" and st["last_line"].startswith("6 checks in a row failed")
    assert len(st["last_line"]) <= 120 and "\n" not in st["last_line"]  # the UI adds "Stopped: " itself


def test_model_failures_trip_the_breaker_with_a_log_hint(monkeypatch, tmp_path):
    crash = RuntimeError("metal device lost")
    seen = run_main(monkeypatch, tmp_path, checks=20, verdicts=[crash] * 20, state_dir=tmp_path / "state")
    assert seen["exit"] == 3 and len(seen["classify"]) == apex.BREAKER
    assert "check the logs" in seen["state"]["last_line"] and "Screen Recording" not in seen["state"]["last_line"]


# ---- --once reports failure in its exit code


def test_once_exits_nonzero_when_the_check_failed(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=5, shots=[False], args=["--once"])
    assert seen["exit"] == 1
    assert seen["events"][-1]["event"] == "session_end"  # cleanup still ran
    assert not list((tmp_path / "tmp").glob("apex_*.jpg"))


def test_once_exits_nonzero_on_an_unparsed_answer(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=5, verdict=UNPARSED, args=["--once"])
    assert seen["exit"] == 1


def test_once_exits_zero_on_a_good_check(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=5, args=["--once"])
    assert seen["exit"] is None and len(seen["log"]) == 1


# ---- Screen Recording preflight


def test_preflight_asks_coregraphics_directly():
    assert apex.screen_permission() in (True, False)  # a real answer, never "couldn't ask", on any Mac


def test_preflight_needs_no_developer_tools(monkeypatch):
    def no_subprocess(*a, **kw):
        raise AssertionError("preflight shelled out (swift needs Xcode tools and failed open without them)")

    monkeypatch.delenv("APEX_SCREEN_OK", raising=False)
    monkeypatch.setattr(apex.subprocess, "run", no_subprocess)
    monkeypatch.setattr(apex, "screen_permission", lambda: True)
    apex.require_screen_permission()


def test_missing_permission_refuses_to_start(monkeypatch):
    monkeypatch.delenv("APEX_SCREEN_OK", raising=False)
    monkeypatch.setattr(apex, "screen_permission", lambda: False)
    with pytest.raises(SystemExit, match="Screen Recording permission is missing"):
        apex.require_screen_permission()


def test_unloadable_coregraphics_warns_instead_of_bricking(monkeypatch, capsys):
    monkeypatch.delenv("APEX_SCREEN_OK", raising=False)
    monkeypatch.setattr(apex, "CORE_GRAPHICS", "/nonexistent/CoreGraphics")
    assert apex.screen_permission() is None
    apex.require_screen_permission()
    assert "couldn't verify Screen Recording permission" in capsys.readouterr().err


def test_app_bundle_skips_the_startup_check(monkeypatch):
    monkeypatch.setenv("APEX_SCREEN_OK", "1")
    monkeypatch.setattr(apex, "screen_permission", lambda: False)
    apex.require_screen_permission()


def scripted_permission(*answers):
    answers = list(answers)
    return lambda: answers.pop(0) if len(answers) > 1 else answers[0]


def test_permission_revoked_mid_session_stops_the_coach(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    seen = run_main(monkeypatch, tmp_path, checks=100, state_dir=sd, permission=scripted_permission(True, False))
    assert seen["exit"] == 3
    checks = [e for e in seen["log"] if e["event"] == "check"]
    assert len(checks) == apex.PERMISSION_EVERY - 1  # check 30 re-checked and stopped before capturing
    assert seen["state"]["state"] == "error" and "permission was turned off" in seen["state"]["last_line"]
    assert len(seen["state"]["last_line"]) <= 120


def test_recheck_passes_while_permission_holds(monkeypatch, tmp_path):
    calls = []
    seen = run_main(monkeypatch, tmp_path, checks=61, permission=lambda: calls.append(1) or True)
    assert seen["exit"] is None and len(calls) == 1 + 61 // apex.PERMISSION_EVERY  # baseline + one per 30


def test_recheck_ignored_when_this_process_never_saw_the_grant(monkeypatch, tmp_path):
    # Packaged app: the bundle owns the grant and checked it; this process may read False all along.
    seen = run_main(monkeypatch, tmp_path, checks=61, permission=lambda: False)
    assert seen["exit"] is None and len(seen["log"]) == 61


def test_replay_mode_never_rechecks(monkeypatch, tmp_path):
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8 frame")

    def no_check():
        raise AssertionError("replay mode needs no Screen Recording")

    seen = run_main(monkeypatch, tmp_path, checks=40, args=["--image", str(img)] * 40, permission=no_check)
    assert seen["exit"] is None and len(seen["classify"]) == 40


# ---- warm-up sanity


def test_warm_up_returns_the_verdict_and_leaves_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    fake = types.SimpleNamespace(classify=lambda path: {"category": "unparsed", "exists": Path(path).exists()})
    assert apex.warm_up(fake) == {"category": "unparsed", "exists": True}
    assert not list(tmp_path.iterdir())


def test_unparsed_warm_up_warns_loudly_but_runs(monkeypatch, tmp_path, capsys):
    warm = {**UNPARSED, "raw": "x" * 500}
    seen = run_main(monkeypatch, tmp_path, checks=2, warm=warm)
    assert "warm-up answer didn't parse" in capsys.readouterr().err
    (w,) = [e for e in seen["events"] if e["event"] == "warning"]
    assert w["stage"] == "warmup" and w["raw"] == "x" * 200
    assert seen["exit"] is None and len(seen["log"]) == 2


def test_parsed_warm_up_is_quiet(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=1)
    assert not [e for e in seen["events"] if e["event"] == "warning"]
