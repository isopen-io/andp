"""Publish-readiness verdicts and GitHub-Actions rendering.

`verify` and `precheck` answer two questions with two different result shapes:
can this app go to TestFlight, and can this version go to the App Store. These
pure functions normalize both into one **verdict** and render it as a GitHub
Step Summary (markdown), step outputs, and `::error::/::warning::` annotations.

A verdict's `status` is tri-state so a gate never confuses "couldn't tell" with
"ready":
  ready       — evaluated, zero blockers
  not_ready   — evaluated, a genuine blocker (fixable content/state)
  unverified  — could not evaluate: no/placeholder credentials, malformed config,
                or a transient/retryable API error (rate limit, 5xx, network)

No I/O except `write_github_output`, which appends to $GITHUB_OUTPUT.
"""
import json
import uuid

_HEADLINE = {"ready": "✅ Ready", "not_ready": "❌ Not ready",
             "unverified": "⚪ Unverified"}
_READY_OUTPUT = {"ready": "true", "not_ready": "false", "unverified": "unknown"}


def _label(target):
    return "TestFlight" if target == "testflight" else "App Store"


def _blocker(id_, detail, remediation=None, retryable=False):
    b = {"id": id_, "detail": detail}
    if remediation:
        b["remediation"] = remediation
    if retryable:
        b["retryable"] = True
    return b


def _status(evaluated_ok, credentials_ready, blockers):
    if evaluated_ok:
        return "ready"
    if not credentials_ready:
        return "unverified"
    if any(b.get("retryable") for b in blockers):
        return "unverified"
    return "not_ready"


def _reason(target, status, blockers):
    label = _label(target)
    if status == "ready":
        return f"{label} readiness passed."
    head = blockers[0]["detail"] if blockers else ""
    if status == "unverified":
        return (f"{label} readiness could not be verified: {head}" if head
                else f"{label} readiness could not be verified.")
    return f"{label} not ready: {head}" if head else f"{label} not ready."


def _finalize(target, status, credentials_ready, blockers, warnings,
              bundle_id=None, version=None, app=None, note=None, checks=None):
    verdict = {
        "command": "readiness",
        "target": target,
        "status": status,
        "ready": status == "ready",
        "credentials_ready": credentials_ready,
        "reason": _reason(target, status, blockers),
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks or [],
    }
    if bundle_id:
        verdict["bundle_id"] = bundle_id
    if version:
        verdict["version"] = version
    if app:
        verdict["app"] = app
    if note:
        verdict["note"] = note
    return verdict


def testflight_verdict(verify_result, bundle_id=None):
    """Normalize a `service.verify` envelope into a TestFlight readiness verdict."""
    checks = verify_result.get("checks", [])
    ready = bool(verify_result.get("ok"))
    credentials_ready = True
    blockers = []
    for c in checks:
        if c.get("ok"):
            continue
        if c.get("name") == "credentials":
            credentials_ready = False
            missing = c.get("missing")
            detail = c.get("detail", "")
            if missing:
                detail = "missing or placeholder credentials: " + ", ".join(missing)
            blockers.append(_blocker("credentials", detail))
        else:
            blockers.append(_blocker(c.get("name", "check"), c.get("detail", ""),
                                     retryable=bool(c.get("retryable"))))
    status = _status(ready, credentials_ready, blockers)
    return _finalize("testflight", status, credentials_ready, blockers, [],
                     bundle_id=bundle_id, app=verify_result.get("app"), checks=checks)


