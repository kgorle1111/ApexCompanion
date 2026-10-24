import warnings

import pytest
from huggingface_hub.errors import LocalEntryNotFoundError

import gemma


def _classify_with(monkeypatch, raw):
    monkeypatch.setattr(gemma, "_run", lambda *a, **k: raw)
    return gemma.classify("unused.jpg")


def test_truncated_json_still_yields_category(monkeypatch):
    v = _classify_with(monkeypatch, '{"app":"YouTube","content":"cats","category":"entertainment_video"')
    assert v["state"] == "distracted"


def test_category_spelling_variants_normalize(monkeypatch):
    assert _classify_with(monkeypatch, '{"category":"social media"}')["state"] == "distracted"
    assert _classify_with(monkeypatch, '{"category":"Social-Media"}')["state"] == "distracted"


def test_garbage_fails_open_to_working(monkeypatch):
    v = _classify_with(monkeypatch, "I cannot help with that.")
    assert (v["state"], v["category"]) == ("working", "unparsed")


def test_raw_unparsed_only_on_unparsed_and_truncated(monkeypatch):
    v = _classify_with(monkeypatch, "x" * 500)
    assert v["category"] == "unparsed" and v["raw_unparsed"] == "x" * 200
    assert "raw" in v  # existing key kept for eval.py
    ok = _classify_with(monkeypatch, '{"app":"Xcode","content":"swift","category":"coding"}')
    assert "raw_unparsed" not in ok


def test_load_model_uses_pinned_snapshot_path(monkeypatch):
    calls = {}

    def fake_snapshot(repo, revision=None, local_files_only=False):
        calls["snap"] = (repo, revision, local_files_only)
        return "/cache/snapshots/" + revision

    def fake_load(path):
        calls["load"] = path
        return "m", "p"

    monkeypatch.setattr(gemma, "_model", None)
    monkeypatch.setattr(gemma, "snapshot_download", fake_snapshot)
    monkeypatch.setattr(gemma, "load", fake_load)
    assert gemma.load_model() == ("m", "p")
    assert calls["snap"] == (gemma.MODEL_ID, "4255b21bd9a9d3fc807ef7abd80373f5e3a52a73", True)
    assert calls["load"] == "/cache/snapshots/4255b21bd9a9d3fc807ef7abd80373f5e3a52a73"


def test_missing_snapshot_is_a_prescriptive_error(monkeypatch):
    def missing(*a, **k):
        raise LocalEntryNotFoundError("Cannot find an appropriate cached snapshot folder")

    monkeypatch.setattr(gemma, "_model", None)
    monkeypatch.setattr(gemma, "snapshot_download", missing)
    monkeypatch.setattr(gemma, "load", lambda *a, **k: pytest.fail("must not load an unpinned model"))
    with pytest.raises(RuntimeError, match="model snapshot 4255b21 not found in the Hugging Face cache") as e:
        gemma.load_model()
    assert "open ApexCompanion to download it" in str(e.value)
    assert f"revision='{gemma.MODEL_REVISION}'" in str(e.value)


def _emit(message, module):
    warnings.warn_explicit(message, UserWarning, module.replace(".", "/") + ".py", 1, module=module, registry={})


def test_only_the_mel_filter_warning_is_hidden():
    # Re-installed here because pytest restores the filter list after collection, dropping import-time filters.
    with warnings.catch_warnings(record=True) as seen:
        gemma.hide_known_noise()
        _emit("At least one mel filter has all zero values. num_mel_filters (128) too high", "transformers.audio_utils")
        _emit("`generate` kwarg foo is deprecated", "transformers.generation.utils")
        _emit("unexpected weight shape", "mlx_vlm.utils")
    assert [str(w.message) for w in seen] == ["`generate` kwarg foo is deprecated", "unexpected weight shape"]


def test_model_never_emits_the_verdict():
    assert "working" not in gemma.CATEGORIES and "distracted" not in gemma.CATEGORIES
    assert not (gemma.WORKING & gemma.DISTRACTED)
