"""Typed error taxonomy for agent-decidable failures.

An agent reading an AndpError knows, without parsing prose, whether the same
call can be retried as-is (retryable) and what to change otherwise
(remediation). Codes are stable identifiers.
"""
from dataclasses import dataclass


@dataclass
class AndpError(Exception):
    code: str
    message: str
    retryable: bool
    remediation: str

    def __post_init__(self):
        super().__init__(f"[{self.code}] {self.message}")

    def to_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "remediation": self.remediation,
        }


_STATUS_MAP = {
    401: ("auth_rejected", False,
          "Check key_id, issuer_id and the API key's App Store Connect role."),
    403: ("permission_denied", False,
          "The API key lacks the required App Store Connect role or permission."),
    404: ("not_found", False,
          "Check the resource id or filters — the resource does not exist on this account."),
    409: ("conflict", False,
          "The request violates the API contract; fix the payload field named in the message."),
    429: ("rate_limited", True,
          "Rate limited; wait for Retry-After and retry the same call."),
}


def from_asc_error(exc):
    """Map an ASCAPIError (transport layer) to a typed AndpError."""
    status = getattr(exc, "status", None)
    if status in _STATUS_MAP:
        code, retryable, remediation = _STATUS_MAP[status]
    elif status is not None and 500 <= status < 600:
        code, retryable, remediation = (
            "asc_unavailable", True,
            "Transient Apple-side error; retry the same call.")
    else:
        code, retryable, remediation = (
            "api_error", False,
            "Unexpected App Store Connect response; inspect the message.")
    return AndpError(code=code, message=str(exc), retryable=retryable,
                     remediation=remediation)
