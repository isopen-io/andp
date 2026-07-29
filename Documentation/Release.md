# The release machine

A release is not a function call. It is a **resumable resource** you advance one
step at a time.

This page is the reference for that machine: why it exists, every state it can
be in, what it guarantees, and how to recover it when something goes wrong.

> For the agent-facing playbook (loop contract, worked example, MCP surface) see
> [AgentGuide.md](AgentGuide.md). For what ANDP refuses to ship in the first
> place, see [Validation.md](Validation.md).

---

## 1. Why a machine

Publishing a build is a chain of irreversible, slow, partially-asynchronous
steps against someone else's server. Three properties of that reality kill the
obvious `def release(ipa): ...` implementation:

- **Apple's processing takes minutes to hours.** A blocking call is unusable
  from an agent tool call, unpleasant in CI, and a network blip away from
  losing everything.
- **Some steps are irreversible.** An upload consumes a build number. A review
  submission takes a slot in Apple's queue. Retrying blindly after a crash is
  not "at worst a no-op" — it can double-submit or brick a build number.
- **Failure is normal.** Rate limits, transient 5xx, a build still ingesting.
  These are not exceptions; they are the steady state of a release.

So ANDP models a release as a small persisted state machine:

```
andp release start build/App.ipa --ship --json     # → release_id
andp release poll  <release_id>  --json            # advance one step
andp release poll  <release_id>  --json            # ... repeat until terminal
```

Each `poll` performs **at most one external effect** and persists the resulting
state to `.andp/state/<release_id>.json` *before returning*. Kill the process at
any point and the next `poll` continues from where it stopped.

---

## 2. The states

```
created → app_resolved → uploaded → processing → valid
                                                   │
                         (--group) group_linked ◄──┤
                                                   │            (no --ship)
                                                   └──────────────► done
  --ship:
  valid / group_linked → version_ensured → build_attached → compliance_set
       → [metadata_pending] → [prechecked] → awaiting_approval → submitted → done

  --ship --replace-in-review, version already in review:
  … → review_canceling ──(version becomes editable)──► version_ensured → …

  terminal: done | failed
```

| State | Meaning | What advances it |
|---|---|---|
| `created` | the release exists; nothing has happened | app record lookup |
| `app_resolved` | the app record was found on the account | reserve + transfer the upload |
| `uploaded` | the binary left the machine | — (bookkeeping step) |
| `processing` | Apple is ingesting the build | polling until `VALID` |
| `valid` | the build is `VALID` | TestFlight group, ship, or finish |
| `group_linked` | the build is in the TestFlight group | ship, or finish |
| `version_ensured` | an **editable** App Store version is resolved | attach the build |
| `build_attached` | the build is attached to the version | declare export compliance |
| `compliance_set` | export compliance is declared | metadata push, or precheck |
| `metadata_pending` | a `--metadata` tree is waiting to be pushed | the push itself |
| `prechecked` | pre-submission validation ran | a clean report, or a fix |
| `awaiting_approval` | **the gate** — never crossed automatically | approval or policy |
| `review_canceling` | a stale submission was withdrawn; waiting it out | the version becoming editable |
| `submitted` | the review submission was sent | — (bookkeeping step) |
| `done` | ✅ terminal success | — |
| `failed` | ❌ terminal failure; read `error` | — |

`prechecked`, `awaiting_approval` and `review_canceling` are **waiting** states,
not failure states. A release parked there is healthy and recoverable — it will
never silently become terminal, and it never forces you to re-upload.

---

## 3. What the machine guarantees

**One effect per step.** `step()` never chains two mutations. If it crashes
between them, there is no "between".

**Write-ahead intent.** The upload reservation id is persisted *before* any
bytes move. On resume the machine can tell "I reserved and may have transferred"
from "I never reserved", so it never blindly re-uploads. If a reservation exists
but no build is visible yet, it reports `upload_incomplete` (retryable) rather
than uploading a second time.

