# ApexCompanion

**A focus coach that watches your screen with Gemma 4, on your laptop, and says it out loud when you drift.**

![ApexCompanion demo](docs/demo.gif)

Every 10 seconds it takes a screenshot, asks Gemma 4 what's on it, and decides in code whether you're working. Two distracted checks in a row and your coach speaks up: a one- or two-line roast, in character, that names what you're actually looking at. While you work, it stays quiet.

Nothing leaves the machine. Pull the Wi-Fi and it keeps running.

> Think of it as a gym coach who can see your screen but has signed an NDA with your laptop.

---

## Why local

A screenshot of your screen is about the most private data you have: your messages, your bank tab, your half-written cover letter. Sending one to a cloud API every 10 seconds is not a reasonable thing to ask anyone to accept.

So the model runs on the laptop: Gemma 4 E4B, 8-bit, through `mlx-vlm` on Apple Silicon. `HF_HUB_OFFLINE=1` keeps the Hugging Face client off the network, and `gemma.py` sets it by default too.

What stays on disk:
- **Screenshots: nothing.** Each frame goes to one temp file, gets classified, and is deleted right after its check.
- **Session log:** `logs/session-*.jsonl` keeps the model's short text description of each check (app, content, category, verdict) plus any line it spoke. Local only, git-ignored. Delete the folder whenever you like.

Side effects of running locally: it's free, and it works on a plane.

## How it works

```
 every 10 s
 ┌───────────────┐   ┌──────────┐   ┌──────────────────────┐   ┌──────────────────┐
 │ screencapture │──▶│ sips     │──▶│ Gemma 4 E4B (vision) │──▶│ code maps        │
 │ -x -t jpg     │   │ -Z 1024  │   │ JSON: app, content,  │   │ category → state │
 └───────────────┘   └──────────┘   │ category             │   │ working /        │
                                    └──────────────────────┘   │ distracted       │
         screenshot deleted after the check                    └────────┬─────────┘
                                                                        │
             bad JSON or unknown category ──▶ "working" (never roast on garbage)
                                                                        │
                          distracted 2 checks in a row AND 60 s cooldown passed?
                                                                        │ yes
                                    ┌──────────────────────┐   ┌────────▼─────────┐
                                    │ macOS notification   │◀──│ Gemma 4 (text)   │
                                    │ + `say` (spoken)     │   │ ≤2-sentence roast│
                                    └──────────────────────┘   │ names app+content│
                                                               └──────────────────┘
 Ctrl-C ──▶ session stats: length, checks, % focused, call-outs
```

One model load, reused for both the vision call and the roast. The same Gemma 4 weights do both jobs.

Category map (lives in code, not in the prompt):

| Category | State |
|---|---|
| `coding`, `docs_reading`, `notes_writing`, `educational_video`, `messaging`, `news_reading`, `other` | working |
| `entertainment_video`, `social_media`, `shopping`, `gaming`, `feed_browsing`, `sports` | distracted |

Messaging, news, and "other" count as working on purpose. A false roast while you're replying to your professor is worse than a missed one. The prompt also tells the model to ignore ads, banners, and pop-ups, so a sidebar ad doesn't decide the category.

Trade-off to know about: "other" fails open to working. A native game that lands in "other" won't be roasted.

### Personas

Two original characters, picked with `--persona`:

- **The Closer** (`--persona closer`): an arrogant, razor-witty dealmaker who treats you like the associate about to blow the deal.
- **The Whip** (`--persona whip`): a cold, slow-talking political operator who speaks in unsettling metaphors.

Each persona is a prompt, a few example lines, and a built-in macOS voice, in `personas.py`. Repeat offenses escalate: the second call-out in a session is sharper than the first, and from the third on it counts out loud. Stay on task long enough (30 working checks in a row by default) and you get a rare line of praise.

## Design decision: the model never says "distracted"

The first version asked Gemma one question: is this screenshot `working` or `distracted`? It labeled a YouTube cat compilation "working". Gemma 4 did it, and so did Gemma 3 when we tried it as a cross-check.

A binary label gives the model room to rationalize ("maybe they're researching cats"). So we split the job:

1. **The model describes.** It returns `{"app", "content", "category"}`: which app, what's on screen, and one category from a fixed list.
2. **Code decides.** A lookup table maps the category to working or distracted. The model never emits the verdict.

With describe-then-categorize, the same cat video landed in a distracted category, so the code called it distracted.

