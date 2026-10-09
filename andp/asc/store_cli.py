"""`andp store plan` — print the listing diff for humans or as JSON."""
import json

_LONG = 70


def _show(value):
    if value is None or value == "":
        return "(empty)"
    if isinstance(value, list):
        if len(value) > 8:
            return f"[{len(value)} items]"
        return ", ".join(str(v) for v in value) or "(none)"
    text = str(value).replace("\n", " ⏎ ")
    if len(text) > _LONG:
        return f"«{text[:_LONG - 10]}…» ({len(str(value))} chars)"
    return text


def _territory_delta(change):
    current = set(change.get("current") or [])
    desired = set(change.get("desired") or [])
    added, removed = sorted(desired - current), sorted(current - desired)
    parts = []
    if added:
        parts.append(f"+{len(added)} ({', '.join(added[:6])}{'…' if len(added) > 6 else ''})")
    if removed:
        parts.append(f"-{len(removed)} ({', '.join(removed[:6])}{'…' if len(removed) > 6 else ''})")
    return " ".join(parts) or "reordered"


def print_plan(result):
    if result.get("error"):
        err = result["error"]
        print(f"❌ store plan: {err.get('message', 'failed')}")
        if err.get("remediation"):
            print(f"   → {err['remediation']}")
        return
    if result.get("dry_run"):
        print("[DRY-RUN] No App Store Connect credentials — the configuration was "
              "validated offline, the live state was not read.")
        for family, count in result.get("desired", {}).items():
            print(f"  {family}: {count}")
    else:
        version = result.get("version")
        where = (f"version {version['version']} ({version['state']})" if version
                 else "no version")
        print(f"Plan for {result.get('bundle_id')} — {where}")
        current = None
        for change in result.get("changes", []):
            header = f"{change['family']} [{change['scope']}]"
            if header != current:
                print(f"  {header}")
                current = header
            mark = {"create": "+", "delete": "-", "upload": "↑"}.get(change["action"], "~")
            lock = "  🔒 locked" if change.get("locked") else ""
            if change["field"] == "territories" and change["family"] == "availability":
                detail = _territory_delta(change)
            else:
                detail = f"{_show(change['current'])} → {_show(change['desired'])}"
            print(f"    {mark} {change['field']}: {detail}{lock}")
        for key, value in (result.get("read_only") or {}).items():
            print(f"  ℹ️  {key} (read-only): {value}")
        print(f"{len(result.get('changes', []))} change(s), "
              f"{result.get('unchanged', 0)} unchanged — nothing was written.")
    for note in result.get("notes", []):
        print(f"  ℹ️  {note}")
    for warning in result.get("warnings", []):
        print(f"  ⚠️  {warning}")
    for error in result.get("errors", []):
        print(f"  ❌ {error}")


def cmd_store_plan(account_id, args, json_mode, take_opt):
    from .. import listing_service
    version = take_opt(args, "--version")
    metadata_dir = take_opt(args, "--metadata")
    if not args:
        print("Usage: store plan <bundle_id> [--version V] [--metadata DIR]")
        return 2
    result = listing_service.store_plan(args[0], account=account_id, version=version,
                                        metadata_dir=metadata_dir)
    if json_mode:
        print(json.dumps(result))
    else:
        print_plan(result)
    return 0 if result.get("ok") else 1
