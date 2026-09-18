from codeloop.rules.line_rules import imaging_modifiers, laterality_modifiers
from codeloop.tools.validators import VALID_MODIFIERS, is_valid_modifier


def test_imaging_lines_carry_26_and_side_modifiers():
    assert imaging_modifiers("knee", "right") == ["26", "RT"]
    assert imaging_modifiers("chest", "not_applicable") == ["26"]
    assert imaging_modifiers("foot", "bilateral") == ["26"]  # bilateral studies: two lines RT/LT are the coder's call
    assert laterality_modifiers("elbow", "left") == ["LT"] and laterality_modifiers("chest", "left") == []
    assert is_valid_modifier("26") and is_valid_modifier("tc") and "26" in VALID_MODIFIERS
