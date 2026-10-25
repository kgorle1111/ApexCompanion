from evals.binary_baseline import parse_reason, parse_state


def test_parses_distracted_and_reason():
    raw = '```json\n{"state": "Distracted", "reason": "Minecraft gameplay video on screen"}\n```'
    assert parse_state(raw) == "distracted"
    assert parse_reason(raw) == "Minecraft gameplay video on screen"


def test_parses_working():
    assert parse_state('{"state":"working","reason":"Reading Python documentation"}') == "working"


def test_unparsed_or_unknown_state_fails_open_to_working():
    assert parse_state("I cannot help with that.") == "working"
    assert parse_state('{"state": "procrastinating"}') == "working"
