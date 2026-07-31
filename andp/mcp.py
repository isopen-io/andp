"""ANDP MCP server — publish to App Store Connect as agent-native tools.

Speaks Model Context Protocol (JSON-RPC 2.0, line-delimited over stdio):
    python3 -m andp.mcp

Two families of tools:
- stateful release tools (`release_start`/`release_poll`/`release_status`/
  `release_list`) drive the resumable release machine through the **service
  layer directly** — library-first, never scraping CLI stdout. Results carry
  `structuredContent` (MCP 2025-03-26).
- one-shot tools (`verify`/`upload`/`status`/`testflight_add`/`submit`) map to
  the CLI in --json mode.

Every tool is annotated (readOnly/destructive/idempotent/openWorld) so hosts
like Claude Code and Cursor can reason about risk. `submit` is refused unless
`policy.allow_submit: true` in the project's andp.yml.
"""
import contextlib
import io
import json
import sys

from . import service
from .asc.asc_manager import main as cli_main

PROTOCOL_VERSION = "2025-03-26"


def _ann(read_only=False, destructive=False, idempotent=False, open_world=True):
    return {
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": open_world,
    }


TOOLS = [
    {
        "name": "verify",
        "description": (
            "Honest App Store Connect publish preflight: credentials -> ES256 JWT -> "
            "live API auth -> app record lookup. Call before any build or upload."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"bundle_id": {"type": "string"}},
        },
        "annotations": {"title": "Verify publish preflight",
                        **_ann(read_only=True, idempotent=True)},
    },
    {
        "name": "release_start",
        "description": (
            "Begin a resumable release for a signed .ipa. Returns a release_id; "
            "then call release_poll repeatedly until it is terminal. Starting the "
            "same IPA again resumes the existing release."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ipa_path": {"type": "string"},
                "group": {"type": "string", "description": "TestFlight group to link the build to"},
                "ship": {"type": "boolean",
                         "description": "Also run the App Store path (version -> attach -> "
                                        "compliance -> submit); the submit stage is gated by "
                                        "andp.yml policy or an out-of-band `release approve`."},
                "metadata_dir": {"type": "string",
                                 "description": "With ship: a folder tree of release notes + "
                                                "screenshots + previews to push before submission."},
                "account": {"type": "string"},
            },
            "required": ["ipa_path"],
        },
        "annotations": {"title": "Start release", **_ann(idempotent=True)},
    },
    {
        "name": "release_poll",
        "description": (
            "Advance a release by one step and return its state. Non-blocking: if "
            "the build is still processing it returns state=processing with "
            "retry_after; call again after that many seconds. Each call may perform "
            "one external effect, so it is NOT idempotent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"release_id": {"type": "string"}, "account": {"type": "string"}},
            "required": ["release_id"],
        },
        "annotations": {"title": "Advance release", **_ann(idempotent=False)},
    },
    {
        "name": "release_status",
        "description": "Read a release's current state without advancing it.",
        "inputSchema": {
            "type": "object",
            "properties": {"release_id": {"type": "string"}},
            "required": ["release_id"],
        },
        "annotations": {"title": "Release status",
                        **_ann(read_only=True, idempotent=True, open_world=False)},
    },
    {
        "name": "release_list",
        "description": "List all releases and their states.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"title": "List releases",
                        **_ann(read_only=True, idempotent=True, open_world=False)},
    },
    {
        "name": "precheck",
        "description": (
            "Read-only pre-submission validation: catches what Apple rejects "
            "(non-editable version, no build, empty description, no screenshots) "
            "before submitting. Returns a report; never mutates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"bundle_id": {"type": "string"}, "version": {"type": "string"}},
            "required": ["bundle_id", "version"],
        },
        "annotations": {"title": "Precheck for submission",
                        **_ann(read_only=True, idempotent=True)},
    },
    {
        "name": "upload",
        "description": "Upload a signed .ipa via Apple's Build Upload API (no processing wait).",
        "inputSchema": {
            "type": "object",
            "properties": {"ipa_path": {"type": "string"}},
            "required": ["ipa_path"],
        },
        "annotations": {"title": "Upload build", **_ann(idempotent=False)},
    },
    {
        "name": "status",
        "description": "Poll the processing state of an uploaded build.",
        "inputSchema": {
            "type": "object",
            "properties": {"bundle_id": {"type": "string"}, "build_number": {"type": "string"}},
            "required": ["bundle_id", "build_number"],
        },
        "annotations": {"title": "Build status", **_ann(read_only=True, idempotent=True)},
    },
    {
        "name": "testflight_add",
        "description": "Ensure a TestFlight group exists and add testers to it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string"},
                "group": {"type": "string"},
                "emails": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["bundle_id", "group"],
        },
        "annotations": {"title": "Add TestFlight testers", **_ann(idempotent=True)},
    },
    {
        "name": "submit",
        "description": (
            "Submit a version for App Review. GATED: requires policy.allow_submit: "
            "true in the project's andp.yml."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"bundle_id": {"type": "string"}, "version": {"type": "string"}},
            "required": ["bundle_id", "version"],
        },
        "annotations": {"title": "Submit for App Review", **_ann(destructive=True, idempotent=False)},
    },
    {
        "name": "unlock",
        "description": (
            "Withdraw a version's pending review submission so it becomes "
            "editable again (screenshots, metadata, build), then resubmit with "
            "`submit`. Apple locks every WAITING_FOR_REVIEW/IN_REVIEW version: "
            "asset writes answer 409 STATE_ERROR until the submission is "
            "cancelled. Submissions older than one hour are refused here "
            "(stale_submission_unconfirmed) unless the project grants standing "
            "consent with `policy.allow_stale_unlock: true` in andp.yml — "
            "forfeiting a queue position is a human decision; without the "
            "policy, surface the refusal and a human runs `andp unlock --yes`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string"},
                "version": {"type": "string"},
                "account": {"type": "string"},
            },
            "required": ["bundle_id", "version"],
        },
        "annotations": {"title": "Unlock version for editing",
                        **_ann(destructive=True, idempotent=True)},
    },
    {
        "name": "store_configure_pricing",
        "description": (
            "Set the app's price (modern appPriceSchedules) or make it free. "
            "Reconciles to the desired price: returns changed=false when already "
            "set. REPLACES the price schedule. price='free' or an exact "
            "base-territory customerPrice (e.g. '0.99')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string"},
                "base_territory": {"type": "string", "description": "Base territory id, e.g. USA"},
                "price": {"type": "string", "description": "'free' or an exact customerPrice"},
                "price_point_id": {"type": "string", "description": "Advanced: exact appPricePoint id"},
                "account": {"type": "string"},
            },
            "required": ["bundle_id"],
        },
        "annotations": {"title": "Configure app pricing", **_ann(idempotent=True)},
    },
    {
        "name": "store_configure_availability",
        "description": (
            "Set (REPLACE) the territories the app is available in. Pass a list of "
            "territory ids or [\"all\"]. DESTRUCTIVE: shrinking the set delists the "
            "app in removed territories. Refuses an empty set. Preserves "
            "availableInNewTerritories unless you set it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string"},
                "territories": {"type": "array", "items": {"type": "string"},
                                "description": "Territory ids, or [\"all\"] for every territory"},
                "available_in_new_territories": {"type": "boolean"},
                "account": {"type": "string"},
            },
            "required": ["bundle_id", "territories"],
        },
        "annotations": {"title": "Configure territory availability",
                        **_ann(destructive=True, idempotent=True)},
    },
    {
        "name": "store_set_age_rating",
        "description": (
            "Set the app's age rating declaration (2025 model). Pass a declaration "
            "object of content descriptors (NONE|INFREQUENT_OR_MILD|FREQUENT_OR_INTENSE) "
            "and booleans. PATCHes only the fields that differ; validates field "
            "names/values first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string"},
                "declaration": {"type": "object", "description": "ageRatingDeclaration fields"},
                "account": {"type": "string"},
            },
            "required": ["bundle_id", "declaration"],
        },
        "annotations": {"title": "Set age rating", **_ann(idempotent=True)},
    },
    {
        "name": "store_apply",
        "description": (
            "Apply every configured store block (pricing/availability/age_rating) "
            "from andp.yml. Best-effort: independent idempotent blocks; a re-run "
            "heals a partially-applied state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"bundle_id": {"type": "string"}, "account": {"type": "string"}},
            "required": ["bundle_id"],
        },
        "annotations": {"title": "Apply store config", **_ann(idempotent=True)},
    },
    {
        "name": "publish",
        "description": (
            "Push localized release notes, screenshots and preview videos from a "
            "folder tree (deliver-style: <dir>/<locale>/screenshots/<DISPLAY_TYPE>/). "
            "Idempotent per file — a retry uploads only what is missing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string"},
                "version": {"type": "string"},
                "metadata_dir": {"type": "string"},
                "account": {"type": "string"},
            },
            "required": ["bundle_id", "version", "metadata_dir"],
        },
        "annotations": {"title": "Publish metadata & media", **_ann(idempotent=True)},
    },
    {
        "name": "readiness_testflight",
        "description": "Can this app be delivered to TestFlight cleanly? Read-only verdict in `ready`.",
        "inputSchema": {
            "type": "object",
            "properties": {"bundle_id": {"type": "string"}, "account": {"type": "string"}},
            "required": ["bundle_id"],
        },
        "annotations": {"title": "TestFlight readiness",
                        **_ann(read_only=True, idempotent=True)},
    },
    {
        "name": "readiness_appstore",
        "description": (
            "Can this version go to the App Store cleanly? Read-only verdict in "
            "`ready` with the exact blockers. `ready: false` is a verdict, not a "
            "tool error."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"bundle_id": {"type": "string"},
                           "version": {"type": "string"},
                           "account": {"type": "string"}},
            "required": ["bundle_id", "version"],
        },
        "annotations": {"title": "App Store readiness",
                        **_ann(read_only=True, idempotent=True)},
    },
    {
        "name": "build_number",
        "description": (
            "Next iOS build number (CFBundleVersion). Strategies: max-build "
            "(max global ASC + 1, needs credentials), timestamp, commit. "
            "Reads only; nothing is written anywhere."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "enum": ["max-build", "timestamp", "commit"]},
                "bundle_id": {"type": "string"},
                "floor": {"type": "integer"},
                "fmt": {"type": "string"},
                "sha": {"type": "string"},
                "digits": {"type": "integer"},
                "account": {"type": "string"},
            },
            "required": ["strategy"],
        },
        "annotations": {"title": "Next build number", **_ann(read_only=True)},
    },
    {
        "name": "release_reset",
        "description": (
            "Delete a release's LOCAL state file (recovery escape hatch). Does not "
            "un-upload a build or un-submit a review."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"release_id": {"type": "string"}},
            "required": ["release_id"],
        },
        "annotations": {"title": "Reset release state",
                        **_ann(destructive=True, idempotent=True, open_world=False)},
    },
    {
        "name": "config",
        "description": "Where ANDP reads its configuration — diagnostic report, read-only.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"title": "Configuration diagnostic",
                        **_ann(read_only=True, idempotent=True, open_world=False)},
    },
    {
        "name": "targets",
        "description": "List the build targets declared in andp.yml and their resolved destinations.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"title": "List build targets",
                        **_ann(read_only=True, idempotent=True, open_world=False)},
    },
    {
        "name": "build",
        "description": (
            "Compile a target declared in andp.yml (or all of them). "
            "`archive: true` produces the signed archive/IPA path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "all": {"type": "boolean"},
                "archive": {"type": "boolean"},
            },
        },
        "annotations": {"title": "Build target", **_ann(idempotent=True, open_world=False)},
    },
    {
        "name": "test",
        "description": "Run a target's test suite (or every target's with `all: true`).",
        "inputSchema": {
            "type": "object",
            "properties": {"target": {"type": "string"}, "all": {"type": "boolean"}},
        },
        "annotations": {"title": "Run tests", **_ann(idempotent=True, open_world=False)},
    },
    {
        "name": "run",
        "description": (
            "Build, install and launch a target on its simulator/device. Never "
            "streams logs (that would block the stdio server)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
        "annotations": {"title": "Run app", **_ann(open_world=False)},
    },
]

