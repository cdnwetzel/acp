import pytest
from pipeline import validate

SCHEMA = {"type": "object", "required": ["a"],
          "properties": {"a": {"type": "string", "minLength": 2},
                         "n": {"type": "integer"},
                         "tags": {"type": "array", "minItems": 1,
                                  "items": {"type": "string", "pattern": "^T-"}}}}

def test_valid_document_passes():
    assert validate.validate(SCHEMA, {"a": "ok", "n": 1, "tags": ["T-1"]})

def test_missing_required_fails():
    with pytest.raises(validate.ValidationError):
        validate.validate(SCHEMA, {})

def test_min_length_fails():
    with pytest.raises(validate.ValidationError):
        validate.validate(SCHEMA, {"a": "x"})

def test_bool_is_not_integer():
    with pytest.raises(validate.ValidationError):
        validate.validate(SCHEMA, {"a": "ok", "n": True})

def test_array_pattern_enforced_per_item():
    with pytest.raises(validate.ValidationError):
        validate.validate(SCHEMA, {"a": "ok", "tags": ["T-1", "X-2"]})

def test_min_items_fails():
    with pytest.raises(validate.ValidationError):
        validate.validate(SCHEMA, {"a": "ok", "tags": []})
