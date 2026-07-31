"""Project policy from andp.yml — the guardrails for agent-driven publishing."""
import copy
import os

import yaml

# Parsed policies, keyed by absolute path. A single command reads the policy up
# to three times (service.py: precheck, store, allow_submit), so the parse is
# worth caching — unlike the credentials, which are read once and never cached.
_POLICY_CACHE = {}


def load_policy(path="andp.yml"):
    """Return {allow_submit: bool, allow_stale_unlock: bool,
    uses_non_exempt_encryption: bool|None, store: dict}."""
    if not os.path.exists(path):
        return {"allow_submit": False, "allow_stale_unlock": False,
                "uses_non_exempt_encryption": None, "store": {}}

    # Absolute path as the key, so a change of working directory cannot serve
    # one project's policy to another. Any change of mtime invalidates — not
    # just a newer one: restoring an older file (git checkout, tar extract) can
    # move mtime backwards, and `>=` would keep serving the stale policy.
    abs_path = os.path.abspath(path)
    mtime = os.path.getmtime(path)
    cached = _POLICY_CACHE.get(abs_path)
    if cached is not None and cached["mtime"] == mtime:
        # A deep copy, because callers index into the returned dict and a shared
        # mutable would let one command's edit leak into the next.
        return copy.deepcopy(cached["policy"])

    policy = {"allow_submit": False, "allow_stale_unlock": False,
              "uses_non_exempt_encryption": None, "store": {}}
    with open(path, "r") as f:
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        data = yaml.load(f, Loader=loader) or {}
    pol = data.get("policy") or {}
    if "allow_submit" in pol:
        policy["allow_submit"] = bool(pol["allow_submit"])
    # Standing, auditable consent for cancelling a >1 h review submission over
    # MCP (forfeits its queue position) — the unlock counterpart of allow_submit.
    if "allow_stale_unlock" in pol:
        policy["allow_stale_unlock"] = bool(pol["allow_stale_unlock"])
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
