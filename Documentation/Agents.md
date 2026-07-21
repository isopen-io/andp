# Agent-native publishing

ANDP is built so an AI agent can drive App Store Connect publishing end to end
— safely. Three primitives make that possible; no other release tool has them
together.

> **Looking for the full operational playbook** (every state, the complete
> CLI/MCP/service surface, error taxonomy, and a repo→submitted worked example)?
> See **[AgentGuide.md](AgentGuide.md)**. This page explains *why* the design is
> agent-native; AgentGuide is the *how*.

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

## 2. Resumable, non-blocking distribution: `release start` / `release poll`

Waiting for Apple to finish processing a build can take many minutes — far
longer than an agent tool call should block, and a crash mid-wait must not lose
progress or re-upload. So a release is a **stateful, resumable resource** the
agent advances one step at a time:

```bash
andp release start build/App.ipa --group "Beta" --json
# {"command":"release_start","ok":true,"release_id":"primary-me-app-1-0-7","state":"created","next":"poll"}

andp release poll primary-me-app-1-0-7 --json
# {"state":"app_resolved","terminal":false, ...}
andp release poll primary-me-app-1-0-7 --json
# {"state":"processing","terminal":false,"retry_after":60, ...}   <- come back in 60s
# ... (agent sleeps 60s, or does other work, then polls again)
andp release poll primary-me-app-1-0-7 --json
# {"state":"done","terminal":true,"ok":true,"build":{"id":"...","processing_state":"VALID"}}
```

Each `poll` performs **at most one external effect** and persists the new state
to `.andp/state/<release_id>.json` before returning. Properties an agent can
rely on:

- **Resumable:** crash or restart anywhere — `poll` continues from the last
  persisted state. It never re-uploads (write-ahead intent + pinned build id),
  so a reused build number never resolves the wrong binary.
- **Non-blocking:** `processing` returns `retry_after` instead of blocking;
  the agent decides when to poll again (and can work on other things meanwhile).
- **Honest failure:** a *retryable* condition (rate limit, transient 5xx, build
  still ingesting) is reported with `retryable: true` and the state is
  unchanged — poll again. A *terminal* failure sets `state: "failed"` with a
  typed `error` (`code`, `retryable`, `remediation`).
- **Inspectable:** `andp release status <id>` reads the state without advancing;
  `andp release list` shows every release.

For a simple human/CI one-shot **TestFlight** delivery, the blocking form still
exists (it does **not** support `--ship` — the App Store path is resumable and
gated, so use `release start --ship`):

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

Exposed tools: `verify`, `release_start`, `release_poll`, `release_status`,
`release_list`, `upload`, `status`, `testflight_add`, `submit`. The `release_*`
tools drive the release machine **through the library directly** (not by
scraping a CLI's stdout), and every result carries `structuredContent`.

### Tool annotations (MCP 2025-03-26)

Every tool is annotated so the host can reason about risk before calling:

| tool | readOnly | destructive | idempotent |
|---|---|---|---|
| `verify`, `status`, `release_status`, `release_list` | ✅ | — | ✅ |
| `release_start` | — | — | ✅ (same IPA resumes) |
| `release_poll` | — | — | ❌ (advances the machine) |
| `upload` | — | — | ❌ |
| `testflight_add` | — | — | ✅ |
| `submit` | — | ✅ | ❌ |

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

## Ship all the way to App Store review: `release start --ship`

`--ship` extends the same resumable machine past TestFlight to an App Store
review submission:

```
processing → valid → [testflight_group] → version → build_attached
           → compliance → awaiting_approval → submitted → done
```

The submit is **gated**. `release poll` stops at `awaiting_approval` with
`needs_approval: true` and **never crosses the gate**. It opens only when:
- `policy.allow_submit: true` in `andp.yml` (a repo pre-authorises CI to submit), **or**
- a human runs `release approve <release_id>` (recorded with a timestamp).

```bash
andp release start build/App.ipa --ship --group Beta --json   # -> release_id
andp release poll <id> --json   # ... advances; stops at awaiting_approval
# {"state":"awaiting_approval","needs_approval":true, ...}
andp release approve <id>       # human opens the gate (out of band)
andp release poll <id> --json   # ... -> submitted -> done
```

Guardrails on the App Store path: a non-editable version (already published /
in review) fails `version_not_editable`; export compliance must be declared in
`andp.yml` or the IPA's Info.plist (`compliance_undeclared` otherwise); a crash
mid-submit is recovered idempotently, and an unrelated open submission escalates
`review_submission_conflict` rather than submitting the wrong thing. Required
App Store metadata (screenshots, description, age rating) is **not** prechecked
— Apple validates it synchronously and its 409 detail is surfaced in the error.

## The full loop an agent can run today

1. `verify <bundle-id>` — act only if `ok`
2. build + sign (xcodebuild, or your own pipeline)
3. `release start <ipa> --group Beta [--ship]` → `release_id`
4. `release poll <id>` in a loop — resumable, non-blocking, until `terminal`
5. `release approve <id>` — human opens the submit gate (only with `--ship`)
6. `testflight_add` — manage testers

Every step: machine-readable output, typed/honest failure, resumable state,
audit trail.

## Threat model of the approval gate (be honest)

The `submit` gate (`policy.allow_submit`) and the MCP server's refusal to
expose `submit` without it are real barriers for an **MCP-only** agent. But an
agent with a shell (Claude Code, Cursor, Codex) can run `andp submit` directly
or edit `andp.yml` itself — so the *effective* enforcement is the host's
permission prompt on the Bash command, not ANDP. ANDP's job is to make the
destructive action **explicit, annotated, gated and audited** so the host and
the human can see it coming; it does not pretend to sandbox a shell-wielding
agent.
