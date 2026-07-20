"""ANDP App Store Connect CLI.

Wires auth -> client -> managers and exposes the commands used by the
shell wrappers (asc-manager.sh) and the CI pipeline.

Without real credentials (secrets.example.yml placeholders) every command
runs in DRY-RUN mode: it validates inputs and prints what it would do,
so CI stays green without an Apple account.
"""
import os
import sys

from .apps import AppsManager
from .appstore import AppStoreManager
from .auth import ASCAuth, ASCAuthError
from .builds import BuildsManager
from .client import ASCAPIError, ASCClient
from .config import ConfigError, load_account
from .testflight import TestFlightManager

USAGE = """Usage: asc_manager.py <command> [args] [--account <account_id>]

Commands:
  verify [bundle_id]                             Preflight: credentials -> JWT -> API -> app lookup
                                                 (exits 1 when publishing is not possible)
  upload <ipa_path>                              Upload a build (Build Upload API)
  status <bundle_id> <build_number>              Poll build processing state
  testflight <bundle_id> <group> add [emails...] Manage TestFlight group testers
  submit <bundle_id> <version>                   Submit a version for App Review
"""


class Managers:
    def __init__(self, client):
        self.client = client
        self.apps = AppsManager(client)
        self.builds = BuildsManager(client)
        self.testflight = TestFlightManager(client)
        self.appstore = AppStoreManager(client)


def make_managers(account):
    auth = ASCAuth(
        key_id=account.key_id,
        issuer_id=account.issuer_id,
        private_key=account.key_content,
    )
    return Managers(ASCClient(auth))


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


def _cmd_verify(account, managers, dry_run, args):
    """Publish preflight. Unlike the other commands this one FAILS in DRY-RUN:
    its whole point is to tell the truth about whether publishing can work."""
    bundle_id = args[0] if args else None
    print(f"ASC publish preflight (account '{account.account_id}'):")

    missing = account.missing_fields()
    if missing:
        for name in missing:
            print(f"  ❌ credentials — missing: {name} (absent or placeholder in secrets.yml)")
        print("PREFLIGHT FAILED — fill in the fields above (template: secrets.example.yml).")
        return 1
    print(f"  ✅ credentials — key_id {account.key_id}, issuer_id set, private key present")

    try:
        managers.client.auth.token()
    except ASCAuthError as exc:
        print(f"  ❌ JWT signing failed: {exc}")
        print("PREFLIGHT FAILED — the private key is not a usable ES256 (.p8) key.")
        return 1
    print("  ✅ JWT signed (ES256)")

    try:
        if bundle_id:
            app = managers.apps.find_app(bundle_id)
            print("  ✅ API authentication accepted")
            if app is None:
                print(f"  ❌ app '{bundle_id}' not found on this App Store Connect account")
                print("PREFLIGHT FAILED — create the app record in the ASC UI first.")
                return 1
            name = (app.get("attributes") or {}).get("name", "?")
            print(f"  ✅ app found: {name} ({bundle_id}) — id {app['id']}")
        else:
            managers.client.get("/v1/apps", params={"limit": 1})
            print("  ✅ API authentication accepted (GET /v1/apps)")
    except ASCAPIError as exc:
        print(f"  ❌ API rejected the request: {exc}")
        print("PREFLIGHT FAILED — check key_id/issuer_id and the key's ASC role.")
        return 1

    print("PREFLIGHT PASSED — the tool can publish to App Store Connect.")
    return 0


def _cmd_upload(account, managers, dry_run, args):
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
    print(f"Upload started: buildUploads/{upload_id}")
    return 0


def _cmd_status(account, managers, dry_run, args):
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


def _cmd_testflight(account, managers, dry_run, args):
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


def _cmd_submit(account, managers, dry_run, args):
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
    submission = managers.appstore.submit_for_review(app["id"], app_store_version["id"])
    print(f"Review submission {submission['id']}: {submission['attributes'].get('state')}")
    return 0


COMMANDS = {
    "verify": _cmd_verify,
    "upload": _cmd_upload,
    "status": _cmd_status,
    "testflight": _cmd_testflight,
    "submit": _cmd_submit,
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
        print(
            f"No real App Store Connect credentials for account '{account_id}' "
            "(placeholders detected) — running in DRY-RUN mode."
        )
        managers = None
    else:
        managers = make_managers(account)

    return handler(account, managers, dry_run, command_args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
