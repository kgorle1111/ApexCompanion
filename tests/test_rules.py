import time

import pytest

import rules


def test_template_has_no_active_rules():
    assert rules.parse(rules.TEMPLATE) == {"distracting": [], "ok": [], "ignored_headers": []}


def test_parse_sections_comments_case():
    r = rules.parse("[distracting]\nReddit  # memes\n\n[ok]\n3Blue1Brown\n")
    assert r == {"distracting": ["reddit"], "ok": ["3blue1brown"], "ignored_headers": []}


def test_unknown_header_ends_section_instead_of_becoming_a_term():
    # Audit repro: [allow] used to land in "distracting" with everything under it -> roasts on the docs.
    r = rules.parse("[distracting]\nreddit\n[allow]\ndocs.python.org\n")
    assert r == {"distracting": ["reddit"], "ok": [], "ignored_headers": ["[allow]"]}
    assert rules.match(r, "Safari", "https://docs.python.org/3/library/re.html") is None
    assert rules.match(r, "Safari", "https://www.reddit.com/") == ("distracted", "reddit")


def test_near_miss_headers_are_ignored_until_a_valid_one():
    r = rules.parse("[OK ]\nfigma\n[distracted]\nsteam\n[ok]\nnotion\n[Distracting]\nimgur\n")
    assert r == {"distracting": ["imgur"], "ok": ["notion"], "ignored_headers": ["[ok ]", "[distracted]"]}


def test_summary_counts_without_terms():
    r = rules.parse("[distracting]\nreddit\nsteam\n[allow]\nx\n[ok]\nfigma\n")
    assert rules.summary(r) == {"distracting": 2, "ok": 1, "ignored_headers": ["[allow]"]}
    assert rules.summary(rules.parse("")) == {"distracting": 0, "ok": 0, "ignored_headers": []}


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


def test_search_query_is_not_a_visit():
    r = rules.parse("[distracting]\nreddit\n")
    assert rules.match(r, "Safari", "https://www.google.com/search?q=reddit+python") is None
    assert rules.match(r, "Safari", "https://www.reddit.com/r/python/") == ("distracted", "reddit")


def test_call_apps_are_meetings():
    for app in (
        "zoom.us",
        "Zoom",
        "Microsoft Teams",
        "Microsoft Teams (work or school)",
        "Teams",
        "FaceTime",
        "Webex",
        "Cisco Webex Meetings",
        "Around",
        "Tuple",
        "Google Meet",
    ):
        assert rules.in_meeting(app, "") is True, app


def test_chat_apps_and_lookalikes_are_not_meetings():
    for app in ("Discord", "Slack", "Zoomerang", "Microsoft Teams Helper", "Safari", "Google Chrome"):
        assert rules.in_meeting(app, "") is False, app


def test_meet_code_vs_landing_page():
    assert rules.in_meeting("Google Chrome", "https://meet.google.com/abc-defg-hij") is True
    assert rules.in_meeting("Google Chrome", "https://meet.google.com/abc-defg-hij?authuser=0&pli=1") is True
    for url in (
        "https://meet.google.com/",
        "https://meet.google.com",
        "https://meet.google.com/landing",
        "https://meet.google.com/abc-defg-hij/extra",
        "https://notmeet.google.com/abc-defg-hij",
    ):
        assert rules.in_meeting("Google Chrome", url) is False, url


def test_zoom_join_vs_marketing():
    assert rules.in_meeting("Safari", "https://us02web.zoom.us/j/1234567890?pwd=abc") is True
    assert rules.in_meeting("Safari", "https://app.zoom.us/wc/1234567890/join") is True
    assert rules.in_meeting("Safari", "https://zoom.us/") is False
    assert rules.in_meeting("Safari", "https://zoom.us/pricing") is False
    assert rules.in_meeting("Safari", "https://zoom.us.evil.com/j/123") is False


def test_teams_and_whereby_calls():
    assert rules.in_meeting("Microsoft Edge", "https://teams.microsoft.com/l/meetup-join/19%3ameeting_x/0") is True
    assert rules.in_meeting("Microsoft Edge", "https://teams.microsoft.com/v2/") is False
    assert rules.in_meeting("Microsoft Edge", "https://teams.live.com/meet/9876543210") is True
    assert rules.in_meeting("Microsoft Edge", "https://teams.live.com/") is False
    assert rules.in_meeting("Arc", "https://whereby.com/team-standup") is True
    assert rules.in_meeting("Arc", "https://whereby.com/") is False
    assert rules.in_meeting("Arc", "https://whereby.com/information/pricing") is False


def test_meeting_url_in_query_string_is_not_a_call():
    for url in (
        "https://www.google.com/search?q=meet.google.com/abc-defg-hij",
        "https://www.google.com/search?q=https%3A%2F%2Fus02web.zoom.us%2Fj%2F123",
        "https://example.com/redirect?to=https://meet.google.com/abc-defg-hij",
        "https://example.com/meet.google.com/abc-defg-hij",
    ):
        assert rules.in_meeting("Google Chrome", url) is False, url


def test_empty_is_never_a_meeting():
    assert rules.in_meeting("", "") is False
    assert rules.in_meeting("   ", "") is False
    assert rules.in_meeting("Safari", "http://[::1") is False
