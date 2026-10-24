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


def run_main(
    monkeypatch,
    tmp_path,
    *,
    checks,
    shots=(),
    verdict=WORKING,
    front_app="Terminal",
    url="",
    sites="",
    mute=True,
    args=(),
    state_dir=None,
    meeting=False,
    clock_step=0.0,
    on_start=None,
    on_sleep=None,
):
    """Run main() for `checks` sleeps (one per check or paused tick). `shots` scripts screencapture: True writes a
    frame, False fails. The wall clock is frozen except that each sleep advances it by `clock_step` seconds.
    `on_start` runs once the model is loaded (after stale control files are cleared); `on_sleep(n)` before sleep n."""
    seen = {"screencapture": [], "classify": [], "roast_prompt": [], "notify": [], "say": []}
    shots = list(shots)

    def fake_run(cmd, **kw):
        if cmd[0] == "screencapture":
            seen["screencapture"].append(cmd[-1])
            ok = shots.pop(0) if shots else True
            if ok:
                Path(cmd[-1]).write_bytes(b"\xff\xd8 frame")
            return subprocess.CompletedProcess(cmd, 0 if ok else 1)
        return subprocess.CompletedProcess(cmd, 0)  # sips

    class FakeSay:
        def __init__(self, cmd, **kw):
            seen["say"].append(cmd[-1])

        def poll(self):
            return 0

        def wait(self):
            return 0

    def classify(path):
        seen["classify"].append((path, Path(path).exists()))
        return dict(verdict)

    fake_gemma = types.ModuleType("gemma")
    fake_gemma.MODEL_ID = "fake-model"
    fake_gemma.load_model = on_start or (lambda: None)
    fake_gemma.classify = classify
    fake_gemma.generate_text = lambda prompt, **kw: seen["roast_prompt"].append(prompt) or "Back to work."
    monkeypatch.setitem(sys.modules, "gemma", fake_gemma)
    monkeypatch.setattr(apex.subprocess, "run", fake_run)
    monkeypatch.setattr(apex.subprocess, "Popen", FakeSay)
    monkeypatch.setattr(apex, "warm_up", lambda g: None)
    monkeypatch.setattr(apex, "notify", lambda text, title: seen["notify"].append(text))
    monkeypatch.setattr(apex, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(rules, "front_app", lambda: front_app)
    monkeypatch.setattr(rules, "front_url", lambda app: url)
    monkeypatch.setattr(rules, "in_meeting", lambda app, u: meeting, raising=False)
    monkeypatch.setenv("APEX_SCREEN_OK", "1")

    clock = [1_800_000_000.0]
    sleeps = []

    def fake_sleep(s):  # Ctrl-C is main's normal exit
        sleeps.append(s)
        if on_sleep:
            on_sleep(len(sleeps))
        clock[0] += clock_step
        if len(sleeps) >= checks:
            raise KeyboardInterrupt

    monkeypatch.setattr(apex.time, "sleep", fake_sleep)
    monkeypatch.setattr(apex.time, "time", lambda: clock[0])
    sites_path = tmp_path / "sites.txt"
    sites_path.write_text(sites)
    argv = ["apex.py", "--interval", "0", "--streak", "1", "--cooldown", "0", "--sites", str(sites_path)]
    argv += ["--mute"] if mute else []
    argv += ["--state-dir", str(state_dir)] if state_dir else []
    monkeypatch.setattr(sys, "argv", argv + list(args))
    apex.main()
    (log_path,) = (tmp_path / "logs").glob("session-*.jsonl")
    seen["events"] = [json.loads(line) for line in log_path.read_text().splitlines()]
    seen["log"] = [e for e in seen["events"] if e["event"] in ("check", "error")]
    seen["log_path"] = log_path
    seen["sleeps"] = sleeps
    if state_dir:
        seen["state"] = json.loads((state_dir / "state.json").read_text())
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


DISTRACTED = {**WORKING, "app": "YouTube", "content": "cat compilation", "category": "entertainment"}
DISTRACTED["state"] = "distracted"


def write_control(state_dir, **values):
    (state_dir / "control.json").write_text(json.dumps(values))


def test_pause_skips_capture_and_model(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    seen = run_main(
        monkeypatch,
        tmp_path,
        checks=3,
        state_dir=sd,
        on_start=lambda: write_control(sd, paused_until=apex.time.time() + 3600),
    )
    assert seen["screencapture"] == [] and seen["classify"] == [] and seen["log"] == []
    assert len(seen["sleeps"]) == 3  # still ticking, just not looking


def test_pause_resumes_after_paused_until(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    pause = lambda: write_control(sd, paused_until=apex.time.time() + 15)  # noqa: E731
    seen = run_main(monkeypatch, tmp_path, checks=3, state_dir=sd, clock_step=10, on_start=pause)
    assert len(seen["screencapture"]) == 1 and len(seen["classify"]) == 1  # paused, paused, then one real check
    assert seen["state"]["paused_until"] is None


def test_paused_state_is_published(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    states = []

    def record(n):
        states.append(json.loads((sd / "state.json").read_text())["state"])

    pause = lambda: write_control(sd, paused_until=apex.time.time() + 3600)  # noqa: E731
    run_main(monkeypatch, tmp_path, checks=2, state_dir=sd, on_start=pause, on_sleep=record)
    assert states == ["paused", "paused"]


def test_mute_suppresses_voice_but_not_notification(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    seen = run_main(
        monkeypatch,
        tmp_path,
        checks=1,
        verdict=DISTRACTED,
        mute=False,
        state_dir=sd,
        on_start=lambda: write_control(sd, muted=True),
    )
    assert seen["notify"] == ["Back to work."] and seen["say"] == []
    assert seen["state"]["muted"] is True


def test_unmuted_roast_is_spoken(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=1, verdict=DISTRACTED, mute=False, state_dir=tmp_path / "state")
    assert seen["say"] == ["Back to work."] and seen["state"]["last_line"] == "Back to work."


def test_stop_flag_ends_session_cleanly(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    stop = lambda n: write_control(sd, stop=True)  # noqa: E731
    seen = run_main(monkeypatch, tmp_path, checks=5, state_dir=sd, on_sleep=stop)
    assert len(seen["log"]) == 1  # the tick in progress finished; no new one started
    assert seen["events"][-1]["event"] == "session_end" and seen["events"][-1]["stop_reason"] == "user"
    assert (seen["state"]["state"], seen["state"]["stop_reason"]) == ("stopped", "user")


def test_timer_ends_session(monkeypatch, tmp_path):
    seen = run_main(
        monkeypatch,
        tmp_path,
        checks=10,
        mute=False,
        state_dir=tmp_path / "state",
        clock_step=60,
        args=["--minutes", "3"],
    )
    assert len(seen["log"]) == 3
    assert seen["notify"] == ["Session done: 2 min focused."] == seen["say"]
    assert (seen["state"]["state"], seen["state"]["stop_reason"]) == ("stopped", "timer")
    assert seen["state"]["ends_at"] == seen["events"][0]["t"] + 180
    assert seen["events"][-1]["stop_reason"] == "timer"


def test_timer_voice_respects_mute(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=10, clock_step=60, args=["--minutes", "2"])
    assert seen["notify"] == ["Session done: 1 min focused."] and seen["say"] == []


def test_stale_control_file_is_removed_at_start(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    sd.mkdir()
    write_control(sd, stop=True, muted=True)
    seen = run_main(monkeypatch, tmp_path, checks=2, mute=False, state_dir=sd)
    assert len(seen["log"]) == 2 and not (sd / "control.json").exists()
    assert seen["state"]["stop_reason"] is None and seen["state"]["muted"] is False


def test_state_file_is_owner_only_and_complete(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    seen = run_main(
        monkeypatch, tmp_path, checks=2, state_dir=sd, args=["--goal", "write\nthe parser", "--minutes", "0"]
    )
    assert (sd / "state.json").stat().st_mode & 0o777 == 0o600
    st = seen["state"]
    keys = {"schema", "t", "session", "persona", "goal", "state", "focused_s", "elapsed_s", "ends_at"}
    keys |= {"paused_until", "muted", "roasts", "last_line", "stop_reason"}
    assert set(st) == keys
    assert (st["schema"], st["state"], st["goal"], st["ends_at"]) == (1, "stopped", "write the parser", None)
    assert st["session"] == seen["events"][0]["session"]
    assert [p.name for p in sd.iterdir()] == ["state.json"]  # no temp file left behind


def test_no_state_dir_writes_nothing(monkeypatch, tmp_path):
    run_main(monkeypatch, tmp_path, checks=1)
    assert not list(tmp_path.glob("**/state.json"))


def test_meeting_skips_capture_model_and_roast(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    seen = run_main(monkeypatch, tmp_path, checks=2, verdict=DISTRACTED, meeting=True, mute=False, state_dir=sd)
    assert seen["screencapture"] == [] and seen["classify"] == [] and seen["roast_prompt"] == []
    assert seen["notify"] == [] and seen["say"] == []
    rec = seen["log"][0]
    assert (rec["category"], rec["state"], rec["action"]) == ("meeting", "working", None)
    assert seen["events"][-1]["focus_pct"] == 100.0


def test_meeting_state_is_published(monkeypatch, tmp_path):
    sd = tmp_path / "state"
    states = []
    record = lambda n: states.append(json.loads((sd / "state.json").read_text())["state"])  # noqa: E731
    run_main(monkeypatch, tmp_path, checks=1, meeting=True, state_dir=sd, on_sleep=record)
    assert states == ["meeting"]


def test_praise_is_never_spoken_or_notified(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=2, mute=False, args=["--praise-every", "1"])
    assert len(seen["roast_prompt"]) == 2  # opted in, so the line is generated...
    assert seen["notify"] == [] and seen["say"] == []  # ...but only logged
    assert [e["action"] for e in seen["log"]] == ["praise", "praise"] and seen["log"][0]["line"] == "Back to work."
    assert seen["events"][-1]["praises"] == 2


def test_praise_is_off_by_default(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=3)
    assert seen["roast_prompt"] == [] and apex.Coach().praise_every == 0


def test_goal_reaches_the_roast_prompt(monkeypatch, tmp_path):
    seen = run_main(monkeypatch, tmp_path, checks=1, verdict=DISTRACTED, args=["--goal", "finish the tax return"])
    assert "They said they'd be working on: finish the tax return." in seen["roast_prompt"][0]
