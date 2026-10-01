import pytest

from app.parsing import extract_code_block, extract_json


def test_extract_json_from_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_prose():
    assert extract_json('Sure! {"a": [1, 2]} Hope this helps.') == {"a": [1, 2]}


def test_extract_json_none_raises():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_extract_code_python_fence():
    assert extract_code_block("Here:\n```python\nx = 1\n```\nDone") == "x = 1"


def test_extract_code_plain_fence():
    assert extract_code_block("```\nx = 1\n```") == "x = 1"


def test_extract_code_no_fence():
    assert extract_code_block("  x = 1\n") == "x = 1"
