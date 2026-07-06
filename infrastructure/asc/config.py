"""Multi-account secrets loading for ANDP App Store Connect tooling.

secrets.yml is the real credential store (never committed); secrets.example.yml
is the committed template used as a fallback so CI keeps working without
credentials — accounts loaded from placeholders report is_configured() == False.
"""
import os

import yaml

# Values from secrets.example.yml that mark an account as "not really configured".
_PLACEHOLDER_MARKERS = (
    "PRIMARY_KEY_CONTENT",
    "SECONDARY_KEY_CONTENT",
    "REPLACE_WITH",
)
_PLACEHOLDER_KEY_IDS = ("ABCDE12345", "VWXYZ67890")


class ConfigError(Exception):
    """Raised when secrets are missing or malformed."""


class AccountConfig:
    def __init__(self, account_id, key_id, issuer_id, key_content, team_id=None, raw=None):
        self.account_id = account_id
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.key_content = key_content
        self.team_id = team_id
        self.raw = raw or {}

    def is_configured(self):
        """True only when the credentials look real (not template placeholders)."""
        if not self.key_id or not self.issuer_id or not self.key_content:
            return False
        if self.key_id in _PLACEHOLDER_KEY_IDS:
            return False
        return not any(marker in self.key_content for marker in _PLACEHOLDER_MARKERS)


def load_account(account_id, secrets_file=None):
    path = secrets_file
    if path is None:
        path = "secrets.yml" if os.path.exists("secrets.yml") else "secrets.example.yml"
    if not os.path.exists(path):
        raise ConfigError(f"No secrets file found (looked for {path})")

    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    accounts = data.get("accounts", {})
    if account_id not in accounts:
        raise ConfigError(f"Account '{account_id}' not found in {path}")

    account = accounts[account_id] or {}
    asc_api = account.get("asc_api", {}) or {}
    signing = account.get("signing", {}) or {}

    return AccountConfig(
        account_id=account_id,
        key_id=asc_api.get("key_id"),
        issuer_id=asc_api.get("issuer_id"),
        key_content=asc_api.get("key_content"),
        team_id=signing.get("development_team"),
        raw=account,
    )
