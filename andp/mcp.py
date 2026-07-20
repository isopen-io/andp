"""ANDP MCP server — publish to App Store Connect as agent-native tools.

Speaks Model Context Protocol (JSON-RPC 2.0, line-delimited over stdio):
    python3 -m andp.mcp

Tools map to the CLI commands in --json mode; results are structured JSON an
agent can reason about. Guardrail: `submit` (App Review) is refused unless the
project's andp.yml explicitly sets `policy.allow_submit: true` — an agent must
never be able to ship to review by accident.
"""
import contextlib
import io
import json
import os
import sys

import yaml

from .asc.asc_manager import main as cli_main

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "verify",
        "description": (
            "Honest App Store Connect publish preflight: credentials -> ES256 JWT -> "
            "live API auth -> app record lookup. Fails with the exact blocking reason. "
            "Call this before any build or upload."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string", "description": "Also verify the app record exists"},
            },
        },
    },
    {
        "name": "upload",
        "description": (
            "Upload a signed .ipa via Apple's Build Upload API. Bundle id, version and "
            "build number are read from the IPA's own Info.plist."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"ipa_path": {"type": "string"}},
            "required": ["ipa_path"],
        },
    },
    {
        "name": "release",
        "description": (
            "One-shot release: verify app record -> upload -> wait for Apple processing "
            "-> optionally link the build to a TestFlight group. The full path from IPA "
            "to distribution."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ipa_path": {"type": "string"},
                "group": {"type": "string", "description": "TestFlight group to link the build to"},
            },
            "required": ["ipa_path"],
        },
    },
    {
        "name": "status",
        "description": "Poll the processing state of an uploaded build.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string"},
                "build_number": {"type": "string"},
            },
            "required": ["bundle_id", "build_number"],
        },
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
    },
    {
        "name": "submit",
        "description": (
            "Submit a version for App Review. GATED: requires policy.allow_submit: true "
            "in the project's andp.yml."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string"},
                "version": {"type": "string"},
            },
            "required": ["bundle_id", "version"],
        },
    },
]

_JSON_TOOLS = {"verify", "upload", "release"}


def load_policy(path="andp.yml"):
    """Project-level guardrails for agent-driven publishing."""
    policy = {"allow_submit": False}
    if os.path.exists(path):
        with open(path, "r") as f:
            loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
            data = yaml.load(f, Loader=loader) or {}
        policy.update((data.get("policy") or {}))
    return policy


def _tool_argv(name, arguments):
    if name == "verify":
        argv = ["verify"]
        if arguments.get("bundle_id"):
            argv.append(arguments["bundle_id"])
    elif name == "upload":
        argv = ["upload", arguments["ipa_path"]]
    elif name == "release":
        argv = ["release", arguments["ipa_path"]]
        if arguments.get("group"):
            argv += ["--group", arguments["group"]]
    elif name == "status":
        argv = ["status", arguments["bundle_id"], str(arguments["build_number"])]
    elif name == "testflight_add":
        argv = ["testflight", arguments["bundle_id"], arguments["group"], "add"]
        argv += list(arguments.get("emails") or [])
    elif name == "submit":
        argv = ["submit", arguments["bundle_id"], arguments["version"]]
    else:
        return None
    if name in _JSON_TOOLS:
        argv.append("--json")
    return argv


def _call_tool(name, arguments):
    if name == "submit" and not load_policy().get("allow_submit"):
        return {
            "content": [{
                "type": "text",
                "text": (
                    "Refused by policy: App Review submission is disabled for agents. "
                    "Set `policy.allow_submit: true` in andp.yml to enable it."
                ),
            }],
            "isError": True,
        }

    argv = _tool_argv(name, arguments or {})
    if argv is None:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli_main(argv)
    text = buffer.getvalue().strip() or "(no output)"
    result = {"content": [{"type": "text", "text": text}]}
    if code != 0:
        result["isError"] = True
    return result


def handle_message(message):
    """Pure JSON-RPC dispatcher; returns the response dict, or None for notifications."""
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
    """Line-delimited JSON-RPC over stdio."""
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
