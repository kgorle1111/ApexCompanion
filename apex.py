"""ApexCompanion: on-device focus coach. Gemma 4 watches the screen; a persona calls you out loud."""

import argparse
import ctypes
import fcntl
import json
import os
import platform
import resource
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SHOT_MAX_PX = 1024
# The packaged app points this at ~/Library/Application Support/ApexCompanion/logs, the folder its docs name.
LOG_DIR = Path(os.environ.get("APEX_LOG_DIR") or Path(__file__).parent / "logs")
# The packaged app redirects stdout into a log file; the screen description only goes to a live terminal.
INTERACTIVE = sys.stdout.isatty()
SCHEMA = 1  # bump when event fields change; report.py reads it
SHOT_TIMEOUT_S = 15  # screencapture and sips each; a hung one must cost one check, not the session
NOTIFY_TIMEOUT_S = 10
SAY_TIMEOUT_S = 30  # longer than any persona line takes to speak
BREAKER = 6  # consecutive failed or unparsed checks before the coach stops instead of faking focus
PERMISSION_EVERY = 30  # checks between Screen Recording re-checks; revoked mid-session = wallpaper = "working"
CORE_GRAPHICS = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"


class EventLog:
    """One JSON object per line, owner-only. Every event carries the session id so a report can group them."""

    def __init__(self, path: Path, session: str):
        self.session = session
        self.warned = False
        # Owner-only from creation: even trimmed, the log says which apps and sites were in front and when.
        self.f = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a")

    def emit(self, event: str, **fields) -> None:
        try:
            self.f.write(
                json.dumps({"t": time.time(), "schema": SCHEMA, "session": self.session, "event": event, **fields})
                + "\n"
            )
            self.f.flush()
        except OSError as e:  # disk full: losing log lines beats losing the session
            self._warn(e)

    def close(self) -> None:
        try:
            self.f.close()  # flushes whatever a full disk refused earlier, so it can raise too
        except OSError as e:
            self._warn(e)

    def _warn(self, e: OSError) -> None:
        if not self.warned:
            self.warned = True
            print(
                f"warning: session log write failed ({e!r}); coaching continues unlogged", file=sys.stderr, flush=True
            )


def prune_logs(log_dir: Path, keep_days: float) -> int:
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for old in log_dir.glob("session-*.jsonl"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
                removed += 1
        except OSError:
            pass  # another instance may be pruning too
    return removed


def peak_rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 1)  # bytes on macOS


@dataclass
class Coach:
    """Pure decision state: no I/O, so the debounce/cooldown rules are unit-testable."""

    streak_to_roast: int = 2
    cooldown_s: float = 60.0
    praise_every: int = 0
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


def take_lock() -> int:
    """Two coaches = two model copies (~22 GB) on a 16 GB Mac. flock dies with the process, even on SIGKILL."""
    fd = os.open(Path(tempfile.gettempdir()) / "apex.lock", os.O_RDWR | os.O_CREAT, 0o600)  # TMPDIR is per-user
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        sys.exit("ApexCompanion is already running; stop it from the menu bar first.")
    return fd


def sweep_frames() -> int:
    """Frames a SIGKILL or OOM kill left behind. Only safe while holding the lock: no live coach owns them."""
    removed = 0
    for old in Path(tempfile.gettempdir()).glob("apex_*.jpg"):
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def screen_permission() -> bool | None:
    """CoreGraphics' own answer, no developer tools needed. None if it can't be asked."""
    try:
        preflight = ctypes.CDLL(CORE_GRAPHICS).CGPreflightScreenCaptureAccess
    except (OSError, AttributeError):
        return None
    preflight.restype, preflight.argtypes = ctypes.c_bool, []
    return bool(preflight())


