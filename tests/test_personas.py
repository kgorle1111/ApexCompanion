import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from personas import PERSONAS, clean_line, praise_prompt, roast_prompt  # noqa: E402


def test_strips_wrapping_quotes():
    assert clean_line('"Close the tab."') == "Close the tab."
    assert clean_line("“Close the tab.”") == "Close the tab."


def test_strips_persona_prefix_and_markdown():
    assert clean_line("**The Closer:** Close the tab.") == "Close the tab."
    assert clean_line("Whip: Close the tab, son.") == "Close the tab, son."


def test_strips_emojis_and_stage_directions():
    assert clean_line("(leans in) Close the tab. \U0001f602\U0001f525") == "Close the tab."
    assert clean_line("*sighs* Close the tab.") == "Close the tab."


def test_four_sentences_become_two():
    out = clean_line("One. Two! Three? Four.")
    assert out == "One. Two!"


def test_empty_input():
    assert clean_line("") == ""
    assert clean_line("   \n ") == ""
    assert clean_line('""') == ""


def test_length_capped():
    out = clean_line("word " * 100)
    assert 0 < len(out) <= 220


def test_prompts_embed_content_and_reject_unknown_persona():
    p = roast_prompt("closer", "YouTube", "cat compilation", 3)
    assert "cat compilation" in p and "number 3" in p
    assert "45 minutes" in praise_prompt("whip", 45)
    with pytest.raises(ValueError):
        roast_prompt("nobody", "x", "y", 1)
    assert all({"voice", "rate"} <= set(v) for v in PERSONAS.values())


def test_drops_echoed_descriptor_and_unwraps_single_quotes():
    raw = "Instagram - reels of dancing dogs\nYou're watching 'Funniest Cats' again. Focus."
    assert clean_line(raw) == "You're watching Funniest Cats again. Focus."
    assert clean_line("'Funniest Cats 2026'? Get back to work.") == "Funniest Cats 2026? Get back to work."