That fix started as **one synthetic test case**. The real-page eval came after: on 28 real public web pages, the classifier got **25/25 clear-cut pages right, with 0 false roasts** (details under [Evaluating it](#evaluating-it)).

It's the pattern we default to: deterministic guards around one structured model call, and code owns the final decision. The debounce, cooldown, and fail-open default are plain Python (`Coach` in `apex.py`, no I/O) with unit tests in `tests/`.

## Prior art (and what's different)

We're not the first to point a local model at a screen to catch drift. [AccountyCat](https://github.com/strjonas/AccountyCat) is an MIT macOS focus companion running local Qwen via llama.cpp; it reads the app and window title first and uses a screenshot only when that's ambiguous, then nudges you. [Observer AI](https://github.com/Roy3838/Observer) lets you build local screen-watching agents, including "when I'm distracted, call me". Dayflow keeps a local screenshot timeline without intervening.

What ApexCompanion does differently:
- **Gemma 4 vision on every check**, not window-title text with a screenshot fallback.
- **Spoken persona roasts** that name what's on screen, instead of a quiet nudge.
- **Code owns the verdict.** The model describes; a lookup table decides.

The trade-off is real: a text-first design like AccountyCat's is cheaper on compute and battery than running a vision model every 10 seconds.

## Setup

Requires an Apple Silicon Mac (MLX), Python 3.12, and [uv](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.12
uv pip install mlx-vlm pillow
```

Download the model once while you're online (it goes into the Hugging Face cache):

```bash
.venv/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/gemma-4-e4b-it-8bit')"
```

Grant screen access: **System Settings → Privacy & Security → Screen Recording**, enable your terminal app, then quit and reopen it. Without this, screenshots come back as just your wallpaper and everything looks like "other", so the coach would silently stay quiet. `apex.py` checks for this and refuses to start without the permission. It also warms the model at boot, so the first real check isn't slow.

Run:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python apex.py --persona closer
```

Swap `closer` for `whip` to change the voice. Turn your volume up. Ctrl-C ends the session and prints your stats.

Useful flags: `--interval` (seconds between checks, default 10), `--streak` (distracted checks before a roast, default 2), `--cooldown` (seconds between roasts, default 60), `--praise-every` (0 turns praise off), `--mute`, `--once` (one check, print, exit), `--image FILE` (classify a file instead of the screen; repeatable).

## Measured numbers

Measured on an M3 Max, `mlx-community/gemma-4-e4b-it-8bit`, `mlx-vlm 0.7.10`, offline.

| What | Number | Caveat |
|---|---|---|
| Model load | **3.7 s** | |
| First classify call | **2.6 s** | includes warm-up |
| Warm classify, per check | **p50 0.87 s, p95 0.96 s** | over the 28 real eval pages, model already loaded |
| Roast generation | **~2.0 s** | |
| Peak memory | **11.2 GB** | CLI cold run |
| End-to-end check | 2 distracted checks → spoken roast | worked once, on a synthetic image |
| Classifier, clear-cut real web pages | **25/25 correct, 0 false roasts** | 28 public pages in total; 25 is a small set, so one miss would cost 4 points |
| Classifier, all 28 real web pages | **26/28** | both misses were on cases labeled ambiguous |
| Distracted recall | **11/11** | every distracted page was caught |
| Held-out pages | **6/6** | one of the 6 (ESPN) was looked at while tuning the prompt, so 5 are clean |
| Real-world time from opening a distraction to the roast | [[TBD: stopwatch, 5 trials]] | by design ≥ 2 checks at a 10 s interval, plus ~2.0 s to write the roast |
| Battery drain per hour | [[TBD: battery % or powermetrics over a 1 h session]] | |

Fixed settings (configuration, not measurements): 10 s check interval, 2 consecutive distracted checks before a roast, 60 s cooldown between roasts, screenshots downscaled to 1024 px on the long side.

## Evaluating it

`eval.py` runs the classifier over real screenshots in `evals/` against hand labels in `evals/labels.json` and prints accuracy and per-case latency. The screenshot files are git-ignored: they're pictures of someone's real screen, so they stay on that machine.

**The set.** 28 real public web pages captured in a headless browser: 12 working, 11 distracted, 5 hard cases. A person confirmed every label. Pages a reasonable person could call either way are labeled ambiguous and reported separately.

**Results** (Gemma 4 E4B 8-bit, `mlx-vlm 0.7.10`, M3 Max, offline):
- Clear-cut pages: **25/25**, with **0 false roasts**.
- All 28 pages: **26/28**. Both misses were ambiguous cases: a lofi "study" stream whose player showed "Video unavailable", and a random Wikipedia biography.
- Distracted recall: **11/11**.
- Held-out: **6/6**. One of those (ESPN) was looked at while tuning the prompt, so 5 are clean.
- Latency: p50 0.87 s, p95 0.96 s per check, warm.

**Checking that the eval can fail.** We broke the category map on purpose and re-ran it (mutation testing). Moving `entertainment_video` into the working list turned the eval red on the distracted-recall gate (threshold 0.85). Moving `coding` into the distracted list turned it red with 5 false roasts. The first version of the gate checked accuracy only, and it did not catch the first mutation, so we added the recall gate.

## Limitations

- **Web pages only.** The eval is 28 real web pages. Native desktop apps (VS Code, the terminal, the native Spotify app, games) are untested.
- **"Other" fails open.** Anything the model files under "other" counts as working, so a native game that lands there won't be roasted.
- **Small eval.** 25 clear-cut cases is a small set; one miss is 4 points. Treat 25/25 as "no misses yet on this set", not as a general accuracy figure.
- **Heavy for a background app.** 11.2 GB peak memory, and a vision call every 10 seconds. Expect trouble on Macs with little unified memory, and expect it to cost more battery than a text-first approach.
- **Mac only.** `screencapture`, `sips`, `osascript`, `say`, and MLX are all macOS / Apple Silicon.
- **It sees one screen, once every 10 seconds.** It can miss short distractions, and on multiple displays it only judges what `screencapture` captures.
- **Context is a single frame.** A lecture on YouTube with a cat thumbnail in the sidebar, or gameplay footage you're watching for work, can be misread. Fail-open defaults and the 2-check debounce reduce false roasts; they don't eliminate them.
- **The session log is a record of what you looked at.** Text only and local, but it exists. Delete `logs/` if you don't want it.
- **It's a nudge, not a blocker.** It won't stop you from opening anything. That's deliberate, but it means it only works if you leave it running.
- **No automatic fallback.** The Ollama build of Gemma 4 we had takes no image input, which is why vision runs through `mlx-vlm`. Gemma 3 vision via Ollama worked in a quick test, but that path isn't wired into `apex.py`.

## License

MIT for the code in this repo. The Gemma 4 weights are distributed by Google under their own terms; check the model card before redistributing them.
