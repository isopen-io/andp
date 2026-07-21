"""Project policy from andp.yml — the guardrails for agent-driven publishing."""
import os

import yaml


def load_policy(path="andp.yml"):
    """Return {allow_submit: bool, uses_non_exempt_encryption: bool|None, store: dict}."""
    policy = {"allow_submit": False, "uses_non_exempt_encryption": None, "store": {}}
    if os.path.exists(path):
        with open(path, "r") as f:
            loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
            data = yaml.load(f, Loader=loader) or {}
        pol = data.get("policy") or {}
        if "allow_submit" in pol:
            policy["allow_submit"] = bool(pol["allow_submit"])
        compliance = data.get("compliance") or {}
        if "uses_non_exempt_encryption" in compliance:
            policy["uses_non_exempt_encryption"] = bool(
                compliance["uses_non_exempt_encryption"])
        # Isolated so a malformed store: block can never regress allow_submit
        # or compliance parsing above (N7).
        store = data.get("store")
        if isinstance(store, dict):
            policy["store"] = store
    return policy
