import pytest

from app.errors import PipelineError
from app.text_input import prepare_text


def test_bom_only_script_counts_as_empty():
    with pytest.raises(PipelineError) as exc:
        prepare_text("\ufeff   \r\n")
    assert exc.value.code == "EMPTY_SCRIPT"


def test_bom_and_zero_width_characters_are_removed():
    assert prepare_text("\ufeffHello \u200bworld.") == "Hello world."