**Pinned build id.** Once a build is resolved, its id is stored and never
re-resolved. A reused build number can never make a later poll act on a
different binary.

**Locked, re-read state.** `step()` takes a lock, reloads the state from disk
under it, and acts on that — not on a snapshot taken before another driver
advanced the same release.

**Checksum-bound resume.** Starting the same release id with a *different* IPA
fails `ipa_changed` instead of quietly mixing two binaries into one release.

**Typed failure only.** Nothing untyped escapes `step()`. Transport errors,
filesystem errors and unexpected exceptions are all classified into an
`AndpError` with `code` / `retryable` / `remediation`.

**Forward-compatible state.** Fields added after schema v1 are filled from
defaults when an older state file is loaded, so an in-flight release survives an
ANDP upgrade.

---

## 4. Two things the machine refuses to do

### 4.1 It refuses to upload a package Apple will silently drop

Before the state file is even created, `release start` reads the embedded app
extensions out of the `.ipa` and refuses known-fatal packaging faults with
`bundle_invalid`. This exists because the failure it prevents is nearly
invisible: the upload reports success, and the build simply never appears.

Full rationale and rule list: [Validation.md](Validation.md#2-the-package-gate).

### 4.2 It refuses to submit to App Review on its own

The ship path stops at `awaiting_approval` and stays there. It crosses only when:

- `policy.allow_submit: true` in `andp.yml` (a repo pre-authorises CI/agents), **or**
- someone runs `andp release approve <release_id>`.

An approval is bound to a plan hash (`build_id:version_id`) and timestamped. If
the build or version changes afterwards, the approval is stale and the machine
fails `plan_changed` rather than submitting something nobody approved.

The policy is read **live** on every poll, so revoking `allow_submit` in
`andp.yml` stops an in-flight release at the gate instead of honouring the value
captured at start.

---

## 5. Replacing a build that is already in review

By default, a version already in `WAITING_FOR_REVIEW` / `IN_REVIEW` is left
strictly alone: the machine reports `done` and touches nothing. Creating a
second submission for the same version is an error, so the safe default is to
keep Apple's queue exactly as it is.

But there is a real case that default cannot express: the submission is
**stale**. You submitted, found a packaging bug, fixed it, rebuilt — and the
version is still sitting in the queue holding the old binary.

```bash
andp release start build/App.ipa --ship --replace-in-review --json
```

The machine then:

1. finds the pending submission (`find_in_review_submission`),
2. cancels it (`PATCH canceled: true`),
3. enters `review_canceling` and **polls** until the version becomes editable,
4. attaches the new build and resubmits.

Three details are encoded because each one bit in practice:

- **Cancellation is not instant.** ASC answers `CANCELING` and only *then* moves
  the version to `DEVELOPER_REJECTED`. Acting immediately would fail on a
  still-locked version — hence a polling state rather than a straight-line step.
- **A sent submission is not an open submission.** `find_open_review_submission`
  only matches the `READY_FOR_REVIEW` draft; a submission actually sent to Apple
  sits in `WAITING_FOR_REVIEW` and was invisible to every lookup until
  `find_in_review_submission` existed.
- **Disagreement is not guesswork.** If the version reads as in-review but no
  pending submission is found, the machine fails `submission_not_found` rather
  than cancelling something it does not understand.

> **This forfeits your place in Apple's review queue.** That is why it is opt-in
> and off by default, and why it is a flag rather than an inference.

---

## 6. Inspecting and recovering

```bash
andp release list --json              # every release and its state
andp release status <id> --json       # read one, without advancing it
andp release poll   <id> --json       # advance one step
andp release approve <id>             # open the submit gate
andp release reset  <id>              # discard the state and start over
```

`status` never mutates and never advances — use it in a dashboard or a health
check. `poll` is the only thing that moves.

### When a release is stuck

| Symptom | What it means | Do |
|---|---|---|
| `state: processing`, `retry_after: 60` | normal Apple ingest | keep polling, respect `retry_after` |
| `upload_incomplete` (retryable) | reserved, build not visible yet | poll again; if it never appears, `reset` |
| `needs_precheck_fix: true` | precheck found real blockers | fix what `precheck_report.checks` lists, poll |
| `needs_approval: true` | the gate | `release approve <id>`, or set policy |
| `state: failed` | terminal | read `error.remediation`, fix, then `reset` |
| `ipa_changed` at start | the file differs from the one that started this release | bump the build number, or `reset` |
| `release_terminal` at start | that release already finished | new build number, or `reset` |

`release reset <id>` deletes the state file only. It does not un-upload a build
or un-submit a review — nothing local can. It is the escape hatch for a state
file that no longer describes reality.

### The state file

`.andp/state/<release_id>.json`, where the id is
`<account>-<bundle-id>-<version>-<build>` slugified. It is plain JSON and safe
to read:

```json
{
  "release_id": "primary-me-your-app-1-2-0-1257",
  "state": "awaiting_approval",
  "bundle_id": "me.your.app", "version": "1.2.0", "build_number": "1257",
  "app_id": "6786703445", "build_id": "…", "version_id": "…",
  "upload_attempted": true, "upload_id": "…",
  "ipa_sha256": "…", "history": ["created", "app_resolved", "…"],
  "replaced_submission_id": null, "error": null
}
```

`history` is the full ordered list of states the release has been through —
the first thing to read when a release did something you did not expect.

---

## 7. The blocking one-shot (TestFlight only)

For a human or a simple CI job that just wants a beta build out, the blocking
form still exists:

```bash
andp release build/App.ipa --group "Beta" --json
```

It runs app lookup → upload → wait for processing → TestFlight group inline and
returns a `stages` array. It deliberately does **not** support `--ship`: the App
Store path is gated and resumable, and pretending it fits in one blocking call
would mean either blocking on a human approval or crossing the gate silently.

```console
$ andp release build/App.ipa --group Beta
  ✅ app_record: YourApp (me.your.app) — id 6786703445
  ✅ upload: buildUploads/… (1.2.0 build 1257)
  ✅ processing: build … is VALID
  ✅ testflight_group: build linked to group 'Beta' (…)
RELEASE SUCCEEDED
```

---

## 8. Error codes on the release path

| Code | Retryable | Meaning / fix |
|---|---|---|
| `bundle_invalid` | no | the .ipa carries a fatal packaging fault — fix and re-export |
| `ipa_unreadable` | no | not a readable signed .ipa |
| `ipa_changed` | no | different binary for an existing release id |
| `release_terminal` | no | that release already finished |
| `app_not_found` | no | create the app record in App Store Connect first |
| `upload_incomplete` | **yes** | reserved but not visible yet — poll again |
| `processing_failed` | no | Apple ended the build `FAILED`/`INVALID` |
| `processing_timeout` | no | exceeded the poll budget (~2h) — check ASC |
| `version_not_editable` | no | published/in review/unknown — bump the version |
| `submission_not_found` | no | version and submission disagree — inspect in ASC |
| `compliance_undeclared` | no | set `compliance.uses_non_exempt_encryption` or the plist key |
| `review_submission_conflict` | no | an open submission references another version |
| `plan_changed` | no | the build/version changed after approval — re-approve |
| `rate_limited` | **yes** | wait `Retry-After`, poll again |
| `asc_unavailable` / `network_error` | **yes** | transient — poll again |

The complete taxonomy, including the store and build paths, is in
[AgentGuide.md §5](AgentGuide.md#5-error-taxonomy--how-an-agent-reacts).

---

## See also

- [Validation.md](Validation.md) — the four things ANDP checks before you find out from Apple
- [AgentGuide.md](AgentGuide.md) — the agent loop contract and worked example
- [CLI.md](CLI.md) — every command, flag and exit code
- [Design/agentic-core.md](Design/agentic-core.md) — the design record behind the machine
