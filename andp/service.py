"""Service layer: the library both the CLI and the MCP server call.

Pure functions returning dicts — no printing, no sys.exit. This is what makes
the MCP server library-first: it drives the release machine directly instead
of scraping a CLI's stdout.
"""
import os
import time

from .asc.config import load_account
from .asc.managers import make_managers
from .core.errors import AndpError
from .core.ipa import read_metadata
from .core.release import ReleaseMachine, release_id
from .core.state import StateStore

STATE_DIR = os.path.join(".andp", "state")


def _store(project_root="."):
    return StateStore(os.path.join(project_root, STATE_DIR))


def _managers_for(account_id):
    """Return (managers, account, dry_run). managers is None in dry-run.
    Raises AndpError (not ConfigError) so callers have one error type to catch."""
    from .asc.config import ConfigError
    try:
        account = load_account(account_id)
    except ConfigError as exc:
        raise AndpError(code="config_error", message=str(exc), retryable=False,
                        remediation="Check secrets.yml and the --account name.")
    if not account.is_configured():
        return None, account, True
    return make_managers(account), account, False


def _snapshot_view(snap):
    """The agent-facing projection of a machine snapshot."""
    view = {
        "release_id": snap["release_id"],
        "state": snap["state"],
        "terminal": snap["state"] in ("done", "failed"),
        "bundle_id": snap["bundle_id"],
        "version": snap["version"],
        "build_number": snap["build_number"],
    }
    if snap.get("app_id"):
        view["app_id"] = snap["app_id"]
    if snap.get("build_id"):
        view["build"] = {"id": snap["build_id"],
                         "processing_state": snap.get("processing_state")}
    if snap.get("retry_after"):
        view["retry_after"] = snap["retry_after"]
    if snap.get("needs_approval"):
        # A human (or policy.allow_submit) must open the gate before the release
        # can proceed — signal it explicitly so an agent stops polling blindly.
        view["needs_approval"] = True
        view["next_action"] = "release approve <id> (or set policy.allow_submit)"
    if snap.get("needs_precheck_fix"):
        view["needs_precheck_fix"] = True
        view["precheck_report"] = snap.get("precheck_report")
        view["next_action"] = "fix the precheck errors (andp publish / ASC UI), then poll again"
    if snap.get("submission_id"):
        view["submission_id"] = snap["submission_id"]
    if snap.get("error"):
        view["error"] = snap["error"]
    return view


def release_start(ipa_path, account="primary", group=None, ship=False,
                  metadata_dir=None, skip_precheck=False,
                  project_root=".", clock=time.time, reset=False):
    if not os.path.exists(ipa_path):
        return {"command": "release_start", "ok": False,
                "error": {"code": "ipa_not_found", "message": f"IPA not found: {ipa_path}",
                          "retryable": False, "remediation": "Build the IPA first."}}

    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("release_start", err)
    bundle_id, version, build_number = read_metadata(ipa_path)

    if dry_run:
        rid = release_id(account, bundle_id, version, build_number)
        plan = ["app_record", "upload", "processing"]
        if group:
            plan.append("testflight_group")
        if ship:
            plan += ["version", "build_attached", "compliance"]
            if metadata_dir:
                plan.append("metadata")
            plan.append("submit")
        return {"command": "release_start", "ok": True, "dry_run": True,
                "release_id": rid, "bundle_id": bundle_id, "plan": plan}

    policy = _load_policy(project_root)
    try:
        machine = ReleaseMachine.start(
            _store(project_root), managers, ipa_path,
            account=account, group=group, ship=ship, metadata_dir=metadata_dir,
            skip_precheck=skip_precheck,
            allow_submit=policy["allow_submit"],
            uses_non_exempt_encryption=policy["uses_non_exempt_encryption"],
            clock=clock, reset=reset,
        )
    except AndpError as err:
        return {"command": "release_start", "ok": False, "dry_run": False,
                "error": err.to_dict()}

    return {"command": "release_start", "ok": True, "dry_run": False,
            "release_id": machine.release_id, "state": machine.state, "next": "poll"}


def _load_policy(project_root):
    from .policy import load_policy
    return load_policy(os.path.join(project_root, "andp.yml"))


def publish(bundle_id, version, metadata_dir, account="primary"):
    """Push release notes + screenshots + previews from a folder to a version."""
    from .publish import publish_metadata
    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("publish", err)
    if not os.path.isdir(metadata_dir):
        return {"command": "publish", "ok": False,
                "error": {"code": "not_found", "message": f"No metadata dir: {metadata_dir}",
                          "retryable": False, "remediation": "Create the folder tree."}}
    if dry_run:
        return {"command": "publish", "ok": True, "dry_run": True,
                "bundle_id": bundle_id, "version": version, "metadata_dir": metadata_dir}
    from .asc.client import ASCAPIError
    from .core.errors import from_asc_error, from_unexpected
    try:
        app = managers.apps.find_app(bundle_id)
        if app is None:
            return {"command": "publish", "ok": False,
                    "error": {"code": "app_not_found", "message": f"App {bundle_id} not found.",
                              "retryable": False, "remediation": "Create the app record in ASC."}}
        summary = publish_metadata(managers, app["id"], version, metadata_dir)
    except AndpError as err:
        return _error_result("publish", err)
    except ASCAPIError as err:
        return _error_result("publish", from_asc_error(err))
    except Exception as err:  # network / filesystem — always return a dict
        return _error_result("publish", from_unexpected(err))
    return {"command": "publish", "ok": True, "dry_run": False, **summary}


