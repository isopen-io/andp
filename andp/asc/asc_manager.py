"""ANDP App Store Connect CLI.

Wires auth -> client -> managers and exposes the commands used by the
shell wrappers (asc-manager.sh) and the CI pipeline.

Without real credentials (secrets.example.yml placeholders) every command
runs in DRY-RUN mode: it validates inputs and prints what it would do,
so CI stays green without an Apple account.
"""
import json
import os
import sys

from .apps import AppsManager
from .appstore import AppStoreManager
from .auth import ASCAuth, ASCAuthError
from .builds import BuildProcessingError, BuildsManager
from .client import ASCAPIError, ASCClient
from .config import ConfigError, load_account
from .managers import Managers, make_managers
from .testflight import TestFlightManager

USAGE = """Usage: asc_manager.py <command> [args] [--account <account_id>]

Commands (all accept --json for a structured, agent-friendly envelope):
  verify [bundle_id]                             Preflight: credentials -> JWT -> API -> app lookup
                                                 (exits 1 when publishing is not possible)
  upload <ipa_path>                              Upload a build (Build Upload API)
  release <ipa_path> [--group <name>]            verify -> upload -> wait processing -> TestFlight group
  status <bundle_id> <build_number>              Poll build processing state
  testflight <bundle_id> <group> add [emails...] Manage TestFlight group testers
  submit <bundle_id> <version>                   Submit a version for App Review
  precheck <bundle_id> <version>                 Read-only App Store pre-submission validation
  readiness testflight <bundle_id>               Can this app go to TestFlight cleanly? (0/1/3)
  readiness appstore <bundle_id> <version>       Can this version go to the App Store cleanly?
  store <pricing|availability|age-rating|apply>  Configure price, territories, age rating
"""


def _read_file_stripped(path, default=""):
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return default


def _ipa_metadata(ipa_path):
    """(bundle_id, version, build) from the IPA's own Info.plist — the upload
    metadata must match the binary, not the calling repo. All None if unreadable."""
    import plistlib
    import zipfile

    try:
        with zipfile.ZipFile(ipa_path) as zf:
            for name in zf.namelist():
                if name.endswith(".app/Info.plist") and name.startswith("Payload/"):
                    info = plistlib.loads(zf.read(name))
                    return (
                        info.get("CFBundleIdentifier"),
                        info.get("CFBundleShortVersionString"),
                        info.get("CFBundleVersion"),
                    )
    except Exception:
        pass
    return None, None, None


# Failing-check name -> the human epilogue line (verify prints one FAILED reason
# chosen by which check failed). Kept here because the failure prose is CLI-only;
# the machine envelope lives in service.verify_checks.
_VERIFY_EPILOGUE = {
    "credentials": "PREFLIGHT FAILED — fill in the fields above (template: secrets.example.yml).",
    "jwt": "PREFLIGHT FAILED — the private key is not a usable ES256 (.p8) key.",
    "app_record": "PREFLIGHT FAILED — create the app record in the ASC UI first.",
    "api_auth": "PREFLIGHT FAILED — check key_id/issuer_id and the key's ASC role.",
}


def _cmd_verify(account, managers, dry_run, args, json_mode=False):
    """Publish preflight. Unlike the other commands this one FAILS in DRY-RUN:
    its whole point is to tell the truth about whether publishing can work.

    Library-first: the checks live in service.verify_checks; this handler owns
    only the human rendering (JSON mode prints the envelope verbatim)."""
    from .. import service

    bundle_id = args[0] if args else None
    result = service.verify_checks(account, managers, bundle_id)

    if json_mode:
        print(json.dumps(result))
        return 0 if result["ok"] else 1

    print(f"ASC publish preflight (account '{account.account_id}'):")
    for c in result["checks"]:
        if c["name"] == "credentials" and not c["ok"]:
            for name in c.get("missing", []):
                print(f"  ❌ credentials — missing: {name} (absent or placeholder in secrets.yml)")
        else:
            print(f"  {'✅' if c['ok'] else '❌'} {c['detail']}")

    if result["ok"]:
        print("PREFLIGHT PASSED — the tool can publish to App Store Connect.")
        return 0
    failed = next((c for c in result["checks"] if not c["ok"]), None)
    print(_VERIFY_EPILOGUE.get(failed["name"] if failed else "", "PREFLIGHT FAILED"))
    return 1


