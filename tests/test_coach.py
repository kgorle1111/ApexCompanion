from apex import Coach


def test_single_distraction_never_roasts():
    c = Coach(streak_to_roast=2, cooldown_s=60, praise_every=0)
    assert c.observe("distracted", 0) is None
    assert c.observe("working", 10) is None
    assert c.observe("distracted", 20) is None


def test_two_in_a_row_roasts_then_cooldown_blocks():
    c = Coach(streak_to_roast=2, cooldown_s=60, praise_every=0)
    assert c.observe("distracted", 0) is None
    assert c.observe("distracted", 10) == "roast"
    assert c.observe("distracted", 20) is None  # inside cooldown
    assert c.observe("distracted", 69) is None
    assert c.observe("distracted", 70) == "roast"
    assert c.strikes == 2


def test_working_resets_run():
    c = Coach(streak_to_roast=2, cooldown_s=0, praise_every=0)
    c.observe("distracted", 0)
    c.observe("working", 10)
    assert c.observe("distracted", 20) is None


def test_praise_on_working_streak():
    c = Coach(streak_to_roast=2, cooldown_s=60, praise_every=3)
    assert [c.observe("working", t) for t in range(3)] == [None, None, "praise"]
    c.observe("distracted", 4)
    assert [c.observe("working", t) for t in range(5, 8)] == [None, None, "praise"]