def require_screen_permission() -> None:
    """Without permission screencapture still succeeds but returns only the wallpaper, so the coach
    would silently call everything 'working'. Refuse to start instead."""
    if os.environ.get("APEX_SCREEN_OK") == "1":  # the app bundle already checked via CoreGraphics
        return
    ok = screen_permission()
    if ok is None:  # warn, don't brick: a missing framework symbol isn't proof the permission is missing
        print(
            "warning: couldn't verify Screen Recording permission; if every check says 'other', grant it.",
            file=sys.stderr,
        )
        return
    if not ok:
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
    r = subprocess.run(["screencapture", "-x", "-t", "jpg", path], capture_output=True, timeout=SHOT_TIMEOUT_S)
    if r.returncode != 0 or not Path(path).exists() or Path(path).stat().st_size == 0:
        # Not sys.exit: SystemExit escapes the loop's `except Exception`, and a locked screen or sleeping
        # display fails capture transiently; that must skip one check, not end the session.
        raise RuntimeError(
            "screencapture failed. Grant Screen Recording to this terminal app "
            "(System Settings → Privacy & Security → Screen Recording), then restart it."
        )
    subprocess.run(["sips", "-Z", str(SHOT_MAX_PX), path], capture_output=True, check=True, timeout=SHOT_TIMEOUT_S)
    return path


def notify(text: str, title: str) -> None:
    # Model text goes in as argv, never spliced into AppleScript source.
    try:
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
            timeout=NOTIFY_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:  # a missed banner, never a dead session
        print("output failed: notification timed out", file=sys.stderr, flush=True)


class Voice:
    def __init__(self, voice: str, rate: int, mute: bool):
        self.voice, self.rate, self.mute = voice, rate, mute
        self.proc: subprocess.Popen | None = None

    def say(self, text: str) -> None:
        if self.mute:
            return
        if self.proc and self.proc.poll() is None:
            self.finish()  # never talk over itself
        self.proc = subprocess.Popen(["say", "-v", self.voice, "-r", str(self.rate), "--", text])

    def finish(self) -> None:
        if not self.proc:
            return
        try:
            self.proc.wait(timeout=SAY_TIMEOUT_S)
        except subprocess.TimeoutExpired:  # a wedged audio stack must not wedge the loop
            self.proc.kill()


