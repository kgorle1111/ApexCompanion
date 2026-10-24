import subprocess

import gemma
import personas


def _classify_with(monkeypatch, raw):
    monkeypatch.setattr(gemma, "_run", lambda *a, **k: raw)
    return gemma.classify("unused.jpg")


def test_truncated_json_still_yields_category(monkeypatch):
    v = _classify_with(monkeypatch, '{"app":"YouTube","content":"cats","category":"entertainment_video"')
    assert v["state"] == "distracted"


def test_category_spelling_variants_normalize(monkeypatch):
    assert _classify_with(monkeypatch, '{"category":"social media"}')["state"] == "distracted"
    assert _classify_with(monkeypatch, '{"category":"Social-Media"}')["state"] == "distracted"


def test_garbage_fails_open_to_working(monkeypatch):
    v = _classify_with(monkeypatch, "I cannot help with that.")
    assert (v["state"], v["category"]) == ("working", "unparsed")


def test_clean_line_strips_leading_bullet():
    assert personas.clean_line("- Close the tab. Now.") == "Close the tab. Now."


def test_osascript_accepts_dash_line_after_separator():
    r = subprocess.run(
        ["osascript", "-e", "on run argv", "-e", "return item 1 of argv", "-e", "end run", "--", "- hi", "t"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0 and r.stdout.strip() == "- hi"
