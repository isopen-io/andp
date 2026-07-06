"""App Store metadata synchronisation.

MetadataSyncer pushes a metadata.json file (bundle_id, version, per-locale
attributes) to App Store Connect through AppsManager/AppStoreManager.
The CLI entry point mirrors asc_manager.py: with placeholder credentials it
runs in DRY-RUN mode so CI works without an Apple account.
"""
import json
import os
import sys

from apps import AppsManager
from appstore import AppStoreManager
from auth import ASCAuth
from client import ASCClient
from config import ConfigError, load_account


class MetadataSyncer:
    def __init__(self, apps_manager, appstore_manager):
        self.apps = apps_manager
        self.appstore = appstore_manager

    def sync_from_file(self, metadata_path):
        """Push every locale in the file; return {locale: "created"|"updated"}."""
        if not os.path.exists(metadata_path):
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

        with open(metadata_path, "r") as f:
            data = json.load(f)

        bundle_id = data["bundle_id"]
        version = data["version"]
        localizations = data.get("localizations", {})

        app = self.apps.find_app(bundle_id)
        if app is None:
            raise LookupError(f"App {bundle_id} not found in App Store Connect")

        app_store_version = self.appstore.ensure_version(app["id"], version)

        results = {}
        for locale, attributes in localizations.items():
            _, created = self.appstore.upsert_version_localization(
                app_store_version["id"], locale, attributes
            )
            results[locale] = "created" if created else "updated"
        return results


def main(argv):
    if not argv:
        print("Usage: metadata_manager.py <sync> <metadata_json_path> [--account <account_id>]")
        return 2

    args = list(argv)
    account_id = "primary"
    if "--account" in args:
        idx = args.index("--account")
        account_id = args[idx + 1]
        del args[idx:idx + 2]

    command, command_args = args[0], args[1:]

    try:
        account = load_account(account_id)
    except ConfigError as exc:
        print(f"Error: {exc}")
        return 1

    if command == "sync":
        if not command_args:
            print("Usage: sync <metadata_json_path>")
            return 2
        metadata_path = command_args[0]
        if not account.is_configured():
            print(
                f"[DRY-RUN] No real credentials for account '{account_id}' — "
                f"would sync metadata from {metadata_path}."
            )
            return 0
        auth = ASCAuth(account.key_id, account.issuer_id, account.key_content)
        client = ASCClient(auth)
        syncer = MetadataSyncer(AppsManager(client), AppStoreManager(client))
        results = syncer.sync_from_file(metadata_path)
        for locale, outcome in results.items():
            print(f"{locale}: {outcome}")
        return 0

    print(f"Unknown command: {command}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
