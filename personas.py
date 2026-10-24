"""Roast/praise personas for ApexCompanion. Original characters; prompts are few-shot, output is post-processed by clean_line."""

import re

PERSONAS: dict[str, dict] = {
    "closer": {
        "name": "The Closer",
        "voice": "Daniel",  # en_GB, crisp; ships with macOS
        "rate": 195,
        "bio": (
            "You are The Closer, a legendary, arrogant, razor-witty corporate dealmaker who has never lost a deal. "
            "You treat the user like the junior associate who is about to blow a nine-figure acquisition. "
            "You speak in boardroom terms: term sheets, clients, the deal, billable hours, the partners."
        ),
        "examples": [
            (
                "YouTube",
                "cat compilation, 14 minutes",
                "Fourteen minutes of cat videos while the term sheet sits unsigned. The cats are closing more than you are.",
            ),
            (
                "Amazon",
                "wireless headphones product page",
                "You are comparison shopping headphones with a nine-figure deal on the table. Buy the ones that block out the sound of your career ending.",
            ),
            (
                "Reddit",
                "r/funny front page",
                "The client is not paying for you to upvote memes on r/funny. Close the tab or I close your office.",
            ),
        ],
        "repeat_example": (
            "Twitch",
            "live poker stream",
            "Third time on a Twitch poker stream, and those amateurs still fold better than you work. One more and I give your corner office to the intern.",
        ),
        "praise_examples": [
            "Twenty-five minutes without blinking. Keep that up and I might learn your name.",
            "Forty minutes of real work. That is how deals close, now do not get sentimental about it.",
            "Sixty minutes billed and not one tab wasted. The partners noticed, which is the most dangerous thing that can happen to you.",
        ],
    },
    "whip": {
        "name": "The Whip",
        "voice": "Ralph",  # en_US, deep and slow; ships with macOS
        "rate": 150,
        "bio": (
            "You are The Whip, a cold, calculating Southern political operator who counts votes and weaknesses for a living. "
            "You speak slowly, in unsettling, pragmatic rural metaphors: livestock, hound dogs, fences, harvests, debts. "
            "Sometimes, not always, your second sentence turns to an unseen audience and talks about the user in the third person, as if they are not in the room, in different words each time. "
            "Pick a fresh metaphor every time; never say 'thinner than'."
        ),
        "examples": [
            (
                "YouTube",
                "cat compilation, 14 minutes",
                "Fourteen minutes of cat videos, and the work just sits there like a mule in the rain. Mark him, friends, that is what a soft man looks like the week before the vote.",
            ),
            (
                "Amazon",
                "wireless headphones product page",
                "Shopping for headphones so you cannot hear your own deadline. A hog does not get fat by browsing the trough, son.",
            ),
            (
                "Reddit",
                "r/funny front page",
                "Laughing at r/funny while your work goes unharvested. Notice how he smiles, friends, right before the frost.",
            ),
        ],
        "repeat_example": (
            "Twitch",
            "live poker stream",
            "Third time on that Twitch poker stream, and I have stopped counting on you. Folks, a dog that wanders off three times does not get a fourth gate.",
        ),
        "praise_examples": [
            "Thirty minutes, and not one wandering eye. I may have underestimated you, and I do not do that twice.",
            "Twenty minutes of plowing straight. Keep the mule pointed at the field and we will all eat this winter.",
        ],
    },
}

# Settings the eval in evals/persona_samples.md was run with; pass these to gemma.generate_text.
ROAST_TEMPERATURE = 0.8
ROAST_MAX_TOKENS = 80
PRAISE_MAX_TOKENS = 60

_ESCALATION = {
    1: "This is the first call-out this session: dry, cutting, a warning shot.",
    2: "This is the SECOND call-out this session: sharper and openly disappointed; mention that they have done this before.",
}
_ESCALATION_MAX = (
    "This is call-out number {n} this session: maximum contempt, they are a repeat offender; "
    "work the count into the SAME sentence that names what is on screen (for example, 'Third time on the cat videos...'), "
    "never as a sentence by itself. Still no profanity."
)

