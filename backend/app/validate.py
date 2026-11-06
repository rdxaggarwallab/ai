"""Strict reading of JSON request fields: wrong types become a 400, never a 500."""
import math

from flask import abort, request


def body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        abort(400, "Request body must be a JSON object")
    return data


def get_str(data: dict, key: str, *, required=False, default="", max_len=10_000, label=None):
    label = label or key.replace("_", " ").capitalize()
    value = data.get(key)
    if value is None:
        if required:
            abort(400, f"{label} is required")
        return default
    if not isinstance(value, str):
        abort(400, f"{label} must be text")
    if required and not value.strip():
        abort(400, f"{label} is required")
    if len(value) > max_len:
        abort(400, f"{label} is too long (max {max_len} characters)")
    return value


def get_int(data: dict, key: str, *, default=None, lo=None, hi=None, label=None):
    label = label or key.replace("_", " ").capitalize()
    value = data.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool):
        abort(400, f"{label} must be a whole number")
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        value = int(value)
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        value = int(value)
    if not isinstance(value, int):
        abort(400, f"{label} must be a whole number")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        abort(400, f"{label} must be between {lo} and {hi}")
    return value


def get_number(data: dict, key: str, *, lo, hi, label=None):
    label = label or key.replace("_", " ").capitalize()
    value = data.get(key)
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            abort(400, f"{label} must be a number")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        abort(400, f"{label} must be a number")
    if not lo <= value <= hi:
        abort(400, f"{label} must be between {lo} and {hi}")
    return float(value)


def get_bool(data: dict, key: str, *, default=False, label=None):
    label = label or key.replace("_", " ").capitalize()
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false", "1", "0"):
        return value.lower() in ("true", "1")
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    abort(400, f"{label} must be true or false")
