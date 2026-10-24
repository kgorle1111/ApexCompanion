"""Gemma 4 E4B (vision + text) via mlx-vlm, loaded once from the local HF cache."""

import json
import os
import re
import time
import warnings

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # air-gapped by design: never hit the network


def hide_known_noise() -> None:
    """Hide only the harmless mel-filter notice from loading Gemma's (unused) audio processor; any other
    mlx/transformers warning is version drift we want to see."""
    warnings.filterwarnings(
        "ignore",
        message=r"At least one mel filter has all zero values",
        category=UserWarning,
        module=r"transformers\.audio_utils",
    )


hide_known_noise()

from huggingface_hub import snapshot_download  # noqa: E402
from huggingface_hub.errors import LocalEntryNotFoundError  # noqa: E402
from mlx_vlm import generate, load  # noqa: E402
from mlx_vlm.prompt_utils import apply_chat_template  # noqa: E402

MODEL_ID = "mlx-community/gemma-4-e4b-it-8bit"
# Exact snapshot the evals ran against: a re-upload under the same repo name must not change behavior.
MODEL_REVISION = "4255b21bd9a9d3fc807ef7abd80373f5e3a52a73"

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


def model_path() -> str:
    """Local folder of the pinned snapshot. Cache only, never the network, even if HF_HUB_OFFLINE is unset."""
    try:
        return snapshot_download(MODEL_ID, revision=MODEL_REVISION, local_files_only=True)
    except LocalEntryNotFoundError as e:  # raised whether HF_HUB_OFFLINE is 1 or 0 (hub 2.3.0)
        raise RuntimeError(
            f"model snapshot {MODEL_REVISION[:7]} not found in the Hugging Face cache; open ApexCompanion to "
            f'download it, or run: HF_HUB_OFFLINE=0 python -c "from huggingface_hub import snapshot_download; '
            f"snapshot_download('{MODEL_ID}', revision='{MODEL_REVISION}')\""
        ) from e


def load_model():
    global _model, _processor
    if _model is None:
        # A local path, not the repo id: mlx_vlm would otherwise resolve "latest" via refs/main.
        _model, _processor = load(model_path())
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
    verdict = {
        "app": str(data.get("app", ""))[:60],
        "content": str(data.get("content", ""))[:120],
        "category": category if valid else "unparsed",
        "state": "distracted" if category in DISTRACTED else "working",
        "latency_s": round(time.perf_counter() - t0, 2),
        "raw": raw[:300],
    }
    if not valid:  # how a prompt/model regression shows up in the log; parsed checks don't carry screen text
        verdict["raw_unparsed"] = raw[:200]
    return verdict


def generate_text(prompt: str, max_tokens: int = 80, temperature: float = 0.9) -> str:
    return _run(prompt, None, max_tokens=max_tokens, temperature=temperature)


if __name__ == "__main__":
    import sys

    for path in sys.argv[1:]:
        print(path, classify(path))
