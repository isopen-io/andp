"""ANDP App Store Connect CLI.

Wires auth -> client -> managers and exposes the commands used by the
shell wrappers (asc-manager.sh) and the CI pipeline.

Without real credentials (secrets.example.yml placeholders) every command
runs in DRY-RUN mode: it validates inputs and prints what it would do,
so CI stays green without an Apple account.
"""
import os
import sys

from apps import AppsManager
from appstore import AppStoreManager
from auth import ASCAuth
from builds import BuildsManager
from client import ASCClient
from config import ConfigError, load_account
from testflight import TestFlightManager

USAGE = """Usage: asc_manager.py <command> [args] [--account <account_id>]

Commands:
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


def _cmd_upload(managers, dry_run, args):
    if not args:
        print("Error: IPA path required for upload.")
        return 2
    ipa_path = args[0]
    if not os.path.exists(ipa_path):
        print(f"Error: IPA not found: {ipa_path}")
        return 1
    version = _read_file_stripped("VERSION", "0.0.0")
    build_number = _read_file_stripped("BUILD_NUMBER", "0")

    if dry_run:
        print(
            f"[DRY-RUN] Would upload {ipa_path} as version {version} "
            f"(build {build_number}) via the Build Upload API."
        )
        return 0

    upload_id = managers.builds.upload_ipa(ipa_path, version=version, build_number=build_number)
    print(f"Upload started: buildUploads/{upload_id}")
    return 0


def _cmd_status(managers, dry_run, args):
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


def _cmd_testflight(managers, dry_run, args):
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


def _cmd_submit(managers, dry_run, args):
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

    return handler(managers, dry_run, command_args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
