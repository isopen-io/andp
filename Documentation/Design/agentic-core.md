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

**States** (stored, linear) — **v1 (TestFlight path):**

```
created -> app_resolved -> uploading -> uploaded -> processing -> valid
        [-> group_linked]                                    (--group)
        -> done
terminal: done | failed(error)
```

`uploading` persists the `buildUploads` reservation id write-ahead (adjustment
1). The App Store path (`version_ensured → build_attached → compliance_set →
submitted`) and plan/approve are **v1.1** — see the review log.

**Local error codes** (beyond the transport taxonomy in §1): `state_locked`
(retryable), `state_corrupted`, `ipa_changed`, `upload_incomplete` (resume hit
an inconclusive reservation — refuse to re-upload), and in v1.1
`approval_required`, `plan_changed`.

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

### 2026-07-21 — independent architectural review (verdict: GO with adjustments)

The design was reviewed against the real code before implementation. The
review caught two factual errors and led to a disciplined scope cut. Decisions
taken, all folded into the spec above:

**Corrected (were wrong / unsafe as written):**

1. **Upload idempotency by "absence in `GET /v1/builds`" is false and unsafe.**
   The repo's own `wait_for_processing` loops precisely because a committed
   build does *not* appear immediately in `/v1/builds` (Apple ingestion window
   of minutes). So "empty list ⇒ not uploaded ⇒ re-upload" would double-upload
   inside that window; the duplicate (same `cfBundleVersion`) ends INVALID and,
   because polling uses `sort=-uploadedDate&limit=1`, the machine could lock
   onto the INVALID duplicate. **Decision:** write-ahead persistence — persist
   the `buildUploads` reservation id *before* the file transfer (new
   `uploading` state); on resume, an inconclusive result is treated as
   inconclusive: the machine **refuses to re-upload** and surfaces
   `upload_incomplete` (actionable) rather than guessing.

2. **Skip-by-`filter[version]` can match the wrong build.** `filter[version]`
   is `CFBundleVersion` only; a build number reused across marketing versions
   (1.2 build 7 vs 1.3 build 7) matches an older VALID build. **Decision:**
   once a build is resolved, **pin its id in the state file**; never
   re-resolve by filter. The `processing` step resolves + pins `build_id`, and
   every later step uses the pinned id.

3. **MCP annotation honesty.** `release_poll` is **not** idempotent — each call
   advances the machine with a new external effect ⇒ `idempotentHint: false`.
   To keep the destructive-action boundary honest, `release_poll` **never
   crosses a gate**: on hitting an approval gate it stops in
   `awaiting_approval` and returns; crossing the gate is a separate explicit
   action. `upload`'s idempotent hint is only claimed after adjustment 1.
   Protocol version bumps to `2025-03-26` (annotations + `structuredContent`).

**Specified (were missing):**

4. **Failure semantics.** A *retryable* `AndpError` does **not** transition to
   `failed`: the state is unchanged, the error resurfaced, the next poll
   retries. `failed` is reserved for non-retryable errors. `start` on a
   terminal state (`done`/`failed`) refuses with remediation unless `--reset`.
5. **DRY-RUN.** `start`/`release` without real credentials returns a plan only,
   writes **no** state file, and sets `dry_run: true`. Keeps CI green, no
   phantom state.
6. **Backward-compat mapping** (state → legacy stage name), so
   `tests/test_release.py` passes **unmodified**: `app_resolved`→`app_record`,
   `uploading|uploaded`→`upload`, `processing|valid`→`processing`,
   `group_linked`→`testflight_group`. State file carries `upload_id`,
   `build_id`, `processing_state`, and `schema_version`.
7. **release_id includes the account** (`--account` exists ⇒ same triple on two
   accounts must not collide). `status`/`list` read without taking the lock.

**Scope cut for v1 (ship fast, lower risk):**

- **v1 = TestFlight path only:** `created → app_resolved → uploading →
  uploaded → processing → valid → [group_linked] → done`, terminal `failed`.
  This is 100% of the resumability value at ~40% of the risk.
- **App Store path** (`version_ensured → build_attached → compliance_set →
  submitted`) and **plan/approve** move to **v1.1**, where `awaiting_approval`
  and submission-recovery get designed properly (adjustments 8–9 below).
