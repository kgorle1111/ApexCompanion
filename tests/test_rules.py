import time

import pytest

import rules


def test_template_has_no_active_rules():
    assert rules.parse(rules.TEMPLATE) == {"distracting": [], "ok": []}


def test_parse_sections_comments_case():
    r = rules.parse("[distracting]\nReddit  # memes\n\n[ok]\n3Blue1Brown\n")
    assert r == {"distracting": ["reddit"], "ok": ["3blue1brown"]}


def test_ok_beats_distracting():
    r = rules.parse("[distracting]\nyoutube\n[ok]\nmusic.youtube.com\n")
    assert rules.match(r, "Safari", "https://music.youtube.com/watch?v=abc") == ("working", "music.youtube.com")
    assert rules.match(r, "Safari", "https://www.youtube.com/watch?v=abc") == ("distracted", "youtube")


def test_whole_word_only():
    r = rules.parse("[distracting]\nx\n")
    assert rules.match(r, "Xcode", "") is None
    assert rules.match(r, "Safari", "https://x.com/home") == ("distracted", "x")


def test_native_app_by_front_app_name():
    r = rules.parse("[distracting]\nsteam\n")
    assert rules.match(r, "Steam", "") == ("distracted", "steam")


def test_url_and_host_match_whatever_the_page_looks_like():
    r = rules.parse("[distracting]\ngithub.com\nreddit\n")
    url = "https://github.com/python/cpython/blob/main/Lib/json/__init__.py"
    assert rules.match(r, "Google Chrome", url) == ("distracted", "github.com")
    assert rules.match(r, "Safari", "https://www.reddit.com/r/funny/") == ("distracted", "reddit")


def test_rules_never_read_model_text():
    # The model's app/content strings are on-screen text, so they are not an input to match() at all.
    r = rules.parse("[distracting]\nnetflix\n")
    with pytest.raises(TypeError):
        rules.match(r, "Terminal", "", "Netflix", "curl netflix.com")


def test_youtube_shorts_is_always_distracted():
    none = rules.parse("")
    for url in (
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://m.youtube.com/shorts/abc?feature=share",
        "https://youtube.com/shorts",
    ):
        assert rules.match(none, "Google Chrome", url) == ("distracted", "youtube.com/shorts"), url
    for url in (
        "https://www.youtube.com/watch?v=abc",
        "https://www.youtube.com/shortsfoo",
        "https://notyoutube.com/shorts/abc",
        "https://example.com/?next=https://www.youtube.com/shorts/abc",
    ):
        assert rules.match(none, "Google Chrome", url) is None, url


def test_user_ok_beats_shorts_guard():
    r = rules.parse("[ok]\nyoutube\n")
    assert rules.match(r, "Safari", "https://www.youtube.com/shorts/abc") == ("working", "youtube")


def test_host():
    assert rules.host("https://www.YouTube.com/shorts/abc") == "www.youtube.com"
    assert rules.host("") == ""
    assert rules.host("http://[::1") == ""


def test_front_url_skips_non_browsers():
    assert rules.front_url("Xcode") == ""
    assert rules.front_url("") == ""


def test_no_rules_no_match():
    assert rules.match(rules.parse(""), "Safari", "https://www.reddit.com/") is None


def test_live_reload(tmp_path):
    p = tmp_path / "sites.txt"
    rr = rules.Rules(p)
    assert rr.current()["distracting"] == []
    time.sleep(0.01)
    p.write_text("[distracting]\nreddit\n")
    import os

    os.utime(p, (time.time() + 5, time.time() + 5))
    assert rr.current()["distracting"] == ["reddit"]