def precheck(bundle_id, version, account="primary"):
    """Read-only pre-submission validation. Never mutates."""
    from .precheck import run_precheck
    from .asc.client import ASCAPIError
    from .core.errors import from_asc_error, from_unexpected
    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("precheck", err)
    if dry_run:
        return {"command": "precheck", "ok": False,
                "error": {"code": "no_credentials",
                          "message": "Precheck needs real credentials.",
                          "retryable": False, "remediation": "Fill in secrets.yml."}}
    try:
        app = managers.apps.find_app(bundle_id)
        if app is None:
            return {"command": "precheck", "ok": False,
                    "error": {"code": "app_not_found", "message": f"App {bundle_id} not found.",
                              "retryable": False, "remediation": "Create the app record in ASC."}}
        version_res = managers.appstore.find_version(app["id"], version)
        if version_res is None:
            return {"command": "precheck", "ok": False,
                    "error": {"code": "version_not_found",
                              "message": f"No version {version} for {bundle_id}.",
                              "retryable": False,
                              "remediation": "Create the version in App Store Connect first."}}
        report = run_precheck(managers, app["id"], version_res["id"])
    except ASCAPIError as err:
        return _error_result("precheck", from_asc_error(err))
    except Exception as err:
        return _error_result("precheck", from_unexpected(err))
    return {"command": "precheck", **report}


def release_approve(release_id_arg, account="primary", project_root=".", clock=time.time):
    """Record an out-of-band human approval opening the submit gate."""
    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("release_approve", err)
    try:
        machine = ReleaseMachine.load(
            _store(project_root), managers if not dry_run else None,
            release_id_arg, clock=clock)
    except AndpError as err:
        return _error_result("release_approve", err)
    if machine is None:
        return {"command": "release_approve", "ok": False,
                "error": {"code": "not_found", "message": f"No release '{release_id_arg}'.",
                          "retryable": False, "remediation": "Check the id with release_list."}}
    snap = machine.approve()
    view = _snapshot_view(snap)
    view.update({"command": "release_approve", "ok": True})
    return view


def _error_result(command, err):
    payload = err.to_dict() if isinstance(err, AndpError) else {
        "code": "internal_error", "message": str(err), "retryable": False,
        "remediation": "Unexpected error.",
    }
    return {"command": command, "ok": False, "error": payload}


def release_poll(release_id_arg, account="primary", project_root=".", clock=time.time):
    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("release_poll", err)
    if dry_run:
        return {"command": "release_poll", "ok": False,
                "error": {"code": "no_credentials",
                          "message": "Polling a real release requires credentials.",
                          "retryable": False,
                          "remediation": "Fill in secrets.yml (see andp verify)."}}

    # Inject a LIVE policy read so revoking allow_submit in andp.yml stops an
    # in-flight release at the gate (rather than honouring a stale start value).
    allow_submit_fn = lambda: _load_policy(project_root)["allow_submit"]
    try:
        machine = ReleaseMachine.load(_store(project_root), managers, release_id_arg,
                                      clock=clock, allow_submit_fn=allow_submit_fn)
    except AndpError as err:
        return _error_result("release_poll", err)
    if machine is None:
        return {"command": "release_poll", "ok": False,
                "error": {"code": "not_found",
                          "message": f"No release '{release_id_arg}'.",
                          "retryable": False,
                          "remediation": "Start it first with release_start, or check the id."}}

    try:
        snap = machine.step()
    except AndpError as err:
        view = _snapshot_view(machine.snapshot())
        view.update({"command": "release_poll", "ok": False, "error": err.to_dict()})
        return view

    view = _snapshot_view(snap)
    ok = snap["state"] != "failed"
    view.update({"command": "release_poll", "ok": ok})
    return view


def release_status(release_id_arg, project_root="."):
    try:
        snap = _store(project_root).load(release_id_arg)
    except AndpError as err:
        return _error_result("release_status", err)
    if snap is None:
        return {"command": "release_status", "ok": False,
                "error": {"code": "not_found",
                          "message": f"No release '{release_id_arg}'.",
                          "retryable": False,
                          "remediation": "Check the id with release_list."}}
    view = _snapshot_view(snap)
    view.update({"command": "release_status", "ok": True})
    return view


def release_list(project_root="."):
    store = _store(project_root)
    releases = []
    for rid in store.list_ids():
        try:
            snap = store.load(rid)
        except AndpError as err:
            # One corrupted release must not hide all the others.
            releases.append({"release_id": rid, "state": "unreadable",
                             "error": err.to_dict()})
            continue
        if snap:
            releases.append(_snapshot_view(snap))
    return {"command": "release_list", "ok": True, "releases": releases}


def release_reset(ipa_path, account="primary", group=None, project_root=".",
                  clock=time.time):
    """Discard a terminal/stuck release's state and start it over."""
    result = release_start(ipa_path, account=account, group=group,
                           project_root=project_root, clock=clock)
    return result


def release_reset_by_id(release_id_arg, project_root="."):
    """Delete a release's state file by id (recovery escape hatch)."""
    import os
    path = os.path.join(project_root, STATE_DIR, f"{release_id_arg}.json")
    if os.path.exists(path):
        os.remove(path)
        return {"command": "release_reset", "ok": True, "release_id": release_id_arg,
                "detail": "state discarded"}
    return {"command": "release_reset", "ok": False,
            "error": {"code": "not_found", "message": f"No release '{release_id_arg}'.",
                      "retryable": False, "remediation": "Check the id with release_list."}}
