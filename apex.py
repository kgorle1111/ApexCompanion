"""ApexCompanion: on-device focus coach. Gemma 4 watches the screen; a persona calls you out loud."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

SHOT_MAX_PX = 1024
LOG_DIR = Path(__file__).parent / "logs"


@dataclass
class Coach:
    """Pure decision state: no I/O, so the debounce/cooldown rules are unit-testable."""

    streak_to_roast: int = 2
    cooldown_s: float = 60.0
    praise_every: int = 30
    distracted_run: int = 0
    working_run: int = 0
    last_roast_at: float = field(default=float("-inf"))
    strikes: int = 0
    working_checks: int = 0
    distracted_checks: int = 0

    def observe(self, state: str, now: float) -> str | None:
        if state == "distracted":
            self.distracted_checks += 1
            self.distracted_run += 1
            self.working_run = 0
            if self.distracted_run >= self.streak_to_roast and now - self.last_roast_at >= self.cooldown_s:
                self.last_roast_at = now
                self.strikes += 1
                return "roast"
            return None
        self.working_checks += 1
        self.working_run += 1
        self.distracted_run = 0
        if self.praise_every and self.working_run % self.praise_every == 0:
            return "praise"
        return None


def require_screen_permission() -> None:
    """Without permission screencapture still succeeds but returns only the wallpaper, so the coach
    would silently call everything 'working'. Refuse to start instead."""
    if os.environ.get("APEX_SCREEN_OK") == "1":  # the app bundle already checked via CoreGraphics
        return
    try:
        r = subprocess.run(
            ["swift", "-e", "import CoreGraphics; print(CGPreflightScreenCaptureAccess())"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print(
            "warning: couldn't verify Screen Recording permission (no swift); if every check says 'other', grant it.",
            file=sys.stderr,
        )
        return
    if r.stdout.strip() == "false":
        sys.exit(
            "Screen Recording permission is missing for this terminal app: screenshots would be "
            "wallpaper only.\nGrant it in System Settings → Privacy & Security → Screen Recording, "
            "quit and reopen the terminal, then rerun. (Use --image FILE to test without it.)"
        )


def warm_up(gemma) -> None:
    from PIL import Image

    path = str(Path(tempfile.gettempdir()) / "apex_warmup.jpg")
    Image.new("RGB", (64, 64), "white").save(path)
    gemma.classify(path)
    Path(path).unlink(missing_ok=True)


def capture(path: str) -> str:
    r = subprocess.run(["screencapture", "-x", "-t", "jpg", path], capture_output=True)
    if r.returncode != 0 or not Path(path).exists() or Path(path).stat().st_size == 0:
        sys.exit(
            "screencapture failed. Grant Screen Recording to this terminal app "
            "(System Settings → Privacy & Security → Screen Recording), then restart it."
        )
    subprocess.run(["sips", "-Z", str(SHOT_MAX_PX), path], capture_output=True, check=True)
    return path


def notify(text: str, title: str) -> None:
    # Model text goes in as argv, never spliced into AppleScript source.
    subprocess.run(
        [
            "osascript",
            "-e",
            "on run argv",
            "-e",
            "display notification (item 1 of argv) with title (item 2 of argv)",
            "-e",
            "end run",
            "--",
            text,
            title,
        ],  # "--": a line starting with "-" would otherwise parse as an osascript flag
        capture_output=True,
    )


class Voice:
    def __init__(self, voice: str, rate: int, mute: bool):
        self.voice, self.rate, self.mute = voice, rate, mute
        self.proc: subprocess.Popen | None = None

    def say(self, text: str) -> None:
        if self.mute:
            return
        if self.proc and self.proc.poll() is None:
            self.proc.wait()  # never talk over itself
        self.proc = subprocess.Popen(["say", "-v", self.voice, "-r", str(self.rate), "--", text])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--persona", default="closer")
    ap.add_argument("--interval", type=float, default=10.0, help="seconds between checks")
    ap.add_argument("--cooldown", type=float, default=60.0, help="min seconds between roasts")
    ap.add_argument("--streak", type=int, default=2, help="consecutive distracted checks before a roast")
    ap.add_argument("--praise-every", type=int, default=30, help="praise after N working checks in a row (0=off)")
    ap.add_argument("--image", action="append", help="classify these files instead of the screen (repeatable)")
    ap.add_argument("--once", action="store_true", help="one check, print verdict, exit")
    ap.add_argument("--mute", action="store_true")
    ap.add_argument(
        "--sites",
        default=os.environ.get("APEX_SITES", str(Path(__file__).parent / "sites.txt")),
        help="your always-distracting / always-OK list (created on first run)",
    )
    args = ap.parse_args()

    import personas  # noqa: E402  (after argparse so --help is instant)
    import rules  # noqa: E402

    user_rules = rules.Rules(Path(args.sites))

    if args.persona not in personas.PERSONAS:
        sys.exit(f"unknown persona {args.persona!r}; choose from {sorted(personas.PERSONAS)}")
    p = personas.PERSONAS[args.persona]
    title = f"ApexCompanion · {args.persona.title()}"
    voice = Voice(p["voice"], p["rate"], args.mute)

    if not args.image:
        require_screen_permission()

    print("loading Gemma 4 (local, offline)…", flush=True)
    t0 = time.perf_counter()
    import gemma  # noqa: E402

    gemma.load_model()
    warm_up(gemma)
    print(f"model ready in {time.perf_counter() - t0:.1f}s", flush=True)

    LOG_DIR.mkdir(exist_ok=True)
    log = (LOG_DIR / f"session-{time.strftime('%Y%m%d-%H%M%S')}.jsonl").open("a")
    coach = Coach(args.streak, args.cooldown, args.praise_every)
    fd, shot = tempfile.mkstemp(prefix="apex_", suffix=".jpg")  # per-run: two instances can't clobber
    os.close(fd)
    images = list(args.image or [])
    started = time.time()

    try:
        while True:
            tick = time.perf_counter()
            if args.image and not images:
                break
            try:
                app_name = "" if args.image else rules.front_app()
                url = rules.front_url(app_name) if app_name else ""
                path = images.pop(0) if images else capture(shot)
                v = gemma.classify(path)
            except Exception as e:  # one bad frame must not end a live session
                print(f"{time.strftime('%H:%M:%S')} check failed: {e!r}", file=sys.stderr, flush=True)
                log.write(json.dumps({"t": time.time(), "error": repr(e)[:300]}) + "\n")
                if args.once:
                    break
                time.sleep(args.interval if not args.image else 0)
                continue
            finally:
                Path(shot).unlink(missing_ok=True)  # privacy claim: no frame outlives its check
            hit = rules.match(user_rules.current(), app_name, url, v["app"], v["content"])
            v["rule"] = None
            if hit:  # the user's list beats the model, both ways
                v["state"], v["rule"] = hit
            action = coach.observe(v["state"], time.monotonic())
            mark = "🟢" if v["state"] == "working" else "🔴"
            why = f"rule:{v['rule']}" if v["rule"] else v["category"]
            print(
                f"{time.strftime('%H:%M:%S')} {mark} {why:<20} {v['app'][:20]:<20} "
                f"{v['content'][:50]:<50} {v['latency_s']:.2f}s",
                flush=True,
            )

            line = None
            if action == "roast":
                line = personas.clean_line(
                    gemma.generate_text(
                        personas.roast_prompt(args.persona, v["app"], v["content"], coach.strikes),
                        max_tokens=personas.ROAST_MAX_TOKENS,
                        temperature=personas.ROAST_TEMPERATURE,
                    )
                )
            elif action == "praise":
                minutes = round(coach.working_run * args.interval / 60)
                line = personas.clean_line(
                    gemma.generate_text(
                        personas.praise_prompt(args.persona, minutes),
                        max_tokens=personas.PRAISE_MAX_TOKENS,
                        temperature=personas.ROAST_TEMPERATURE,
                    )
                )
            if line:
                print(f"   🗣  {line}", flush=True)
                try:
                    notify(line, title)
                    voice.say(line)
                except OSError as e:
                    print(f"output failed: {e!r}", file=sys.stderr, flush=True)

            log.write(
                json.dumps(
                    {
                        "t": time.time(),
                        "front_app": app_name,
                        "url": url,
                        **{k: v[k] for k in ("app", "content", "category", "state", "rule", "latency_s")},
                        "action": action,
                        "line": line,
                    }
                )
                + "\n"
            )
            log.flush()
            if args.once:
                break
            time.sleep(max(0.0, args.interval - (time.perf_counter() - tick)) if not args.image else 0)
    except KeyboardInterrupt:
        pass
    finally:
        Path(shot).unlink(missing_ok=True)
        if voice.proc:
            voice.proc.wait()
        log.close()
        checks = coach.working_checks + coach.distracted_checks
        focus_pct = 100 * coach.working_checks / checks if checks else 0
        print(
            f"\nsession {(time.time() - started) / 60:.1f} min · {checks} checks · "
            f"focused {focus_pct:.0f}% · call-outs {coach.strikes}"
        )


if __name__ == "__main__":
    main()
