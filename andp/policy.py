"""Project policy from andp.yml — the guardrails for agent-driven publishing."""
import os

import yaml


def load_policy(path="andp.yml"):
    """Return {allow_submit: bool, uses_non_exempt_encryption: bool|None}."""
    policy = {"allow_submit": False, "uses_non_exempt_encryption": None}
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
    return policy