_CLI_JSON_TOOLS = {"upload"}

from .policy import load_policy  # noqa: E402  (shared allow_submit / compliance loader)


# -- library-first release tools --------------------------------------------

def _release_result(payload):
    """Wrap a service dict as an MCP tool result with structuredContent."""
    result = {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "structuredContent": payload,
    }
    if payload.get("ok") is False:
        result["isError"] = True
    return result


def _call_release_tool(name, args):
    if name == "release_start":
        return _release_result(service.release_start(
            args["ipa_path"], account=args.get("account", "primary"),
            group=args.get("group"), ship=bool(args.get("ship", False)),
            metadata_dir=args.get("metadata_dir")))
    if name == "release_poll":
        return _release_result(service.release_poll(
            args["release_id"], account=args.get("account", "primary")))
    if name == "release_status":
        return _release_result(service.release_status(args["release_id"]))
    if name == "release_list":
        return _release_result(service.release_list())
    return None


def _call_store_tool(name, args):
    acct = args.get("account", "primary")
    if name == "store_configure_pricing":
        return _release_result(service.configure_pricing(
            args["bundle_id"], account=acct, base_territory=args.get("base_territory"),
            price=args.get("price"), price_point_id=args.get("price_point_id")))
    if name == "store_configure_availability":
        return _release_result(service.configure_availability(
            args["bundle_id"], account=acct, territories=args.get("territories"),
            available_in_new_territories=args.get("available_in_new_territories")))
    if name == "store_set_age_rating":
        return _release_result(service.configure_age_rating(
            args["bundle_id"], account=acct, declaration=args.get("declaration")))
    if name == "store_apply":
        return _release_result(service.configure_store(args["bundle_id"], account=acct))
    return None