def _graceful_term(signum, frame) -> None:
    # The launcher's fallback is SIGTERM; take the Ctrl-C path so session_end, state.json and frame cleanup still run.
    raise KeyboardInterrupt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--persona", default="closer")
    ap.add_argument("--interval", type=float, default=10.0, help="seconds between checks")
    ap.add_argument("--cooldown", type=float, default=60.0, help="min seconds between roasts")
    ap.add_argument("--streak", type=int, default=2, help="consecutive distracted checks before a roast")
    ap.add_argument(
        "--praise-every", type=int, default=0, help="log praise after N working checks in a row (0=off); never spoken"
    )
    ap.add_argument("--goal", default="", help="what you plan to work on; call-outs contrast it with the screen")
    ap.add_argument("--minutes", type=float, default=0.0, help="end the session after N minutes (0 = no limit)")
    ap.add_argument("--state-dir", help="write state.json and obey control.json here (the menu bar app)")
    ap.add_argument("--image", action="append", help="classify these files instead of the screen (repeatable)")
    ap.add_argument("--once", action="store_true", help="one check, print verdict, exit")
    ap.add_argument("--mute", action="store_true")
    ap.add_argument(
        "--sites",
        default=os.environ.get("APEX_SITES", str(Path(__file__).parent / "sites.txt")),
        help="your always-distracting / always-OK list (created on first run)",
    )
    ap.add_argument("--log-days", type=float, default=7.0, help="delete session logs older than this (0 = keep all)")
    args = ap.parse_args()
    session_t0 = time.time()

    import control  # noqa: E402  (after argparse so --help is instant)
    import personas  # noqa: E402
    import rules  # noqa: E402

    user_rules = rules.Rules(Path(args.sites))

    if args.persona not in personas.PERSONAS:
        sys.exit(f"unknown persona {args.persona!r}; choose from {sorted(personas.PERSONAS)}")
    p = personas.PERSONAS[args.persona]
    title = f"ApexCompanion · {args.persona.title()}"
    voice = Voice(p["voice"], p["rate"], args.mute)
    goal = control.clean_goal(args.goal)

    lock_fd, swept, screen_ok = None, 0, None
    if not args.image:
        lock_fd = take_lock()
        swept = sweep_frames()
        require_screen_permission()
        # Baseline for the mid-session re-check: if this process can't see the grant even at start (the packaged
        # app checks via its own bundle), a False later says nothing about revocation.
        screen_ok = screen_permission()

    LOG_DIR.mkdir(exist_ok=True)
    pruned = prune_logs(LOG_DIR, args.log_days) if args.log_days > 0 else 0
    session = uuid.uuid4().hex[:8]
    ctl = None
    if args.state_dir:
        Path(args.state_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
        ctl = control.Control(Path(args.state_dir) / "control.json", since=session_t0)
    started = last_mark = focused_s = 0.0
    ends_at: float | None = None
    last_state, last_line, stop_reason = "starting", None, None
    errors = roasts = praises = guarded = bad_run = 0

    def publish(state: str) -> None:
        nonlocal last_state
        last_state = state
        if not ctl:
            return
        now = time.time()
        paused_until = ctl.values["paused_until"]
        try:
            control.write_state(
                Path(args.state_dir) / "state.json",
                {
                    "schema": control.SCHEMA,
                    "t": now,
                    "session": session,
                    "persona": args.persona,
                    "goal": goal,
                    "state": state,
                    "focused_s": int(focused_s),
                    "elapsed_s": int(now - started) if started else 0,
                    "ends_at": ends_at,
                    "paused_until": paused_until if paused_until and paused_until > now else None,
                    "muted": voice.mute,
                    "roasts": roasts,
                    "last_line": last_line,
                    "stop_reason": stop_reason,
                },
            )
        except OSError as e:  # the menu bar goes stale, but the session itself is fine
            print(f"state write failed: {e!r}", file=sys.stderr, flush=True)

    def trip(cause: str, error: str) -> None:
        """Alive-but-broken must not sound like focus: stop loudly instead of logging 'working' forever.
        `cause` is shown after "Stopped: " by the menu bar and launcher: one line, no prefix, under 120 chars."""
        nonlocal stop_reason, last_line
        stop_reason, last_line = "error", cause
        print(f"stopped: {cause}", file=sys.stderr, flush=True)
        log.emit("error", n=n, stage="breaker", error=error[:300])
        try:
            notify(cause, title)
        except OSError as e:
            print(f"output failed: {e!r}", file=sys.stderr, flush=True)
        publish("error")

    def end_reason() -> str | None:
        if ctl and ctl.current()["stop"]:
            return "user"
        if ends_at is not None and time.time() >= ends_at:
            return "timer"
        return None

    log = EventLog(LOG_DIR / f"session-{time.strftime('%Y%m%d-%H%M%S')}-{session}.jsonl", session)
    log.emit(
        "session_start",
        persona=args.persona,
        interval_s=args.interval,
        cooldown_s=args.cooldown,
        streak=args.streak,
        minutes=args.minutes,
        goal_set=bool(goal),
        mode="replay" if args.image else "screen",
        python=platform.python_version(),
        macos=platform.mac_ver()[0],
        pruned_logs=pruned,
        swept_frames=swept,
    )
    publish("starting")
    coach = Coach(args.streak, args.cooldown, args.praise_every)
    fd, shot = tempfile.mkstemp(prefix="apex_", suffix=".jpg")  # per-run: two instances can't clobber
    os.close(fd)
    images = list(args.image or [])
    n = 0
    prev_term = signal.signal(signal.SIGTERM, _graceful_term)

    try:
        print("loading Gemma 4 (local, offline)…", flush=True)
        t0 = time.perf_counter()
        import gemma  # noqa: E402

        gemma.load_model()
        warm_up(gemma)
        load_s = time.perf_counter() - t0
        print(f"model ready in {load_s:.1f}s", flush=True)
        log.emit("model_ready", model=gemma.MODEL_ID, load_s=round(load_s, 2), rss_mb=peak_rss_mb())
        started = last_mark = time.time()
        # Fixed at start: pausing doesn't extend it, the menu bar derives "of N min" from ends_at.
        ends_at = started + args.minutes * 60 if args.minutes > 0 else None
        while True:
            tick = time.perf_counter()
            if args.image and not images:
                break
            stop_reason = end_reason()
            if stop_reason == "timer":
                last_line = f"Session done: {round(focused_s / 60)} min focused."
                print(f"   🗣  {last_line}", flush=True)
                try:
                    notify(last_line, title)
                    voice.say(last_line)
                except OSError as e:
                    print(f"output failed: {e!r}", file=sys.stderr, flush=True)
            if stop_reason:
                break
            if ctl:
                voice.mute = args.mute or ctl.values["muted"]
                if ctl.paused(time.time()):  # no frame, no model call until paused_until passes
                    last_mark = time.time()
                    publish("paused")
                    time.sleep(args.interval)
                    continue
            n += 1
            if screen_ok and n % PERMISSION_EVERY == 0 and screen_permission() is False:
                trip(
                    "Screen Recording permission was turned off. Turn it back on, then open ApexCompanion again.",
                    "screen recording permission revoked",
                )
                break
            timing: dict[str, float] = {}
            stage = "rules"
            try:
                t = time.perf_counter()
                app_name = "" if args.image else rules.front_app()
                url = rules.front_url(app_name) if app_name else ""
                meeting = rules.in_meeting(app_name, url)
                hit = None if meeting else rules.match(user_rules.current(), app_name, url)
                timing["rules_s"] = round(time.perf_counter() - t, 4)
                if meeting:  # counted as working so a call doesn't cost focus %; nothing is captured or said
                    v = {"app": app_name, "content": rules.host(url), "category": "meeting", "latency_s": 0.0}
                    v["state"], v["rule"] = "working", None
                elif hit:  # the user's list beats the model both ways, so no frame is taken or read at all
                    v = {"app": app_name, "content": rules.host(url), "category": "rule", "latency_s": 0.0}
                    v["state"], v["rule"] = hit
                else:
                    stage, t = "capture", time.perf_counter()
                    path = images.pop(0) if images else capture(shot)
                    timing["capture_s"] = round(time.perf_counter() - t, 4)
                    stage = "classify"
                    v = gemma.classify(path) | {"rule": None}
                    timing["classify_s"] = v["latency_s"]
            except Exception as e:  # one bad frame must not end a live session
                errors += 1
                bad_run += 1
                print(f"{time.strftime('%H:%M:%S')} check failed: {e!r}", file=sys.stderr, flush=True)
                log.emit("error", n=n, stage=stage, error=repr(e)[:300])
                last_mark = time.time()
                if bad_run >= BREAKER:  # ...but six in a row is a broken coach, not a bad frame
                    hint = (
                        "Check Screen Recording permission" if stage == "capture" else "If it repeats, check the logs"
                    )
                    trip(f"{bad_run} checks in a row failed. {hint}, then open ApexCompanion again.", repr(e))
                    break
                publish(last_state)
                if args.once:
                    break
                if end_reason() is None:
                    time.sleep(args.interval if not args.image else 0)
                continue
            finally:
                Path(shot).unlink(missing_ok=True)  # privacy claim: no frame outlives its check
            bad_run = bad_run + 1 if v["category"] == "unparsed" else 0
            action = coach.observe(v["state"], time.monotonic())
            if v["category"] == "meeting":
                action = None
            now = time.time()
            if v["state"] == "working":
                # Capped so a Mac that slept between checks doesn't credit hours of focus.
                focused_s += min(now - last_mark, args.interval + 120)
            last_mark = now
            mark = "🟢" if v["state"] == "working" else "🔴"
            why = f"rule:{v['rule']}" if v["rule"] else v["category"]
            print(
                f"{time.strftime('%H:%M:%S')} {mark} {why:<20} {v['app'][:20]:<20} "
                f"{v['content'][:50] if INTERACTIVE else '':<50} {v['latency_s']:.2f}s",
                flush=True,
            )

            line = None
            was_guarded = False
            if action in ("roast", "praise"):
                if action == "roast":
                    prompt = personas.roast_prompt(args.persona, v["app"], v["content"], coach.strikes, goal=goal)
                    max_tokens = personas.ROAST_MAX_TOKENS
                else:
                    minutes = round(coach.working_run * args.interval / 60)
                    prompt, max_tokens = personas.praise_prompt(args.persona, minutes), personas.PRAISE_MAX_TOKENS
                t = time.perf_counter()
                try:
                    raw = gemma.generate_text(prompt, max_tokens=max_tokens, temperature=personas.ROAST_TEMPERATURE)
                except Exception as e:  # a failed roast is a missed line, not a dead session
                    errors += 1
                    log.emit("error", n=n, stage=action, error=repr(e)[:300])
                    raw = ""
                timing["roast_s"] = round(time.perf_counter() - t, 3)
                line = personas.clean_line(raw, persona=args.persona)
                was_guarded = bool(line) and personas.is_unsafe(raw)
                roasts += action == "roast"
                praises += action == "praise"
                guarded += was_guarded
            if line and action == "praise":  # logged only: a spoken compliment breaks the focus it praises
                print(f"   ✓  {line}", flush=True)
            elif line:
                last_line = line
                print(f"   🗣  {line}", flush=True)
                try:
                    notify(line, title)
                    voice.say(line)
                except OSError as e:
                    print(f"output failed: {e!r}", file=sys.stderr, flush=True)

            timing["total_s"] = round(time.perf_counter() - tick, 3)
            log.emit(
                "check",
                n=n,
                front_app=app_name,
                host=rules.host(url),  # not the URL: paths and queries make the log a browsing diary
                app=v["app"],
                content=v["content"] if action == "roast" else None,  # only what was said out loud
                **{k: v[k] for k in ("category", "state", "rule", "latency_s")},
                action=action,
                line=line,
                guarded=was_guarded,
                timing=timing,
            )
            publish("meeting" if v["category"] == "meeting" else v["state"])
            if bad_run >= BREAKER:
                trip(
                    f"{bad_run} checks in a row got no usable answer from the model. Open ApexCompanion again.",
                    "unparsed model output: " + str(v.get("raw_unparsed", ""))[:200],
                )
                break
            if args.once:
                break
            if end_reason() is None:
                time.sleep(max(0.0, args.interval - (time.perf_counter() - tick)) if not args.image else 0)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # a second TERM must not cut session_end short
        Path(shot).unlink(missing_ok=True)
        voice.finish()
        checks = coach.working_checks + coach.distracted_checks
        focus_pct = 100 * coach.working_checks / checks if checks else 0
        log.emit(
            "session_end",
            checks=checks,
            errors=errors,
            roasts=roasts,
            praises=praises,
            guarded=guarded,
            focus_pct=round(focus_pct, 1),
            duration_s=round(time.time() - started, 1) if started else 0.0,
            peak_rss_mb=peak_rss_mb(),
            stop_reason=stop_reason,
        )
        log.close()
        publish("error" if stop_reason == "error" else "stopped")  # the launcher shows last_line after exit 3
        signal.signal(signal.SIGTERM, prev_term)
        if lock_fd is not None:
            os.close(lock_fd)
        print(
            f"\nsession {(time.time() - started) / 60 if started else 0:.1f} min · {checks} checks · "
            f"focused {focus_pct:.0f}% · call-outs {coach.strikes}"
        )
    if stop_reason == "error":
        sys.exit(3)
    if args.once and bad_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
