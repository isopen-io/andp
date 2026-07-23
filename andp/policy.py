"""Project policy from andp.yml — the guardrails for agent-driven publishing."""
import os

import yaml


import copy

_POLICY_CACHE = {}


def load_policy(path="andp.yml"):
    """Return {allow_submit: bool, uses_non_exempt_encryption: bool|None, store: dict}."""
    if not os.path.exists(path):
        return {"allow_submit": False, "uses_non_exempt_encryption": None, "store": {}}

    # Bolt Optimization: Cache parsed policy to avoid redundant disk I/O and CPU parsing.
    # Uses absolute path as the cache key to prevent test isolation issues when directories change,
    # and uses file modification time (mtime) to handle dynamic configuration changes.
    abs_path = os.path.abspath(path)
    mtime = os.path.getmtime(path)
    if abs_path in _POLICY_CACHE and _POLICY_CACHE[abs_path]["mtime"] >= mtime:
        return copy.deepcopy(_POLICY_CACHE[abs_path]["policy"])

    policy = {"allow_submit": False, "uses_non_exempt_encryption": None, "store": {}}
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

    _POLICY_CACHE[abs_path] = {"mtime": mtime, "policy": policy}
    return copy.deepcopy(policy)
