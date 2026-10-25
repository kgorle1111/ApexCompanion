# Hardening record

What was checked before v0.2.0, what was fixed, and what is still unverified. ApexCompanion runs for one person on one Mac, so "scale" here means memory, timing and failure behavior, not users. The short version lives in the README under **Ceilings**.

## Ceilings

| Metric | Value | Live / derived | How measured |
|---|---|---|---|
| Expected concurrency | 1 coach per Mac | enforced | single-instance lock in `apex.py`; a second coach exits with a message |
| Break point | memory: 11.3 GB peak footprint (steady 8.6 to 8.9 GB) | live | `/usr/bin/time -l` over a 306-check soak on an M3 Max |
| Time per check | p50 1.29 s, p95 1.60 s (classify alone p50 0.97 s) | live | 52-minute session on a real desktop, 624 checks, 0 errors ([`evals/live_session_2026-10-24.json`](evals/live_session_2026-10-24.json)) |
| Shortest useful interval | about 1.6 s | derived | the loop is sequential; below the p95 it just runs back to back |
| Cost per check | $0 | by design | no network calls after setup; `HF_HUB_OFFLINE=1` |
| Largest input | one screenshot, 1024 px long side; output capped at 100 tokens (classify), 80 (roast), 60 (praise) | configuration | `apex.py`, `gemma.py`, `personas.py` |

## Gaps, ranked by blast radius

Privacy and data loss first, then silent wrong output, then outages, then cosmetic.

| # | Gap | Fix | Status |
|---|---|---|---|
| 1 | `apex.log` (spoken roast lines) grew forever | launcher rotates `apex.log` and `launcher.log` at 1 MB, `umask 077` | fixed (v0.2.0) |
| 2 | A screenshot could survive SIGTERM, SIGKILL or a low-memory kill | SIGTERM takes the clean-exit path; leftover `apex_*.jpg` frames are swept at startup | fixed |
| 3 | Alive but broken looked like focus: every check failing, or garbage model output, counted as "working" | 6 bad checks in a row: notify, write state `error`, exit 3; the menu bar shows ⚠︎ and the app explains why | fixed (v0.2.0) |
| 4 | Screen Recording failed open: without it, screenshots are wallpaper only | strict CoreGraphics preflight at start (no developer tools needed); re-checked every 30 checks when the coach's own process could see the grant at start | fixed (v0.2.0) |
| 5 | A typo in a `sites.txt` header flipped allowed sites to distracting | an unknown `[header]` ends the section; rule counts are logged | fixed |
| 6 | Model version not pinned, so new installs could get different weights | snapshot `4255b21` pinned in `gemma.py` and the launcher | fixed |
| 7 | Warm-up proved the model loads, not that it answers | loud warning and a `warning` event if the warm-up output doesn't parse | fixed (v0.2.0) |
| 8 | CI tested floating dependencies | installs with `-c packaging/constraints.txt`, pinned tools, actions pinned to SHAs | fixed |
| 9 | `--once` exited 0 on failure | exits 1 | fixed (v0.2.0) |
| 10 | No timeouts on `screencapture`, `sips`, notifications or `say`, so the loop could freeze | timeouts on all four; a stuck `say` is killed after 30 s | fixed (v0.2.0) |
| 11 | Two coaches could run at once (about 22 GB) | single-instance lock | fixed (v0.2.0) |
| 12 | Disk full could kill the session; the launcher deleted the engine before rebuilding it | log writes can't end a session; the venv is rebuilt beside the old one and swapped in | fixed (v0.2.0) |
| 13 | `curl` for uv had no timeout and fetched the latest installer | `--max-time 120 --retry 2`, installer pinned to uv 0.11.21 | fixed (v0.2.0) |
| 14 | No release pipeline; version hard-coded to 0.1.0 | version from the git tag, dirty tree refused, sha256 written next to the zip | fixed (v0.2.0) |
| 15 | `build_app.sh` did not ship `control.py`, so the packaged v0.2.0 app would crash at start | added, plus a test that every module `apex.py` imports is shipped | fixed (v0.2.0) |
| 16 | Ad-hoc signing resets the Screen Recording grant on every update | needs a Developer ID ($99/year) or a self-signed certificate | open, documented in INSTALL |

## Unverified

Each line names the one action that would verify it.

- **Clean-account install** through the macOS security prompt, with no developer tools, no Hugging Face cache and no uv: run it on a fresh user account.
- **First-run 8.3 GB download with resume:** interrupt the download once on a clean account.
- **Rollback to an older zip:** install v0.1.2 over v0.2.0 and start a session.
- **8 GB and 16 GB Macs:** run a 30-minute session and record the peak footprint and swap.
- **Battery drain per hour:** an hour on battery, coach on vs off.
- **Mid-session permission revocation:** turn Screen Recording off during a session and confirm the coach stops within 30 checks. The preflight call is unit-tested with a stub; macOS may cache its answer per process.
- **The packaged app's own process seeing the grant:** if Python inside the app can't read it at start, the mid-session re-check stays off (fails safe to the old behavior). Check `session_start` on the first packaged session.
- **The venv swap with real dependencies:** proven with a stub installer only. Bump the deps stamp on a real install once.

## Add when

- **Developer ID signing:** before anyone outside the author installs updates regularly (item 16).
- **Change-gated vision** (skip the model when the app and URL are unchanged): when someone runs it all day, or battery drain is measured above a few percent per hour.
- **A memory guard at startup** (refuse on Macs under 16 GB): when the first 8 GB or 16 GB report comes in.
