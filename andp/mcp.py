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
import os
import sys

import yaml

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
]

_CLI_JSON_TOOLS = {"upload"}


def load_policy(path="andp.yml"):
    policy = {"allow_submit": False}
    if os.path.exists(path):
        with open(path, "r") as f:
            loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
            data = yaml.load(f, Loader=loader) or {}
        policy.update((data.get("policy") or {}))
    return policy


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
            group=args.get("group")))
    if name == "release_poll":
        return _release_result(service.release_poll(
            args["release_id"], account=args.get("account", "primary")))
    if name == "release_status":
        return _release_result(service.release_status(args["release_id"]))
    if name == "release_list":
        return _release_result(service.release_list())
    return None


# -- CLI-backed one-shot tools ----------------------------------------------

def _cli_argv(name, args):
    if name == "verify":
        argv = ["verify"] + ([args["bundle_id"]] if args.get("bundle_id") else []) + ["--json"]
    elif name == "upload":
        argv = ["upload", args["ipa_path"], "--json"]
    elif name == "status":
        argv = ["status", args["bundle_id"], str(args["build_number"])]
    elif name == "testflight_add":
        argv = ["testflight", args["bundle_id"], args["group"], "add"] + list(args.get("emails") or [])
    elif name == "submit":
        argv = ["submit", args["bundle_id"], args["version"]]
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
    args = arguments or {}
    if name == "submit" and not load_policy().get("allow_submit"):
        return {
            "content": [{"type": "text", "text": (
                "Refused by policy: App Review submission is disabled for agents. "
                "Set `policy.allow_submit: true` in andp.yml to enable it."
            )}],
            "isError": True,
        }
    if name.startswith("release_"):
        result = _call_release_tool(name, args)
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
