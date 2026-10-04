"""Minimal JSON-schema-subset validator (stdlib only).

Supported: type (object|array|string|integer|number|boolean), required,
properties, items, minLength, minItems, pattern. Raises ValidationError
with the failing path — contracts fail loudly, never silently pass.
"""
import json, re

class ValidationError(Exception):
    """Artifact failed its contract."""

_BOOL = bool
_TYPES = {
    "object": dict, "array": list, "string": str,
    "integer": int, "number": (int, float), "boolean": bool,
}

def validate(schema, doc, path="$"):
    t = schema.get("type")
    if t:
        if t in ("integer", "number") and isinstance(doc, _BOOL):
            raise ValidationError(f"{path}: expected {t}, got boolean")
        if t == "integer" and isinstance(doc, float):
            raise ValidationError(f"{path}: expected integer, got float")
        if not isinstance(doc, _TYPES[t]):
            raise ValidationError(f"{path}: expected {t}, got {type(doc).__name__}")
    if t == "object":
        for req in schema.get("required", []):
            if req not in doc:
                raise ValidationError(f"{path}.{req}: required field missing")
        for key, sub in schema.get("properties", {}).items():
            if key in doc:
                validate(sub, doc[key], f"{path}.{key}")
    elif t == "array":
        if "minItems" in schema and len(doc) < schema["minItems"]:
            raise ValidationError(f"{path}: need >= {schema['minItems']} items, got {len(doc)}")
        items = schema.get("items")
        if items:
            for i, el in enumerate(doc):
                validate(items, el, f"{path}[{i}]")
    elif t == "string":
        if "minLength" in schema and len(doc) < schema["minLength"]:
            raise ValidationError(f"{path}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], doc):
            raise ValidationError(f"{path}: {doc!r} does not match /{schema['pattern']}/")
    return True

def load(path):
    with open(path) as f:
        return json.load(f)
