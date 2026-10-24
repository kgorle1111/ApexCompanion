import json
import os

import pytest

import control


def test_state_write_is_owner_only_and_replaces(tmp_path):
    path = tmp_path / "state.json"
    control.write_state(path, {"state": "working"})
    control.write_state(path, {"state": "paused"})
    assert json.loads(path.read_text()) == {"state": "paused"}
    assert path.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_failed_state_write_leaves_old_file_and_no_temp(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    control.write_state(path, {"state": "working"})

    def half_written(obj, f):
        f.write('{"state": "pau')
        raise OSError("disk full")

    monkeypatch.setattr(control.json, "dump", half_written)
    with pytest.raises(OSError):
        control.write_state(path, {"state": "paused"})
    assert json.loads(path.read_text()) == {"state": "working"}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


@pytest.mark.parametrize("text", ["", "{", "[]", "null", '"stop"'])
def test_invalid_control_is_defaults(text):
    assert control.parse_control(text) == control.DEFAULTS


def test_control_fields_must_have_the_right_type():
    parsed = control.parse_control(json.dumps({"paused_until": "soon", "muted": "true", "stop": 1}))
    assert parsed == control.DEFAULTS
    parsed = control.parse_control(json.dumps({"paused_until": 1700000000, "muted": True, "stop": True}))
    assert parsed == {"paused_until": 1700000000.0, "muted": True, "stop": True}
    assert control.parse_control(json.dumps({"paused_until": True}))["paused_until"] is None


def test_control_reloads_on_change_and_resets_when_deleted(tmp_path):
    path = tmp_path / "control.json"
    ctl = control.Control(path)
    assert ctl.current() == control.DEFAULTS
    path.write_text(json.dumps({"muted": True}))
    assert ctl.current()["muted"] is True
    path.write_text(json.dumps({"muted": False, "stop": True}))
    os.utime(path, ns=(1, 1))  # a new mtime even on a coarse-clock filesystem
    assert ctl.current() == {"paused_until": None, "muted": False, "stop": True}
    path.unlink()
    assert ctl.current() == control.DEFAULTS


def test_paused_only_before_paused_until(tmp_path):
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"paused_until": 100}))
    ctl = control.Control(path)
    assert ctl.paused(99.9) and not ctl.paused(100)


def test_remove_stale_deletes_file_and_forgets_values(tmp_path):
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"stop": True}))
    ctl = control.Control(path)
    assert ctl.current()["stop"]
    ctl.remove_stale()
    assert not path.exists() and ctl.current() == control.DEFAULTS
    ctl.remove_stale()  # already gone is fine


def test_goal_is_one_line_and_capped():
    assert control.clean_goal("  write\nthe\r\n parser ") == "write the parser"
    assert len(control.clean_goal("x" * 500)) == control.GOAL_MAX
    assert control.clean_goal(None) == ""