# -- CLI-backed one-shot tools ----------------------------------------------

def _cli_argv(name, args):
    if name == "verify":
        argv = ["verify"] + ([args["bundle_id"]] if args.get("bundle_id") else []) + ["--json"]
    elif name == "precheck":
        argv = ["precheck", args["bundle_id"], str(args["version"]), "--json"]
    elif name == "upload":
        argv = ["upload", args["ipa_path"], "--json"]
    elif name == "status":
        argv = ["status", args["bundle_id"], str(args["build_number"])]
    elif name == "testflight_add":
        argv = ["testflight", args["bundle_id"], args["group"], "add"] + list(args.get("emails") or [])
    elif name == "submit":
        argv = ["submit", args["bundle_id"], args["version"]]
    elif name == "config":
        argv = ["config", "--json"]
    elif name == "targets":
        argv = ["targets", "--json"]
    elif name == "build":
        argv = ["build"]
        if args.get("target"):
            argv.append(args["target"])
        if args.get("all"):
            argv.append("--all")
        if args.get("archive"):
            argv.append("--archive")
        argv.append("--json")
    elif name == "test":
        argv = ["test"]
        if args.get("target"):
            argv.append(args["target"])
        if args.get("all"):
            argv.append("--all")
        argv.append("--json")
    elif name == "run":
        # Never --logs: streaming would block the stdio server.
        argv = ["run", args["target"], "--json"]
    else:
        return None
    return argv


