# Agent-native publishing

ANDP is built so an AI agent can drive App Store Connect publishing end to end
— safely. Three primitives make that possible; no other release tool has them
together.

## 1. Act only when provable: `verify`

An agent should never start a 30-minute build on credentials that cannot
publish. `verify` is the agent's *can-I-act* primitive:

```bash
andp verify me.your.app --json
```

```json
{"command": "verify", "ok": true,
 "checks": [
   {"name": "credentials", "ok": true, "detail": "..."},
   {"name": "jwt",         "ok": true, "detail": "JWT signed (ES256)"},
   {"name": "api_auth",    "ok": true, "detail": "API authentication accepted"},
   {"name": "app_record",  "ok": true, "detail": "app found: ..."}],
 "app": {"id": "6786703445", "name": "Rekonect", "bundle_id": "ceo.services.rekonect"}}
```

On failure, `ok` is false, the failing check names the exact blocker (e.g.
`"missing": ["issuer_id"]`), and the exit code is 1. The agent knows *what to
fix* without parsing prose.

## 2. One-shot distribution: `release`

The full path from a signed IPA to TestFlight distribution, as one idempotent
command with structured stages:

```bash
andp release build/App.ipa --group "Beta" --json
```

```json
{"command": "release", "ok": true,
 "stages": [
   {"name": "app_record",       "ok": true, "detail": "Rekonect (...) — id 6786703445"},
   {"name": "upload",           "ok": true, "detail": "buildUploads/... (1.0 build 1)"},
   {"name": "processing",       "ok": true, "detail": "build ... is VALID"},
   {"name": "testflight_group", "ok": true, "detail": "build linked to group 'Beta'"}],
 "build": {"id": "...", "processing_state": "VALID"}}
```

Bundle id, version and build number come from the IPA's own Info.plist — the
agent cannot ship mismatched metadata. A failed stage stops the chain and
reports exactly where.

## 3. MCP server: publishing as native agent tools

```bash
python3 -m andp.mcp
```

Claude Code / any MCP client configuration:

```json
{
  "mcpServers": {
    "andp": {
      "command": "python3",
      "args": ["-m", "andp.mcp"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

Exposed tools: `verify`, `upload`, `release`, `status`, `testflight_add`,
`submit`. Results are the same structured JSON envelopes as the CLI.

### Guardrails (policy)

Agents must not be able to ship to App Review by accident. `submit` is
**refused by default**; enable it explicitly per project in `andp.yml`:

```yaml
policy:
  allow_submit: true   # default: false
```

### Audit trail

Set `ANDP_AUDIT_LOG=/path/audit.jsonl` and every API **mutation**
(POST/PATCH/DELETE) is appended as one JSON line (`ts`, `method`, `path`,
`status`). Reads are not logged. When an agent publishes, you can always
answer "what exactly did it do?".

## The full loop an agent can run today

1. `verify <bundle-id>` — act only if `ok`
2. build + sign (xcodebuild, or your own pipeline)
3. `release <ipa> --group Beta` — upload, wait for `VALID`, distribute
4. `testflight_add` — manage testers
5. `submit` — only if the human enabled `allow_submit`

Every step: machine-readable output, honest failure, audit trail.
