"""Typed error taxonomy: an agent must be able to decide retry vs escalate
from the error object alone — code, retryable, remediation.
"""
import pytest

from andp.core.errors import AndpError, from_asc_error
from andp.asc.client import ASCAPIError


def _asc(status, detail="boom", code=None):
    errors = [{"status": str(status), "title": "T", "detail": detail}]
    if code:
        errors[0]["code"] = code
    return ASCAPIError(status, errors)


def test_401_maps_to_auth_rejected_not_retryable():
    err = from_asc_error(_asc(401))
    assert err.code == "auth_rejected"
    assert err.retryable is False
    assert "issuer" in err.remediation or "key" in err.remediation


def test_403_maps_to_permission_denied():
    err = from_asc_error(_asc(403))
    assert err.code == "permission_denied"
    assert err.retryable is False


def test_404_maps_to_not_found():
    err = from_asc_error(_asc(404))
    assert err.code == "not_found"
    assert err.retryable is False


def test_409_maps_to_contract_conflict_and_keeps_detail():
    err = from_asc_error(_asc(409, detail="You must provide a value for the relationship 'app'"))
    assert err.code == "conflict"
    assert err.retryable is False
    assert "relationship 'app'" in err.message


def test_429_is_retryable():
    err = from_asc_error(_asc(429))
    assert err.code == "rate_limited"
    assert err.retryable is True


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_is_retryable_asc_unavailable(status):
    err = from_asc_error(_asc(status))
    assert err.code == "asc_unavailable"
    assert err.retryable is True


def test_unknown_status_falls_back_to_api_error_not_retryable():
    err = from_asc_error(_asc(418))
    assert err.code == "api_error"
    assert err.retryable is False


def test_error_is_an_exception_with_readable_str():
    err = AndpError(code="x", message="m", retryable=False, remediation="r")
    assert isinstance(err, Exception)
    assert "x" in str(err)
    assert "m" in str(err)


def test_to_dict_serializes_for_agents():
    err = AndpError(code="auth_rejected", message="m", retryable=False, remediation="r")
    assert err.to_dict() == {
        "code": "auth_rejected",
        "message": "m",
        "retryable": False,
        "remediation": "r",
    }
