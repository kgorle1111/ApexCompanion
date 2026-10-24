"""User site/app rules: deterministic overrides on top of the model's verdict. The user always wins."""

import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

TEMPLATE = """\
# ApexCompanion: your sites and apps.
# One per line: a site name, domain or app name. Not case-sensitive. Lines starting with # are ignored.
# Matched against the frontmost app's name and the browser tab's address, never against what is on screen.
# Changes apply on the next check; no restart needed.

[distracting]
# Always call me out for these, whatever the screen looks like:
# reddit
# instagram
# steam

[ok]
# Never call me out for these (wins over the list above):
# docs.python.org
# figma
"""


def front_app() -> str:
    """Name of the frontmost app via LaunchServices: no permission prompt, ~6 ms."""
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=2).stdout.strip()
        out = subprocess.run(
            ["lsappinfo", "info", "-only", "name", asn], capture_output=True, text=True, timeout=2
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r'"LSDisplayName"="([^"]*)"', out)
    return m.group(1) if m else ""


_CHROMIUM = {"Google Chrome", "Brave Browser", "Microsoft Edge", "Arc", "Chromium", "Vivaldi", "Opera"}


def front_url(app: str) -> str:
    """Active tab URL of a scriptable browser, so site rules don't depend on what the model read.
    First call per browser triggers macOS's one-time Automation prompt; denied/unsupported (Firefox) → ""."""
    if app == "Safari":
        script = 'tell application "Safari" to get URL of front document'
    elif app in _CHROMIUM:
        script = f'tell application "{app}" to get URL of active tab of front window'
    else:
        return ""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip()[:500] if r.returncode == 0 else ""


def parse(text: str) -> dict[str, list[str]]:
    rules: dict[str, list[str]] = {"distracting": [], "ok": []}
    section = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if not line:
            continue
        if line in ("[distracting]", "[ok]"):
            section = line[1:-1]
        elif section:
            rules[section].append(line[:100])
    return rules


def _hit(term: str, haystack: str) -> bool:
    # Whole-word match so a short rule like "x" can't match every word containing an x.
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack) is not None


def host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:  # malformed netloc, e.g. an unclosed IPv6 bracket
        return ""


def _address(url: str) -> str:
    # Host + path only: a search for "reddit" (?q=reddit) is not a visit to reddit.
    try:
        return urlsplit(url)._replace(query="", fragment="").geturl()
    except ValueError:
        return ""


def match(rules: dict[str, list[str]], front_app: str, url: str) -> tuple[str, str] | None:
    """Return ("working"|"distracted", term) if a user rule applies. "ok" wins over "distracting".
    Trusted signals only: never the model's reading of the screen, which any page, sidebar or terminal
    output can steer (a "3blue1brown" sidebar link, a log line printing "netflix")."""
    haystack = " | ".join(t.lower() for t in (front_app, _address(url), host(url)) if t)
    for term in rules["ok"]:
        if _hit(term, haystack):
            return "working", term
    for term in rules["distracting"]:
        if _hit(term, haystack):
            return "distracted", term
    if _is_shorts(url):
        return "distracted", SHORTS
    return None


SHORTS = "youtube.com/shorts"


def _is_shorts(url: str) -> bool:
    # Built in because the model can't be trusted here: the one clear-cut blind-eval miss was a Short it
    # called educational_video. Host + path, so "youtube.com/shorts" inside a query string doesn't count.
    h = host(url)
    if h != "youtube.com" and not h.endswith(".youtube.com"):
        return False
    path = urlsplit(url).path.lower()
    return path == "/shorts" or path.startswith("/shorts/")


class Rules:
    """Reloads the file when it changes, so edits in TextEdit apply live."""

    def __init__(self, path: Path):
        self.path = path
        self.mtime = None
        self.rules = parse("")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(TEMPLATE)

    def current(self) -> dict[str, list[str]]:
        try:
            m = self.path.stat().st_mtime
            if m != self.mtime:
                self.rules, self.mtime = parse(self.path.read_text(errors="replace")), m
        except OSError:
            pass  # keep the last good rules if the file is mid-save or deleted
        return self.rules