def appstore_verdict(precheck_result, bundle_id=None, version=None):
    """Normalize a `service.precheck` result into an App Store readiness verdict."""
    error = precheck_result.get("error")
    if error:
        code = error.get("code", "error")
        # A config error means creds could not be loaded — report credentials as
        # not-ready, matching the TestFlight gate for the same condition.
        credentials_ready = code not in ("no_credentials", "config_error")
        retryable = bool(error.get("retryable"))
        blockers = [_blocker(code, error.get("message", ""),
                             remediation=error.get("remediation"), retryable=retryable)]
        if (not credentials_ready) or retryable:
            status = "unverified"
        else:
            status = "not_ready"
        return _finalize("appstore", status, credentials_ready, blockers, [],
                         bundle_id=bundle_id, version=version)

    checks = precheck_result.get("checks", [])
    blockers = [_blocker(c.get("id", "check"), c.get("message", ""))
                for c in checks if c.get("level") == "error"]
    warnings = [_blocker(c.get("id", "check"), c.get("message", ""))
                for c in checks if c.get("level") == "warning"]
    status = "ready" if precheck_result.get("ok") else "not_ready"
    return _finalize("appstore", status, True, blockers, warnings,
                     bundle_id=bundle_id, version=version,
                     note=precheck_result.get("note"), checks=checks)


# ---- rendering -----------------------------------------------------------

def _cell(text):
    return str(text).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def render_markdown(verdict):
    """The `$GITHUB_STEP_SUMMARY` block for one verdict."""
    label = _label(verdict["target"])
    headline = _HEADLINE.get(verdict["status"], verdict["status"])
    lines = [f"## {label} readiness — {headline}", ""]
    if verdict.get("bundle_id"):
        lines.append(f"- **Bundle:** `{verdict['bundle_id']}`")
    if verdict.get("version"):
        lines.append(f"- **Version:** `{verdict['version']}`")
    if verdict.get("app"):
        app = verdict["app"]
        lines.append(f"- **App:** {_cell(app.get('name', '?'))} (id `{app.get('id', '?')}`)")
    lines.append(f"- **Verdict:** {_cell(verdict['reason'])}")
    lines.append("")
    if verdict.get("blockers"):
        lines += ["### Blockers", "", "| Check | Detail | Fix |", "|---|---|---|"]
        for b in verdict["blockers"]:
            lines.append(f"| `{b['id']}` | {_cell(b['detail'])} | {_cell(b.get('remediation', ''))} |")
        lines.append("")
    if verdict.get("warnings"):
        lines += ["### Warnings (advisory)", "", "| Check | Detail |", "|---|---|"]
        for w in verdict["warnings"]:
            lines.append(f"| `{w['id']}` | {_cell(w['detail'])} |")
        lines.append("")
    if verdict.get("note"):
        lines += [f"> {_cell(verdict['note'])}", ""]
    return "\n".join(lines)


def _annot(text):
    # GitHub requires these escapes in workflow-command message data.
    return (str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A"))


def render_annotations(verdict):
    """`::error::`/`::warning::` workflow-command lines (best-effort UX)."""
    title = "ANDP " + _label(verdict["target"]) + " readiness"
    lines = []
    for b in verdict.get("blockers", []):
        lines.append(f"::error title={title}::{b['id']}: {_annot(b['detail'])}")
    for w in verdict.get("warnings", []):
        lines.append(f"::warning title={title}::{w['id']}: {_annot(w['detail'])}")
    return lines


def render_outputs(verdict):
    """Flat string map for `$GITHUB_OUTPUT` (all values are strings)."""
    return {
        "ready": _READY_OUTPUT.get(verdict["status"], "unknown"),
        "status": verdict["status"],
        "reason": verdict["reason"],
        "credentials_ready": "true" if verdict.get("credentials_ready") else "false",
        "blockers": json.dumps(verdict.get("blockers", []), separators=(",", ":")),
        "warnings": json.dumps(verdict.get("warnings", []), separators=(",", ":")),
        "blockers_count": str(len(verdict.get("blockers", []))),
        "warnings_count": str(len(verdict.get("warnings", []))),
    }


def write_github_output(path, mapping):
    """Append outputs to $GITHUB_OUTPUT using a heredoc per value.

    The `name=value` form corrupts on (or is spoofable by) multiline values —
    an API-error `reason` can contain newlines — so every value is written with
    a unique random delimiter that is guaranteed not to appear in the value.
    """
    chunks = []
    for name, value in mapping.items():
        value = str(value)
        delim = f"__ANDP_{uuid.uuid4().hex}__"
        while delim in value:
            delim = f"__ANDP_{uuid.uuid4().hex}__"
        chunks.append(f"{name}<<{delim}\n{value}\n{delim}")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(chunks) + "\n")
