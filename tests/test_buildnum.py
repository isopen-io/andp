"""Pure build-number strategies in andp/buildnum.py (no I/O, injected clock/sha)."""
from datetime import datetime, timezone

import pytest

from andp import buildnum


def _clock(*a):
    return lambda: datetime(*a, tzinfo=timezone.utc)


def test_timestamp_default_format_digits_and_monotonic():
    value, mono = buildnum.timestamp_build(clock=_clock(2026, 7, 22, 18, 30))
    assert value == "202607221830"
    assert mono is True


def test_timestamp_custom_format_seconds():
    value, _ = buildnum.timestamp_build(clock=_clock(2026, 7, 22, 18, 30, 45),
                                        fmt="%Y%m%d%H%M%S")
    assert value == "20260722183045"


def test_timestamp_rejects_non_digit_format():
    with pytest.raises(ValueError):
        buildnum.timestamp_build(clock=_clock(2026, 7, 22), fmt="v%Y")


def test_timestamp_rejects_over_18_chars():
    with pytest.raises(ValueError):
        buildnum.timestamp_build(clock=_clock(2026, 7, 22), fmt="%Y%m%d%H%M%S%f0000")


def test_timestamp_monotonic_across_minutes():
    v1, _ = buildnum.timestamp_build(clock=_clock(2026, 7, 22, 18, 30))
    v2, _ = buildnum.timestamp_build(clock=_clock(2026, 7, 22, 18, 31))
    assert int(v2) > int(v1)


def test_commit_hex_to_int():
    assert buildnum.commit_build("a1b2c3d4e5", digits=7) == str(int("a1b2c3d", 16))


def test_commit_uppercase_and_whitespace():
    assert buildnum.commit_build("  A1B2C3D\n", digits=7) == str(int("a1b2c3d", 16))


def test_commit_non_hex_raises():
    with pytest.raises(ValueError):
        buildnum.commit_build("zzzzzzz", digits=7)


def test_commit_rejects_0x_prefix():
    with pytest.raises(ValueError):
        buildnum.commit_build("0xabcdef", digits=7)


def test_commit_none_raises():
    with pytest.raises(ValueError):
        buildnum.commit_build(None)


def test_commit_digits_bound():
    with pytest.raises(ValueError):
        buildnum.commit_build("f" * 20, digits=15)  # >14 hex -> >18 chars
