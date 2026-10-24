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


def test_model_never_emits_the_verdict():
    assert "working" not in gemma.CATEGORIES and "distracted" not in gemma.CATEGORIES
    assert not (gemma.WORKING & gemma.DISTRACTED)
