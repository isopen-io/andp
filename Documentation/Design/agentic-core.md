# Design: the ANDP agentic core

Status: reviewed (see Review log below) · Target release: 1.8.0 · Date: 2026-07-21

## Why (and why now)

The current "agent-native" layer is adapters over a CLI: `--json` render flags,
an MCP server that captures its own CLI's stdout, a boolean policy. Meanwhile
the competition ships MCP wrappers over the raw API (asc-mcp: ~200 1:1 tools)
or over fastlane (fastlane-mcp). Every one of them shares the same flaws for
agents:

- **No resumability** — a crash mid-release loses all progress; retry re-runs
  everything against a non-idempotent external system.
- **Blocking long operations** — waiting for Apple processing inside one tool
  call breaks agent timeouts.
- **Huge, unguarded tool surfaces** — 200 tools with no risk model is how an
  agent accidentally ships to App Review.
- **Prose errors** — the agent cannot decide retry vs escalate.

The differentiator is not more tools; it is **releases as stateful,
resumable, policy-gated resources**. Nobody in the space has that.

## Architecture

```
andp/
  core/                    <- the product: a typed library. No printing, no sys.exit.
    errors.py              AndpError: code, retryable, remediation
    state.py               StateStore: atomic JSON persistence + locking (.andp/state/)
    release.py             ReleaseMachine: idempotent steps, one non-blocking step() at a time
  asc/                     <- unchanged API layer (auth/client/managers)
  cli.py / asc/asc_manager.py  <- adapter: parses argv, renders core results
  mcp.py                   <- adapter: serializes core results, annotated tools
```

Rule: **core never prints and never exits.** It returns dataclasses and raises
`AndpError`. CLI renders text or JSON; MCP serializes. (The legacy commands
keep their handlers until migrated; `release` migrates now.)

## 1. Error taxonomy (`core/errors.py`)

```python
@dataclass
class AndpError(Exception):
    code: str            # stable, machine-readable: "auth_rejected", "app_not_found", ...
    message: str         # human-readable detail
    retryable: bool      # can the agent retry the same call as-is?
    remediation: str     # what to change before retrying (for humans AND agents)
```

Mapping from the transport layer (`from_asc_error`):

| Condition | code | retryable | remediation |
|---|---|---|---|
| 401 | `auth_rejected` | no | check key_id/issuer_id/role |
| 403 | `permission_denied` | no | key lacks the required ASC role/permission |
| 404 | `not_found` | no | resource id/filters |
| 409 | `conflict` | no | payload contract (relationship/attribute named in detail) |
| 429 | `rate_limited` | **yes** | wait Retry-After (client already retries 3x) |
| 5xx | `asc_unavailable` | **yes** | transient Apple-side error |
| network exception | `network_error` | **yes** | connectivity |
| build FAILED/INVALID | `processing_failed` | no | inspect build in ASC UI |

Edge cases covered by tests: unknown status codes (fallback `api_error`,
retryable=False), empty error arrays, non-JSON bodies (already normalized by
client `_parse`).

## 2. Persistent state (`core/state.py`)

- Location: `.andp/state/<release-id>.json` under the project root (gitignored).
- **Atomic writes**: write to `<file>.tmp` then `os.replace` — a crash cannot
  half-write state.
- **Locking**: `<file>.lock` created with `O_CREAT|O_EXCL` containing the pid;
  stale locks (dead pid) are broken. Two concurrent `poll`s on the same
  release: second one fails fast with `state_locked` (retryable=True).
- Corrupted state file (invalid JSON): surfaced as `state_corrupted` with
  remediation, never silently reset.

## 3. The release machine (`core/release.py`)

**Identity & idempotency**: `release_id = <bundle_id>-<version>-<build>`
(slugified). Starting a release for the same IPA triple returns the existing
machine (resume semantics by default). The IPA's sha256 is recorded; if the
file changed for the same triple, `step()` refuses with `ipa_changed`.

**States** (stored, linear):

```
created -> app_resolved -> uploaded -> processing -> valid
        [-> group_linked]                       (TestFlight path, --group)
        [-> version_ensured -> build_attached -> compliance_set -> submitted]
                                                (App Store path, --ship)
terminal: done | failed(error)
```