def _call_cli_tool(name, args):
    argv = _cli_argv(name, args or {})
    if argv is None:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli_main(argv)
    text = buffer.getvalue().strip() or "(no output)"
    result = {"content": [{"type": "text", "text": text}]}
    with contextlib.suppress(json.JSONDecodeError):
        result["structuredContent"] = json.loads(text)
    if code != 0:
        result["isError"] = True
    return result


def _call_tool(name, arguments):
    """Dispatch a tool call, guaranteeing a typed result — never an exception
    that would kill the stdio server."""
    try:
        return _dispatch_tool(name, arguments or {})
    except Exception as exc:  # last-resort boundary: one bad call must not crash the server
        return {
            "content": [{"type": "text", "text": f"Tool '{name}' failed: {exc}"}],
            "isError": True,
        }


def _dispatch_tool(name, args):
    if name == "submit" and not load_policy().get("allow_submit"):
        return {
            "content": [{"type": "text", "text": (
                "Refused by policy: App Review submission is disabled for agents. "
                "Set `policy.allow_submit: true` in andp.yml to enable it."
            )}],
            "isError": True,
        }
    if name == "unlock":
        # Library-first, and no per-call consent bypass: standing consent is
        # policy.allow_stale_unlock in andp.yml — durable and auditable, like
        # allow_submit. Without it, a stale submission comes back as the typed
        # refusal `stale_submission_unconfirmed` for a human to decide
        # (`andp unlock --yes` in a shell).
        return _release_result(service.unlock(
            args["bundle_id"], str(args["version"]),
            account=args.get("account", "primary"),
            assume_yes=bool(load_policy().get("allow_stale_unlock"))))
    if name == "publish":
        return _release_result(service.publish(
            args["bundle_id"], str(args["version"]), args["metadata_dir"],
            account=args.get("account", "primary")))
    if name == "readiness_testflight":
        return _release_result(service.readiness_testflight(
            args["bundle_id"], account=args.get("account", "primary")))
    if name == "readiness_appstore":
        return _release_result(service.readiness_appstore(
            args["bundle_id"], str(args["version"]),
            account=args.get("account", "primary")))
    if name == "build_number":
        return _release_result(service.build_number(
            args["strategy"], bundle_id=args.get("bundle_id"),
            floor=int(args.get("floor") or 0), fmt=args.get("fmt"),
            sha=args.get("sha"), digits=int(args.get("digits") or 7),
            account=args.get("account", "primary")))
    if name == "release_reset":
        return _release_result(service.release_reset_by_id(args["release_id"]))
    if name.startswith("release_"):
        result = _call_release_tool(name, args)
        if result is not None:
            return result
    if name.startswith("store_"):
        result = _call_store_tool(name, args)
        if result is not None:
            return result
    return _call_cli_tool(name, args)


def handle_message(message):
    method = message.get("method")
    msg_id = message.get("id")
    if msg_id is None:  # notification
        return None

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "andp", "version": _version()},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        result = _call_tool(params.get("name"), params.get("arguments"))
    else:
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _version():
    from . import __version__
    return __version__


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
