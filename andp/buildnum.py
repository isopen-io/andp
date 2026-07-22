"""Build-number (CFBundleVersion) strategies — pure, no I/O.

ANDP computes the next build number so a release pipeline no longer needs an
external tool just for it; the build step applies the value to the Xcode project
before archiving. Apple caps CFBundleVersion at 18 characters (up to three
dot-separated non-negative integers) — there is no 2^32 per-component limit.
"""
from datetime import datetime, timezone

_DEFAULT_TS_FORMAT = "%Y%m%d%H%M"
_MAX_LEN = 18            # Apple's CFBundleVersion character limit
_MAX_HEX_DIGITS = 14     # 14 hex -> <= 18 decimal chars


def _utc_now():
    return datetime.now(timezone.utc)


def timestamp_build(clock=None, fmt=None):
    """(value, monotonic) where value = clock().strftime(fmt).

    monotonic is True only for the default fixed-width format (every field
    zero-padded, so numeric order == chronological order). Raises ValueError if
    the result is not an all-digit CFBundleVersion of <= 18 chars."""
    clock = clock or _utc_now
    fmt = fmt or _DEFAULT_TS_FORMAT
    value = clock().strftime(fmt)
    if not value.isdigit():
        raise ValueError(
            f"timestamp build '{value}' is not all digits — use a numeric --format")
    if len(value) > _MAX_LEN:
        raise ValueError(
            f"timestamp build '{value}' exceeds {_MAX_LEN} chars (invalid CFBundleVersion)")
    return value, fmt == _DEFAULT_TS_FORMAT


def commit_build(sha, digits=7):
    """int(sha[:digits], 16) as a string. Unique and traceable but NOT
    monotonic. Raises ValueError on a missing/non-hex sha or an out-of-range
    digits count."""
    if digits > _MAX_HEX_DIGITS:
        raise ValueError(
            f"--digits {digits} too large: max {_MAX_HEX_DIGITS} hex (CFBundleVersion <= 18 chars)")
    if not sha:
        raise ValueError("no commit sha (pass --sha or set $GITHUB_SHA)")
    sha = sha.strip().lower()
    if sha.startswith("0x"):
        raise ValueError("sha must be raw hex, not 0x-prefixed")
    short = sha[:digits]
    try:
        return str(int(short, 16))
    except ValueError:
        raise ValueError(f"'{sha}' is not a hex commit sha")
