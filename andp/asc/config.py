"""Multi-account secrets loading for ANDP App Store Connect tooling.

secrets.yml is the real credential store (never committed); secrets.example.yml
is the committed template used as a fallback so CI keeps working without
credentials — accounts loaded from placeholders report is_configured() == False.
"""
import os

import yaml

from .. import paths
from ..errors import ConfigError  # noqa: F401  (re-exported for existing importers)

# Values from secrets.example.yml that mark an account as "not really configured".
_PLACEHOLDER_MARKERS = (
    "PRIMARY_KEY_CONTENT",
    "SECONDARY_KEY_CONTENT",
    "REPLACE_WITH",
)
_PLACEHOLDER_KEY_IDS = ("ABCDE12345", "VWXYZ67890")


class AccountConfig:
    def __init__(self, account_id, key_id, issuer_id, key_content, team_id=None,
                 raw=None, origin=None):
        self.account_id = account_id
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.key_content = key_content
        self.team_id = team_id
        self.raw = raw or {}
        # D'où viennent ces credentials (env/project/global/template/explicit) —
        # un agent qui échoue doit savoir quel fichier a réellement été lu.
        self.origin = origin

    def is_configured(self):
        """True only when the credentials look real (not template placeholders)."""
        return not self.missing_fields()

    def missing_fields(self):
        """Names of credential fields that are absent or still template placeholders."""
        missing = []
        if not self.key_id or self.key_id in _PLACEHOLDER_KEY_IDS:
            missing.append("key_id")
        if not self.issuer_id or any(m in self.issuer_id for m in _PLACEHOLDER_MARKERS):
            missing.append("issuer_id")
        if not self.key_content or any(m in self.key_content for m in _PLACEHOLDER_MARKERS):
            missing.append("key_content")
        return missing


def load_account(account_id, secrets_file=None, project_root="."):
    if secrets_file is not None:
        path, origin = secrets_file, "explicit"
        if not os.path.exists(path):
            raise ConfigError(
                f"No secrets file found (looked for {path})",
                code="config_not_found",
                remediation="Pass an existing path, or drop the secrets_file argument.")
    else:
        misplaced = paths.misplaced_secrets(project_root)
        if misplaced:
            raise ConfigError(
                f"secrets.yml trouvé à la racine du projet ({misplaced}), mais ANDP "
                "ne lit plus cet emplacement.",
                code="config_misplaced",
                remediation="mkdir -p .andp && mv secrets.yml .andp/secrets.yml "
                            "(ou : andp config migrate)",
                context={"misplaced": misplaced,
                         "searched": paths.searched_paths("secrets.yml", project_root)})
        resolution = paths.resolve_config("secrets.yml", project_root)
        if resolution.path is None:
            raise ConfigError(
                "Aucun fichier de credentials trouvé.",
                code="config_not_found",
                remediation="Créez .andp/secrets.yml à partir de secrets.example.yml.",
                context={"resolved": None,
                         "searched": paths.searched_paths("secrets.yml", project_root)})
        path, origin = resolution.path, resolution.origin

    with open(path, "r") as f:
        # Bolt Optimization: Use PyYAML's LibYAML-backed CSafeLoader if available (~8x speedup)
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        data = yaml.load(f, Loader=loader) or {}

    accounts = data.get("accounts", {})
    if account_id not in accounts:
        raise ConfigError(f"Account '{account_id}' not found in {path}",
                          code="account_not_found",
                          remediation="Check the --account name against the accounts "
                                      "block of the secrets file.")

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
        origin=origin,
    )
