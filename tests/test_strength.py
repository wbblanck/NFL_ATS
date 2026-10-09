from engine.picks import strength as S


def test_tier_boundaries_follow_the_preregistered_cuts():
    assert [S.tier_key(m) for m in (0, 0.5, 1, 1.5, 2, 2.5, 3, 7)] == ["lean", "lean", "solid", "solid", "strong", "strong", "max", "max"]
    assert S.tier_key(-2.5) == "strong" and S.tier_key(None) is None and S.tier_key("") is None


def test_tag_is_empty_until_the_tiers_are_validated():
    assert S.tag(3, {"ok": True}) == "Max" and S.tag(0, {"ok": True}) == "Lean"
    assert S.tag(3, {"ok": False}) == "" and S.tag(None, {"ok": True}) == ""