def _cmd_upload(account, managers, dry_run, args, json_mode=False):
    if not args:
        print("Error: IPA path required for upload.")
        return 2
    ipa_path = args[0]
    if not os.path.exists(ipa_path):
        print(f"Error: IPA not found: {ipa_path}")
        return 1
    bundle_id, version, build_number = _ipa_metadata(ipa_path)
    if not version:
        version = _read_file_stripped("VERSION", "0.0.0")
    if not build_number:
        build_number = _read_file_stripped("BUILD_NUMBER", "0")

    if dry_run:
        if json_mode:
            print(json.dumps({"command": "upload", "ok": True, "dry_run": True,
                              "ipa": ipa_path, "bundle_id": bundle_id,
                              "version": version, "build_number": build_number}))
        else:
            print(
                f"[DRY-RUN] Would upload {ipa_path} as version {version} "
                f"(build {build_number}) via the Build Upload API."
            )
        return 0

    if not bundle_id:
        print(f"Error: Could not read CFBundleIdentifier from {ipa_path}.")
        return 1
    app = managers.apps.find_app(bundle_id)
    if app is None:
        print(f"Error: App {bundle_id} not found in App Store Connect.")
        return 1

    upload_id = managers.builds.upload_ipa(
        ipa_path, version=version, build_number=build_number, app_id=app["id"]
    )
    if json_mode:
        print(json.dumps({"command": "upload", "ok": True, "dry_run": False,
                          "ipa": ipa_path, "bundle_id": bundle_id,
                          "version": version, "build_number": build_number,
                          "app_id": app["id"], "upload_id": upload_id}))
    else:
        print(f"Upload started: buildUploads/{upload_id}")
    return 0


def _cmd_release(account, managers, dry_run, args, json_mode=False):
    """One-shot automation primitive: verify app record -> upload -> wait for
    Apple processing -> optional TestFlight group assignment.

    Subcommands expose the resumable machine for agents:
      release start <ipa> [--group G]   begin (or resume) a release -> release_id
      release poll <id>                 advance one non-blocking step
      release status <id>               read state without advancing
      release list                      list all releases
    """
    args = list(args)
    if args and args[0] in ("start", "poll", "status", "list", "reset", "approve"):
        return _cmd_release_sub(account, args[0], args[1:], json_mode)

    if "--ship" in args:
        # The App Store path is resumable and gated — it cannot run as a
        # blocking one-shot. Direct the user to the agent surface.
        print("The App Store path is resumable and gated; use `release start "
              "--ship` then `release poll`/`release approve`.")
        return 2
    group_name = None
    if "--group" in args:
        idx = args.index("--group")
        group_name = args[idx + 1]
        del args[idx:idx + 2]
    if not args:
        print("Usage: release <ipa_path> [--group <name>]")
        return 2
    ipa_path = args[0]
    if not os.path.exists(ipa_path):
        print(f"Error: IPA not found: {ipa_path}")
        return 1
    bundle_id, version, build_number = _ipa_metadata(ipa_path)

    if dry_run:
        planned = ["app_record", "upload", "processing"] + (["testflight_group"] if group_name else [])
        if json_mode:
            print(json.dumps({"command": "release", "ok": True, "dry_run": True,
                              "ipa": ipa_path, "bundle_id": bundle_id,
                              "stages_planned": planned}))
        else:
            print(f"[DRY-RUN] Would release {ipa_path}: {' -> '.join(planned)}.")
        return 0

    stages = []

    def stage(name, ok, detail):
        stages.append({"name": name, "ok": ok, "detail": detail})
        if not json_mode:
            print(f"  {'✅' if ok else '❌'} {name}: {detail}")

    def finish(ok, build=None, app_id=None, upload_id=None):
        if json_mode:
            payload = {"command": "release", "ok": ok, "dry_run": False,
                       "ipa": ipa_path, "bundle_id": bundle_id, "stages": stages}
            if app_id:
                payload["app_id"] = app_id
            if upload_id:
                payload["upload_id"] = upload_id
            if build is not None:
                payload["build"] = {
                    "id": build["id"],
                    "processing_state": build["attributes"].get("processingState"),
                }
            print(json.dumps(payload))
        else:
            print("RELEASE " + ("SUCCEEDED" if ok else "FAILED"))
        return 0 if ok else 1

    if not bundle_id:
        stage("app_record", False, f"Could not read CFBundleIdentifier from {ipa_path}")
        return finish(False)
    app = managers.apps.find_app(bundle_id)
    if app is None:
        stage("app_record", False, f"App {bundle_id} not found in App Store Connect")
        return finish(False)
    app_name = (app.get("attributes") or {}).get("name", "?")
    stage("app_record", True, f"{app_name} ({bundle_id}) — id {app['id']}")

    upload_id = managers.builds.upload_ipa(
        ipa_path, version=version, build_number=build_number, app_id=app["id"]
    )
    stage("upload", True, f"buildUploads/{upload_id} ({version} build {build_number})")

    try:
        build = managers.builds.wait_for_processing(app["id"], build_number)
    except BuildProcessingError as exc:
        stage("processing", False, str(exc))
        return finish(False, app_id=app["id"], upload_id=upload_id)
    stage("processing", True, f"build {build['id']} is {build['attributes'].get('processingState')}")

    if group_name:
        group = managers.testflight.ensure_group(app["id"], group_name)
        managers.testflight.add_build_to_group(group["id"], build["id"])
        stage("testflight_group", True, f"build linked to group '{group_name}' ({group['id']})")

    return finish(True, build=build, app_id=app["id"], upload_id=upload_id)


