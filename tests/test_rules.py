import time

import rules


def test_template_has_no_active_rules():
    assert rules.parse(rules.TEMPLATE) == {"distracting": [], "ok": []}


def test_parse_sections_comments_case():
    r = rules.parse("[distracting]\nReddit  # memes\n\n[ok]\n3Blue1Brown\n")
    assert r == {"distracting": ["reddit"], "ok": ["3blue1brown"]}


def test_ok_beats_distracting():
    r = rules.parse("[distracting]\nyoutube\n[ok]\n3blue1brown\n")
    assert rules.match(r, "Google Chrome", "YouTube", "3Blue1Brown neural networks") == ("working", "3blue1brown")
    assert rules.match(r, "Google Chrome", "YouTube", "cat compilation") == ("distracted", "youtube")


def test_whole_word_only():
    r = rules.parse("[distracting]\nx\n")
    assert rules.match(r, "Xcode", "Xcode", "editing a Swift file") is None
    assert rules.match(r, "Safari", "X", "timeline of posts") == ("distracted", "x")


def test_native_app_by_front_app_name():
    r = rules.parse("[distracting]\nsteam\n")
    assert rules.match(r, "Steam", "", "") == ("distracted", "steam")


def test_url_matches_even_when_model_misreads_site():
    r = rules.parse("[distracting]\ngithub.com\nreddit\n")
    url = "https://github.com/python/cpython/blob/main/Lib/json/__init__.py"
    assert rules.match(r, "Google Chrome", url, "VS Code", "editing Python code") == ("distracted", "github.com")
    assert rules.match(r, "Safari", "https://www.reddit.com/r/funny/", "", "") == ("distracted", "reddit")


def test_front_url_skips_non_browsers():
    assert rules.front_url("Xcode") == ""
    assert rules.front_url("") == ""


def test_no_rules_no_match():
    assert rules.match(rules.parse(""), "Safari", "Reddit", "funny posts") is None


def test_live_reload(tmp_path):
    p = tmp_path / "sites.txt"
    rr = rules.Rules(p)
    assert rr.current()["distracting"] == []
    time.sleep(0.01)
    p.write_text("[distracting]\nreddit\n")
    import os

    os.utime(p, (time.time() + 5, time.time() + 5))
    assert rr.current()["distracting"] == ["reddit"]