**`step()` advances exactly one state and persists before returning.** The
`processing` state is special: each step performs ONE poll (`GET /v1/builds`);
if still PROCESSING it stays in `processing` and reports
`{"retry_after": 60}` — the agent (or the blocking CLI wrapper) decides when
to call again. No sleep inside the machine.

**Per-step idempotency against the external world** (crash-safety):
- `uploaded`: before reserving, query `GET /v1/builds` for
  `filter[version]=build_number` — if Apple already has the build (crash after
  upload, before persist), skip the upload and advance.
- `version_ensured`/`build_attached`/`compliance_set`: the underlying manager
  calls are already ensure-style or idempotent PATCHes.
- `submitted`: **never blind-retried** — before submitting, check for an
  existing open reviewSubmission for the app; if present, adopt it.

**Fixes a live bug**: the current `submit` CLI creates a version and submits
**without attaching a build** — Apple rejects that. The App Store path orders
`build_attached` strictly before `submitted`.

## 4. Plan / approve / apply (policy that scales beyond a boolean)

- `--ship` releases compute a **plan** at start: the ordered list of stages
  with their consequences, persisted in the state file.
- The `submitted` stage is **gated**: it executes only if
  `policy.allow_submit: true` (andp.yml) **or** the plan carries an approval
  (`andp release approve <id>` — a human action, recorded with timestamp).
- MCP intentionally does **not** expose an approve tool: approval happens
  out-of-band by the human. The agent can prepare everything, ask, and resume
  after approval — that is the collaboration model Claude Code/Cursor need.

## 5. Adapters

**CLI** (backward compatible):
- `andp release <ipa> [--group G] [--ship]` — blocking convenience: loops
  `step()` (sleeping between processing polls), same JSON envelope as today.
- `andp release start|poll|status|list|approve` — the agent surface:
  - `start <ipa> [--group G] [--ship]` -> `{release_id, state, plan}`
  - `poll <id>` -> advance one step -> full state (incl. `retry_after` hint)
  - `status <id>` -> read-only state; `list` -> all releases
  - `approve <id>` -> record human approval for the gated stages

**MCP v2** — tools call the core library directly (no stdout capture), return
the same JSON in `content[0].text` **and** `structuredContent`. Tool
annotations per the 2025-03-26 spec (conservative defaults made explicit):

| tool | readOnly | destructive | idempotent | openWorld |
|---|---|---|---|---|
| verify | true | false | true | true |
| release_start | false | false | **true** (same triple resumes) | true |
| release_poll | false | false | true (safe to re-call) | true |
| release_status / release_list | true | false | true | false |
| upload | false | false | true (skips existing build) | true |
| testflight_add | false | false | true | true |
| submit | false | **true** | false | true |

`submit` stays gated by policy; `release_poll` respects the gate through the
machine itself (single enforcement point — adapters cannot bypass it).

## Competitive positioning (research, 2026-07-21)

- asc-mcp (~200 tools, 1:1 API), fastlane-mcp (CLI wrapper),
  appstore-release-mcp: none are resumable, none have preflight, plan/apply,
  typed retryability or audit. Their surface breadth is a liability for agents.
- MCP annotations shipped in spec 2025-03-26; hosts treat unannotated tools as
  destructive+open-world. Annotating honestly is both a UX and a trust win.
- ANDP's wedge: *the only App Store publishing layer an agent can drive
  safely: provable preflight, resumable stateful releases, out-of-band human
  approval, full audit.*

## Review log

- 2026-07-21 — design reviewed by independent agent before implementation;
  adjustments recorded here:
  - (pending review)

## Test plan (TDD, edge cases first-class)

- errors: every mapping row + unknown status + non-JSON body.
- state: atomic write survives simulated crash (tmp exists, main intact);
  lock contention; stale lock takeover; corrupted JSON surfaced.
- machine: full happy paths (TestFlight, App Store, both); resume at every
  state; crash-after-upload idempotency (build already on ASC); ipa sha
  mismatch; processing FAILED/INVALID/timeout; double start returns same id;
  approve gate (blocked, then approved, then proceeds); missing IPA at resume
  (only needed before upload — later stages must not require the file).
- adapters: CLI envelopes unchanged for the blocking path; start/poll JSON;
  MCP annotations present; submit gate through machine.