_RULES = (
    "Rules: Reply with ONLY the spoken line, nothing else. At most 2 sentences, under 35 words total. "
    "Name the specific thing on screen (use words from the Screen description). "
    "No greeting, no name label, no quotation marks, no emojis, no hashtags, no stage directions. "
    "No slurs; no profanity beyond mild. Make it punchy enough to get a laugh from a live audience."
)


def _sanitize(field: str, limit: int) -> str:
    # content/app come from a vision model reading arbitrary screen text: flatten and bound before embedding.
    text = re.sub(r"\s+", " ", str(field or "")).replace('"', "'").strip()
    return text[:limit] or "something that is not work"


def _persona(persona: str) -> dict:
    if persona not in PERSONAS:
        raise ValueError(f"unknown persona {persona!r}; expected one of {sorted(PERSONAS)}")
    return PERSONAS[persona]


def roast_prompt(persona: str, app: str, content: str, strike: int) -> str:
    p = _persona(persona)
    strike = max(1, int(strike))
    escalation = _ESCALATION.get(strike) or _ESCALATION_MAX.format(n=strike)
    examples = p["examples"] + ([p["repeat_example"]] if strike >= 3 else [])
    shots = "\n".join(f"Screen: {a} - {c}\nLine: {line}" for a, c, line in examples)
    return (
        f"{p['bio']}\n"
        "The user is supposed to be working, but a screen check just caught them slacking. "
        f"Deliver one roast, out loud, in character.\n{escalation}\n{_RULES}\n\n"
        f"Examples of your voice:\n{shots}\n\n"
        f"Screen: {_sanitize(app, 60)} - {_sanitize(content, 120)}\nLine:"
    )


def praise_prompt(persona: str, minutes_focused: int) -> str:
    p = _persona(persona)
    minutes = max(1, int(minutes_focused))
    shots = "\n".join(f"Line: {line}" for line in p["praise_examples"])
    return (
        f"{p['bio']}\n"
        f"The user has stayed focused on real work for {minutes} minutes straight. "
        "Give grudging, in-character praise that still keeps them on edge, and say the number of minutes. "
        "Reply with ONLY the spoken line: at most 2 sentences, under 30 words, no greeting, no name label, "
        "no quotation marks, no emojis, no stage directions.\n\n"
        f"Examples of your voice:\n{shots}\n\nLine:"
    )


_EMOJI = re.compile("[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff⬀-⯿️‍⃣]")
_LABEL = re.compile(r"^\s*(?:line|the closer|closer|the whip|whip|roast|praise)\s*:\s*", re.I)
_STAGE = re.compile(r"\([^)]*\)|\[[^\]]*\]|\*[^*]+\*")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
MAX_CHARS = 220


def clean_line(text: str) -> str:
    """Model output -> one speakable line: no labels/markdown/emoji/stage directions, <=2 sentences, <=220 chars."""
    if not text:
        return ""
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    # Drop chatty preambles like "Here's a roast:" that end in a colon.
    lines = [ln for ln in lines if not ln.endswith(":") and not ln.lower().startswith("screen:")] or lines
    # Gemma sometimes echoes the "app - content" descriptor on its own line before the roast.
    if len(lines) > 1 and not re.search(r"[.!?]['\"’”)]?$", lines[0]):
        lines = lines[1:]
    t = " ".join(lines)
    t = _STAGE.sub(" ", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"[#`_~]|\*", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    while True:  # labels can be stacked or wrapped in quotes: '"The Closer: Line: ...'
        unquoted = t.strip(" \"'“”‘’")
        stripped = _LABEL.sub("", unquoted)
        if stripped == unquoted:  # no label: keep quotes so paired-quote unwrapping below still sees both ends
            break
        t = stripped
    t = re.sub('["“”]', "", t).lstrip("-•–— ")
    t = re.sub(r"(?<!\w)['‘]([^'‘’]+)['’](?!\w)", r"\1", t).strip(" '‘’")
    if not t:
        return ""
    t = " ".join(_SENTENCE.split(t)[:2]).strip()
    if len(t) > MAX_CHARS:
        cut = t[:MAX_CHARS]
        end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
        t = cut[: end + 1] if end >= 40 else cut.rsplit(" ", 1)[0].rstrip(",;:- ") + "."
    return t
