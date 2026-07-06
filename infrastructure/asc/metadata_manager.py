import os
import sys
import json
import yaml

class MetadataManager:
    def __init__(self, key_id, issuer_id, key_content):
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.key_content = key_content
        self.base_url = "https://api.appstoreconnect.apple.com/v1"

    def fetch_localized_metadata(self, app_id, version):
        """Fetches metadata for a specific app version and locale."""
        print(f"Fetching metadata for app {app_id}, version {version}...")
        # Mocked API call
        return {
            "en-US": {
                "name": "Meeshy",
                "description": "Next-gen Apple platform automation.",
                "keywords": "apple, build, automation, delivery",
                "whats_new": "Iteration 7 improvements."
            }
        }

    def update_localized_metadata(self, app_id, version, locale, metadata):
        """Updates localized metadata for an app version."""
        print(f"Updating {locale} metadata for app {app_id}, version {version}...")
        for key, value in metadata.items():
            print(f"  Setting {key} to: {value}")
        print("Update successful (Mocked).")
        return True

    def sync_metadata_from_file(self, metadata_path):
        """Syncs metadata from a JSON file to App Store Connect."""
        if not os.path.exists(metadata_path):
            print(f"Error: Metadata file {metadata_path} not found.")
            return False

        with open(metadata_path, 'r') as f:
            data = json.load(f)

        app_id = data.get("app_id")
        version = data.get("version")
        localizations = data.get("localizations", {})

        for locale, meta in localizations.items():
            self.update_localized_metadata(app_id, version, locale, meta)

        return True

def load_secrets(account_id):
    secrets_file = "secrets.yml"
    if not os.path.exists(secrets_file):
        secrets_file = "secrets.example.yml"

    with open(secrets_file, 'r') as f:
        data = yaml.safe_load(f)

    accounts = data.get('accounts', {})
    if account_id not in accounts:
        print(f"Error: Account '{account_id}' not found in secrets.")
        sys.exit(1)

    return accounts[account_id]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: metadata_manager.py <command> [args] [--account <account_id>]")
        sys.exit(1)

    cmd = sys.argv[1]
    account_id = "primary"
    args = sys.argv[2:]

    if "--account" in args:
        idx = args.index("--account")
        account_id = args[idx+1]
        args.pop(idx+1)
        args.pop(idx)

    account_data = load_secrets(account_id)
    asc_api = account_data.get('asc_api', {})

    mgr = MetadataManager(
        asc_api.get('key_id'),
        asc_api.get('issuer_id'),
        asc_api.get('key_content')
    )

    if cmd == "fetch":
        if len(args) < 2:
            print("Usage: fetch <app_id> <version>")
            sys.exit(1)
        metadata = mgr.fetch_localized_metadata(args[0], args[1])
        print(json.dumps(metadata, indent=2))
    elif cmd == "sync":
        if not args:
            print("Usage: sync <metadata_json_path>")
            sys.exit(1)
        mgr.sync_metadata_from_file(args[0])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