def _cmd_release_sub(account, sub, args, json_mode):
    """Agent-facing release subcommands, backed by the library service layer."""
    from .. import service

    group = None
    args = list(args)
    if "--group" in args:
        idx = args.index("--group")
        group = args[idx + 1]
        del args[idx:idx + 2]
    ship = False
    if "--ship" in args:
        ship = True
        args.remove("--ship")
    metadata_dir = None
    if "--metadata" in args:
        idx = args.index("--metadata")
        metadata_dir = args[idx + 1]
        del args[idx:idx + 2]
    skip_precheck = False
    if "--no-precheck" in args:
        skip_precheck = True
        args.remove("--no-precheck")

    if sub == "start":
        if not args:
            print("Usage: release start <ipa_path> [--group <name>] [--ship] "
                  "[--metadata <dir>] [--no-precheck]")
            return 2
        result = service.release_start(args[0], account=account.account_id,
                                       group=group, ship=ship, metadata_dir=metadata_dir,
                                       skip_precheck=skip_precheck)
    elif sub == "poll":
        if not args:
            print("Usage: release poll <release_id>")
            return 2
        result = service.release_poll(args[0], account=account.account_id)
    elif sub == "status":
        if not args:
            print("Usage: release status <release_id>")
            return 2
        result = service.release_status(args[0])
    elif sub == "approve":
        if not args:
            print("Usage: release approve <release_id>")
            return 2
        result = service.release_approve(args[0], account=account.account_id)
    elif sub == "reset":
        if not args:
            print("Usage: release reset <release_id>")
            return 2
        result = service.release_reset_by_id(args[0])
    else:  # list
        result = service.release_list()

    if json_mode:
        print(json.dumps(result))
    else:
        _print_release_human(result)
    return 0 if result.get("ok", True) else 1


def _print_release_human(result):
    cmd = result.get("command", "release")
    if not result.get("ok", True):
        err = result.get("error", {})
        print(f"❌ {cmd}: {err.get('message', 'failed')}")
        if err.get("remediation"):
            print(f"   → {err['remediation']}")
        return
    if cmd == "release_list":
        for r in result["releases"]:
            print(f"  {r['release_id']}: {r['state']}")
        if not result["releases"]:
            print("  (no releases)")
        return
    if result.get("dry_run"):
        print(f"[DRY-RUN] {result['release_id']}: {' -> '.join(result.get('plan', []))}")
        return
    line = f"{result['release_id']}: {result['state']}"
    if result.get("retry_after"):
        line += f" (poll again in {result['retry_after']}s)"
    if result.get("build"):
        line += f" — build {result['build']['id']} {result['build'].get('processing_state', '')}"
    print(line)


