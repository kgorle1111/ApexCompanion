"""State/control files shared with the menu bar app: the coach writes state.json, the menu bar writes control.json."""

import json
import os
import re
import tempfile
from pathlib import Path

SCHEMA = 1
STATES = ("starting", "working", "distracted", "paused", "meeting", "stopped", "error")
GOAL_MAX = 120
DEFAULTS = {"paused_until": None, "muted": False, "stop": False}


def clean_goal(text: str | None) -> str:
    text = re.sub(r"\s+", " ", str(text or ""))
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text).strip()[:GOAL_MAX]


def write_state(path: Path, state: dict) -> None:
    """Atomic: the menu bar polls this file, so it must never see a half-written one."""
    # mkstemp creates the file 0600 in the target dir, so os.replace stays a same-filesystem rename.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _epoch(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def parse_control(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError:
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    # `is True`: a stray "false" string or 1 must not stop or mute a session.
    return {
        "paused_until": _epoch(data.get("paused_until")),
        "muted": data.get("muted") is True,
        "stop": data.get("stop") is True,
    }


class Control:
    """Reloads control.json when it changes; missing or invalid means defaults."""

    def __init__(self, path: Path, since: float | None = None):
        self.path = path
        self.since = since
        self.key: tuple[int, int] | None = None
        self.values = dict(DEFAULTS)

    def current(self) -> dict:
        try:
            st = self.path.stat()
        except OSError:
            self.key, self.values = None, dict(DEFAULTS)
            return self.values
        key = (st.st_mtime_ns, st.st_size)
        if key != self.key:
            try:
                text = self.path.read_text(errors="replace")
            except OSError:
                text = ""
            self.values, self.key = parse_control(text), key
            # A stop written before this session started belongs to the previous one. The file isn't deleted:
            # a Pause or Mute clicked while the model loads must still apply.
            if self.since is not None and st.st_mtime < self.since:
                self.values["stop"] = False
        return self.values

    def paused(self, now: float) -> bool:
        until = self.current()["paused_until"]
        return until is not None and now < until
