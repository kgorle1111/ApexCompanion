"""Gemma 4 E4B (vision + text) via mlx-vlm, loaded once from the local HF cache."""

import json
import os
import re
import time
import warnings

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # air-gapped by design: never hit the network
warnings.filterwarnings("ignore")

from mlx_vlm import generate, load  # noqa: E402
from mlx_vlm.prompt_utils import apply_chat_template  # noqa: E402

MODEL_ID = "mlx-community/gemma-4-e4b-it-8bit"

WORKING = {"coding", "docs_reading", "notes_writing", "educational_video", "messaging", "news_reading", "other"}
DISTRACTED = {"entertainment_video", "social_media", "shopping", "gaming", "feed_browsing", "sports"}
CATEGORIES = sorted(WORKING | DISTRACTED)

CLASSIFY_PROMPT = (
    "Describe this laptop screenshot. Ignore ads, banners and pop-ups; judge the main page. "
    "Reply ONLY JSON with keys in this order: "
    '{"app":"<app or site in focus>","content":"<what the user is looking at, 8 words>",'
    f'"category":one of {json.dumps(CATEGORIES)}}}\n'
    "educational_video = one lecture/tutorial video is open. "
    "feed_browsing = a grid or feed of recommended videos, images or posts (e.g. YouTube home, Imgur). "
    "news_reading = news or tech-news headlines or articles. "
    "sports = sports scores, highlights or sports news."
)

_model = _processor = None


def load_model():
    global _model, _processor
    if _model is None:
        _model, _processor = load(MODEL_ID)
    return _model, _processor


def _run(prompt: str, image: str | None, max_tokens: int, temperature: float) -> str:
    model, processor = load_model()
    formatted = apply_chat_template(processor, model.config, prompt, num_images=1 if image else 0)
    result = generate(
        model,
        processor,
        formatted,
        image=[image] if image else None,
        max_tokens=max_tokens,
        temperature=temperature,
        verbose=False,
    )
    return result.text.strip()


def _parse(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def classify(image_path: str) -> dict:
    """Model describes + categorizes; code owns the verdict. Unparseable output fails open to working."""
    t0 = time.perf_counter()
    raw = _run(CLASSIFY_PROMPT, image_path, max_tokens=100, temperature=0.0)
    data = _parse(raw)
    if "category" not in data:  # category is the last key, so truncated JSON loses it first
        m = re.search(r'"category"\s*:\s*"([^"]+)"', raw)
        if m:
            data["category"] = m.group(1)
    category = re.sub(r"[\s\-]+", "_", str(data.get("category", "")).strip().lower())
    valid = category in WORKING or category in DISTRACTED
    return {
        "app": str(data.get("app", ""))[:60],
        "content": str(data.get("content", ""))[:120],
        "category": category if valid else "unparsed",
        "state": "distracted" if category in DISTRACTED else "working",
        "latency_s": round(time.perf_counter() - t0, 2),
        "raw": raw[:300],
    }


def generate_text(prompt: str, max_tokens: int = 80, temperature: float = 0.9) -> str:
    return _run(prompt, None, max_tokens=max_tokens, temperature=temperature)


if __name__ == "__main__":
    import sys

    for path in sys.argv[1:]:
        print(path, classify(path))