def _cmd_status(account, managers, dry_run, args, json_mode=False):
    if len(args) < 2:
        print("Usage: status <bundle_id> <build_number>")
        return 2
    bundle_id, build_number = args[0], args[1]

    if dry_run:
        print(f"[DRY-RUN] Would poll processing state of build {build_number} for {bundle_id}.")
        return 0

    app = managers.apps.find_app(bundle_id)
    if app is None:
        print(f"Error: App {bundle_id} not found in App Store Connect.")
        return 1
    build = managers.builds.wait_for_processing(app["id"], build_number)
    print(f"Build {build_number}: {build['attributes']['processingState']}")
    return 0


def _cmd_testflight(account, managers, dry_run, args, json_mode=False):
    if len(args) < 3:
        print("Usage: testflight <bundle_id> <group_name> <add> [tester_emails...]")
        return 2
    bundle_id, group_name, action = args[0], args[1], args[2]
    emails = args[3:]

    if dry_run:
        print(
            f"[DRY-RUN] Would ensure group '{group_name}' on {bundle_id} "
            f"and {action} testers: {', '.join(emails) or '(none)'}"
        )
        return 0

    app = managers.apps.find_app(bundle_id)
    if app is None:
        print(f"Error: App {bundle_id} not found in App Store Connect.")
        return 1
    group = managers.testflight.ensure_group(app["id"], group_name)
    if action == "add":
        for email in emails:
            managers.testflight.add_tester(group["id"], email)
            print(f"Added tester {email} to '{group_name}'.")
    else:
        print(f"Error: Unsupported testflight action '{action}'.")
        return 2
    return 0


def _cmd_submit(account, managers, dry_run, args, json_mode=False):
    if len(args) < 2:
        print("Usage: submit <bundle_id> <version>")
        return 2
    bundle_id, version = args[0], args[1]

    if dry_run:
        print(f"[DRY-RUN] Would submit version {version} of {bundle_id} for App Review.")
        return 0

    app = managers.apps.find_app(bundle_id)
    if app is None:
        print(f"Error: App {bundle_id} not found in App Store Connect.")
        return 1
    app_store_version = managers.appstore.ensure_version(app["id"], version)

    # Apple rejects a review submission whose version has no build attached.
    build = managers.builds.latest_valid_build(app["id"])
    if build is None:
        print(
            f"Error: No VALID build found for {bundle_id}. Upload a build and wait "
            "for it to finish processing before submitting for review."
        )
        return 1
    managers.appstore.attach_build(app_store_version["id"], build["id"])

    submission = managers.appstore.submit_for_review(app["id"], app_store_version["id"])
    print(f"Review submission {submission['id']}: {submission['attributes'].get('state')}")
    return 0


def _cmd_publish(account, managers, dry_run, args, json_mode=False):
    """Push release notes + screenshots + previews from a folder tree."""
    from .. import service
    if len(args) < 3:
        print("Usage: publish <bundle_id> <version> <metadata_dir>")
        return 2
    result = service.publish(args[0], args[1], args[2], account=account.account_id)
    if json_mode:
        print(json.dumps(result))
    elif result.get("ok"):
        if result.get("dry_run"):
            print(f"[DRY-RUN] Would publish metadata from {args[2]} for {args[0]} {args[1]}.")
        else:
            for locale, s in result.get("locales", {}).items():
                print(f"  {locale}: metadata {s['metadata']}, "
                      f"{s['screenshots']} screenshots, {s['previews']} previews")
    else:
        err = result.get("error", {})
        print(f"❌ publish: {err.get('message', 'failed')}")
    return 0 if result.get("ok") else 1


