import subprocess


def test_osascript_accepts_dash_line_after_separator():
    r = subprocess.run(
        ["osascript", "-e", "on run argv", "-e", "return item 1 of argv", "-e", "end run", "--", "- hi", "t"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0 and r.stdout.strip() == "- hi"