- The **submit "no build attached" bug** was decoupled and **shipped
  immediately** as a 3-line fix (commit before this one), not gated on the
  machine.
- **Lock stale-takeover:** kept the pid-liveness check already built and
  tested (instant same-machine crash recovery — the common case; permanent
  lock-out on crash would defeat the whole purpose), with an explicit
  remediation message. Deviation from the review's "cut it" recorded here with
  justification; its limits (pid recycling, cross-machine) are listed under
  Residual risks.

**Deferred to v1.1 (documented, not lost):** submission recovery must verify an
open reviewSubmission's items reference *this* version before adopting it (8);
`version_ensured` must reject a version already READY_FOR_SALE / in review (9);
`compliance_set` (`usesNonExemptEncryption`) is a legal declaration and must
come from explicit `andp.yml`, never a default.

### 2026-07-21 — pre-release code review (verdict: corrections required → applied)

An adversarial code review of the implementation found real blockers; all were
fixed before release (TDD, `tests/test_hardening.py`):

- **BUG 1 (critical) — permanent brick on first-upload failure.** The
  write-ahead set `upload_attempted=True` *before* the reservation, so any
  transient error during the first upload stuck the release in
  `upload_incomplete` forever. **Fix:** split `upload_ipa` into
  `reserve_upload` + `transfer_reserved`; `upload_attempted`/`upload_id` are
  persisted *only after* the reservation succeeds. A retryable reservation
  failure now leaves state untouched (clean retry); a transfer failure
  self-heals once the build appears, or is recovered with `release reset`.
- **BUG 2 (critical) — untyped exceptions escaped `step()`.** Transport
  (`requests.*`) and filesystem (`FileNotFoundError`) errors crashed the
  machine and the `network_error` code was never produced. **Fix:**
  `from_unexpected()` maps them to typed errors; `step()` has a catch-all that
  keeps the "retryable → raise / terminal → fail" contract.
- **BUG 3 (major) — a corrupted state file crashed the MCP server (DoS).**
  **Fix:** service functions convert `state_corrupted`/`config_error` to error
  dicts; `release_list` reports a bad file without hiding the others;
  `mcp._call_tool` has a last-resort boundary returning a typed `isError`.
- **BUG 4 (major) — resume re-read the IPA.** **Fix:** existing state is loaded
  before hashing; `release poll`/`status` never touch the file, and the
  `ipa_unreadable` remediation points to `poll`.
- **BUG 5 (major) — terminal releases were unrecoverable.** **Fix:** `start`
  refuses a terminal release (`release_terminal`); added `--reset` /
  `release reset <id>`; poll budget raised to 120 (~2h) so normal Apple
  processing never times out spuriously.
- **BUG 6 (major) — a possibly-unsupported `filter[preReleaseVersion.version]`
  could 400 every poll.** **Fix:** dropped it; `find_build` uses the proven
  `filter[version]` and the machine pins the build id after first resolution.
- **BUG 7 (major) — TOCTOU: `step()` acted on stale in-memory state.** **Fix:**
  `step()` reloads under the lock before dispatching.

Deferred as genuinely minor (documented): finer lock tokens (BUG 8),
`get_build` by pinned id in `_do_processing` (BUG 9 — re-resolution mid-
processing is deterministic since the build number is fixed), and small
duplications (BUG 10). The blocking `andp release <ipa>` intentionally stays
its own direct implementation in v1 (not machine-backed) to avoid regressing a
tested path; unifying it is v1.1.

**Residual risks (accepted for v1):** Apple ingestion is eventually-consistent
and undocumented — rare double-upload windows remain, mitigated finally by
Apple's INVALID rejection + pinned build id; the approval gate is advisory
against a shell-wielding agent (real enforcement = host permission prompt);
local state can diverge from ASC truth if a human acts in the UI mid-release;
multi-machine concurrent drivers on the same triple stay unprotected;
file-locking on synced dirs (iCloud/Dropbox/NFS) is unreliable; CI runners are
ephemeral, so resumability in CI needs the state dir cached/artifacted —
**out of scope for v1, stated explicitly.**

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