def _cmd_precheck(account, managers, dry_run, args, json_mode=False):
    """Read-only pre-submission validation."""
    from .. import service
    if len(args) < 2:
        print("Usage: precheck <bundle_id> <version>")
        return 2
    result = service.precheck(args[0], args[1], account=account.account_id)
    if json_mode:
        print(json.dumps(result))
    elif result.get("error"):
        print(f"❌ precheck: {result['error']['message']}")
    else:
        for c in result.get("checks", []):
            mark = "❌" if c["level"] == "error" else "⚠️ "
            print(f"  {mark} {c['id']}: {c['message']}")
        verdict = "PASSED" if result["ok"] else "FAILED"
        print(f"PRECHECK {verdict} — {result['errors']} errors, {result['warnings']} warnings")
    return 0 if result.get("ok") else 1


_READINESS_USAGE = ("Usage: readiness <testflight|appstore> <bundle_id> [<version>] "
                    "[--soft] [--allow-unverified]")


def _take_opt(args, name):
    """Pop `--name value` from args (mutating) and return value, or None."""
    if name in args:
        idx = args.index(name)
        value = args[idx + 1] if idx + 1 < len(args) else None
        del args[idx:idx + 2]
        return value
    return None


def _take_flag(args, name):
    if name in args:
        args.remove(name)
        return True
    return False


def _print_readiness_human(verdict):
    icon = {"ready": "✅", "not_ready": "❌", "unverified": "⚪"}.get(verdict["status"], "")
    print(f"{icon} {verdict['reason']}")
    for b in verdict.get("blockers", []):
        print(f"  ❌ {b['id']}: {b['detail']}")
        if b.get("remediation"):
            print(f"     → {b['remediation']}")
    for w in verdict.get("warnings", []):
        print(f"  ⚠️  {w['id']}: {w['detail']}")
    if verdict.get("note"):
        print(f"  ℹ️  {verdict['note']}")


def _cmd_readiness(account, managers, dry_run, args, json_mode=False):
    """Publish-readiness gate for CI: verify (TestFlight) / precheck (App Store),
    normalized to a tri-state verdict with GitHub-native output.

    Exit: 0 ready, 1 not_ready, 3 unverified (no creds / transient), 2 usage.
    --soft downgrades not_ready->0; --allow-unverified downgrades unverified->0."""
    from .. import service
    from ..readiness import (render_annotations, render_markdown, render_outputs,
                             write_github_output)

    args = list(args)
    soft = _take_flag(args, "--soft")
    allow_unverified = _take_flag(args, "--allow-unverified")

    if not args:
        print(_READINESS_USAGE)
        return 2
    target = args[0]
    if target == "testflight":
        if len(args) < 2:
            print(_READINESS_USAGE)
            return 2
        verdict = service.readiness_testflight(args[1], account=account.account_id)
    elif target == "appstore":
        if len(args) < 3:
            print("Usage: readiness appstore <bundle_id> <version> [--soft] [--allow-unverified]")
            return 2
        verdict = service.readiness_appstore(args[1], args[2], account=account.account_id)
    else:
        print(_READINESS_USAGE)
        print(f"Unknown readiness target: {target}")
        return 2

    # GitHub Actions side-effects — inert when the env vars are absent (local runs).
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as fh:
                fh.write(render_markdown(verdict) + "\n")
        except OSError:
            pass
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        try:
            write_github_output(output_path, render_outputs(verdict))
        except OSError:
            pass
    # Annotations render reliably from stdout; suppress under --json to keep it pure.
    if os.environ.get("GITHUB_ACTIONS") and not json_mode:
        for line in render_annotations(verdict):
            print(line)

    if json_mode:
        print(json.dumps(verdict))
    else:
        _print_readiness_human(verdict)

    status = verdict["status"]
    if status == "ready":
        return 0
    if status == "unverified":
        return 0 if allow_unverified else 3
    return 0 if soft else 1


_STORE_USAGE = ("Usage: store <pricing|availability|age-rating|apply> <bundle_id> "
                "[--territory USA] [--price 0.00|free] [--territories USA,FRA|--all] "
                "[--new-territories] [--config <json>]")


def _cmd_store(account, managers, dry_run, args, json_mode=False):
    """Declarative store configuration: pricing, territory availability and age
    rating. Reconciles to a desired state; `apply` reads it all from andp.yml."""
    from .. import service
    args = list(args)
    if not args:
        print(_STORE_USAGE)
        return 2
    sub, rest = args[0], list(args[1:])
    acct = account.account_id

    if sub == "pricing":
        territory = _take_opt(rest, "--territory")
        price = _take_opt(rest, "--price")
        if not rest:
            print("Usage: store pricing <bundle_id> [--territory USA] [--price 0.00|free]")
            return 2
        result = service.configure_pricing(rest[0], account=acct,
                                           base_territory=territory, price=price)
    elif sub == "availability":
        all_flag = _take_flag(rest, "--all")
        new_terr = True if _take_flag(rest, "--new-territories") else None
        terr_opt = _take_opt(rest, "--territories")
        if not rest:
            print("Usage: store availability <bundle_id> [--territories USA,FRA|--all] "
                  "[--new-territories]")
            return 2
        territories = ("all" if all_flag
                       else [t for t in terr_opt.split(",") if t] if terr_opt else None)
        result = service.configure_availability(
            rest[0], account=acct, territories=territories,
            available_in_new_territories=new_terr)
    elif sub in ("age-rating", "age_rating"):
        config = _take_opt(rest, "--config")
        if not rest:
            print("Usage: store age-rating <bundle_id> [--config <json>]")
            return 2
        declaration = {"config_path": config} if config else None
        result = service.configure_age_rating(rest[0], account=acct, declaration=declaration)
    elif sub == "apply":
        if not rest:
            print("Usage: store apply <bundle_id>")
            return 2
        result = service.configure_store(rest[0], account=acct)
    else:
        print(_STORE_USAGE)
        return 2

    if json_mode:
        print(json.dumps(result))
    else:
        _print_store_human(result)
    return 0 if result.get("ok", True) else 1


def _print_store_human(result):
    cmd = result.get("command", "store")
    if not result.get("ok", True):
        err = result.get("error", {})
        print(f"❌ {cmd}: {err.get('message', 'failed')}")
        if err.get("remediation"):
            print(f"   → {err['remediation']}")
        return
    if cmd == "configure_store":
        for name, block in result.get("blocks", {}).items():
            if "skipped" in block:
                print(f"  {name}: skipped (not configured)")
            elif block.get("ok"):
                print(f"  {name}: {'changed' if block.get('changed') else 'unchanged'}")
            else:
                print(f"  {name}: ❌ {block.get('error', {}).get('message', 'failed')}")
        return
    prefix = "[DRY-RUN] " if result.get("dry_run") else ""
    state = "would set" if result.get("dry_run") else (
        "changed" if result.get("changed") else "unchanged")
    print(f"{prefix}{cmd}: {state}")
    for w in result.get("warnings", []):
        print(f"  ⚠️  {w}")


COMMANDS = {
    "verify": _cmd_verify,
    "upload": _cmd_upload,
    "release": _cmd_release,
    "status": _cmd_status,
    "testflight": _cmd_testflight,
    "submit": _cmd_submit,
    "publish": _cmd_publish,
    "precheck": _cmd_precheck,
    "readiness": _cmd_readiness,
    "store": _cmd_store,
}


def main(argv):
    if not argv:
        print(USAGE)
        return 2

    args = list(argv)
    account_id = "primary"
    if "--account" in args:
        idx = args.index("--account")
        account_id = args[idx + 1]
        del args[idx:idx + 2]
    json_mode = "--json" in args
    if json_mode:
        args.remove("--json")

    command, command_args = args[0], args[1:]
    handler = COMMANDS.get(command)
    if handler is None:
        print(USAGE)
        print(f"Unknown command: {command}")
        return 2

    try:
        account = load_account(account_id)
    except ConfigError as exc:
        print(f"Error: {exc}")
        return 1

    dry_run = not account.is_configured()
    if dry_run:
        # No usable credentials: never build managers (empty/placeholder creds
        # make ASCAuth raise — e.g. a fork PR with unset secrets). Handlers know
        # to run in DRY-RUN from the flag; the banner is human-mode only.
        if not json_mode:
            print(
                f"No real App Store Connect credentials for account '{account_id}' "
                "(placeholders detected) — running in DRY-RUN mode."
            )
        managers = None
    else:
        managers = make_managers(account)

    return handler(account, managers, dry_run, command_args, json_mode=json_mode)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
