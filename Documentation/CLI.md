# CLI reference

Every command in one place: what it does, every flag, every exit code.

```
andp <command> [args] [--account <id>] [--json]
```

- `--json` — a structured envelope on stdout instead of human text. Available on
  **every** command.
- `--account <id>` — select a non-`primary` account block from `secrets.yml`.

Without usable credentials, every command **except `verify`** runs in DRY-RUN:
it validates inputs, returns the plan, and exits 0 so CI stays green.
[`verify` fails on purpose](Validation.md#1-the-credentials-gate--verify).

## Universal exit codes

| Code | Meaning |
|---|---|
| 0 | success (or a DRY-RUN plan) |
| 1 | the operation failed |
| 2 | usage error — bad flags or missing arguments |
| 3 | `readiness` only: **unverified**, could not evaluate |

## The failure envelope

One shape for the whole tool:

```json
{"command":"release_start","ok":false,
 "error":{"code":"bundle_invalid","message":"…","retryable":false,
          "remediation":"…","context":{…}}}
```

Branch on `ok`, `error.code` and `error.retryable`. Never on prose. `context` is
present when there is something to inspect — searched paths, allowed values,
compiler error lines — so a caller can remediate without re-running to explore.

---

# App Store Connect commands

These need credentials (see [Configuration.md](Configuration.md)).

## `verify [bundle_id]`

Publish preflight: credentials → ES256 JWT → live API auth → app record lookup.

```bash
andp verify                      # credentials + API reachable
andp verify me.your.app          # … and the app record exists on this account
```

Exit 0 when publishing is possible, 1 when it is not. **The only command that
fails rather than degrading to DRY-RUN.** Details: [Validation.md §1](Validation.md#1-the-credentials-gate--verify).

## `upload <ipa_path>`

Upload a signed `.ipa` through Apple's Build Upload API. Does not wait for
processing. Bundle id, version and build number are read from the IPA's own
`Info.plist`, never from the calling repo.

```bash
andp upload build/exported/App.ipa
```

## `release <ipa_path> [--group <name>]`

Blocking one-shot for TestFlight: app lookup → upload → wait for processing →
optional group link. Returns a `stages` array.

Does **not** accept `--ship` — the App Store path is gated and resumable. Use
the subcommands below.

## `release start <ipa_path> [flags]`

Begin (or resume) a resumable release. Returns a `release_id`.

| Flag | Effect |
|---|---|
| `--group <name>` | link the build to a TestFlight group |
| `--ship` | continue past TestFlight to an App Store submission (gated) |
| `--metadata <dir>` | with `--ship`: push notes/screenshots/previews first |
| `--no-precheck` | with `--ship`: skip the built-in precheck stage |
| `--replace-in-review` | withdraw a stale pending submission so this build replaces it |

Starting the **same IPA** again resumes the existing release. Starting the same
release id with a *different* IPA fails `ipa_changed`.

`--replace-in-review` forfeits your place in Apple's review queue — that is why
it is opt-in. See [Release.md §5](Release.md#5-replacing-a-build-that-is-already-in-review).

Before any state is written, the `.ipa` is checked for fatal packaging faults
and refused with `bundle_invalid` if found ([Validation.md §2](Validation.md#2-the-package-gate)).

## `release poll <release_id>`

Advance the machine by exactly one step. Non-blocking: a build still processing
returns `state: processing` with `retry_after` in seconds.

Not idempotent — each call may perform one external effect.

## `release status <release_id>`

Read the state **without advancing** it. Safe in a loop, a dashboard, a health
check.

## `release list`

Every release and its state. A release whose state file is corrupted is listed
as `unreadable` with its error rather than hiding all the others.

## `release approve <release_id>`

Record an out-of-band human approval, opening the submit gate. Bound to a plan
hash (`build_id:version_id`) and timestamped: if the build or version changes
afterwards, the approval is stale and the release fails `plan_changed`.

## `release reset <release_id>`

Delete the release's state file. Local only — it does not un-upload a build or
un-submit a review. The escape hatch for a state file that no longer describes
reality.

## `status <bundle_id> <build_number>`

Poll one build's processing state.

## `testflight <bundle_id> <group> add [emails…]`

Ensure the TestFlight group exists, then add testers. `add` is the only
supported action.

## `submit <bundle_id> <version>`

Submit a version for App Review, attaching the latest `VALID` build first
(Apple rejects a submission whose version has no build).

Prefer `release start --ship`, which is resumable, precheck'd and gated. This
command is the direct, unguarded form.

## `precheck <bundle_id> <version>`

Read-only pre-submission validation. Never mutates. Exit 0 when zero errors.
Checks, warnings and limits: [Validation.md §3](Validation.md#3-the-metadata-gate--precheck).

## `publish <bundle_id> <version> <metadata_dir>`

Push localized release notes, screenshots and preview videos from a folder tree.
Idempotent per file — a retry uploads only what is missing. Folder convention:
[Metadata.md](Metadata.md).

## `readiness testflight <bundle_id>`
## `readiness appstore <bundle_id> <version>`

The CI gate. Tri-state verdict with GitHub-native rendering.

| Flag | Effect |
|---|---|
| `--soft` | `not_ready` exits 0 (report, don't block) |
| `--allow-unverified` | `unverified` exits 0 (fork PRs pass) |

Exit 0 ready · 1 not_ready · 3 unverified · 2 usage.
See [Validation.md §4](Validation.md#4-the-ci-gate--readiness) and
[PublishReadiness.md](PublishReadiness.md).

## `store <subcommand> <bundle_id>`

Declarative store configuration, reconciled to a desired state. Every result
carries `changed: true|false`.

```bash
andp store pricing      me.your.app [--territory USA] [--price 0.99|free]
andp store availability me.your.app [--territories USA,FRA | --all] [--new-territories]
andp store age-rating   me.your.app [--config rating.json]
andp store apply        me.your.app        # every configured block from andp.yml
```

`store apply` is best-effort: independent idempotent blocks, so a re-run heals a
partially-applied state. `availability` is **destructive** — shrinking the set
delists the app in removed territories; an empty set is refused outright.

Full reference: [StoreConfig.md](StoreConfig.md).

## `build-number [bundle_id] --strategy <max-build|timestamp|commit>`

Compute the next `CFBundleVersion`. **Prints only the number on stdout** —
banners and warnings go to stderr — so it drops straight into a build step.

```bash
agvtool new-version -all "$(andp build-number me.your.app --strategy max-build --floor 1254)"
```

| Flag | For |
|---|---|
| `--floor N` | `max-build`: never go below N |
| `--format FMT` | `timestamp`: strftime format (default `%Y%m%d%H%M`) |
| `--sha SHA` | `commit`: the sha to hash (defaults to `$GITHUB_SHA`) |
| `--digits N` | `commit`: how many hex digits to consume |

Only `max-build` touches App Store Connect. Full reference:
[BuildNumber.md](BuildNumber.md).

---

# Local tooling — no credentials needed

A build does not talk to Apple. These commands never load credentials, and
`config` exists precisely to diagnose a broken configuration.

## `build [targets…] [--all] [--archive]`

Compile the targets declared in `andp.yml`. Sequential; a failure never stops the
run, so one broken platform cannot hide the state of the others. `ok` is the
conjunction of all targets.

`--archive` chains `archive` + `-exportArchive` into `.andp/build/exported/`.

## `run <target> [--no-build] [--logs]`

Boot → build → install → launch on a simulator, or `xcrun devicectl` for a
physical device. `--logs` follows the app's log stream. Takes a single target.

## `test [targets…] [--all]`

Run the suite per target, writing `.andp/build/<target>.xcresult`.

## `targets`

List resolved targets with their effective fields after inheritance and the
`-destination` each produces.

**Overrides for build/run/test:** `--scheme`, `--configuration`, `--platform`,
`--destination`, `--os`. Highest priority, above the named target and
`defaults`. Full model: [Build.md](Build.md).

## `config [path <secrets|policy> | dir | migrate]`

Where ANDP reads its configuration.

```bash
andp config                     # the resolved diagnostic
andp config path secrets        # stdout carries only the path
andp config dir
andp config migrate             # move a legacy ./secrets.yml into .andp/
```

Full cascade and typed errors: [Configuration.md](Configuration.md).

---

# The MCP surface

```bash
python3 -m andp.mcp
```

```json
{"mcpServers":{"andp":{"command":"python3","args":["-m","andp.mcp"],
 "cwd":"/path/to/your/project"}}}
```

| MCP tool | readOnly | destructive | idempotent |
|---|---|---|---|
| `verify`, `status`, `release_status`, `release_list`, `precheck` | ✅ | — | ✅ |
| `release_start`, `testflight_add` | — | — | ✅ |
| `store_configure_pricing`, `store_set_age_rating`, `store_apply` | — | — | ✅ |
| `store_configure_availability` | — | ✅ | ✅ |
| `release_poll`, `upload` | — | — | ❌ |
| `submit` | — | ✅ | ❌ |

`submit` is refused outright unless `policy.allow_submit: true`.

**Not exposed over MCP** — CLI and library only: `release_approve`,
`release_reset`, `publish`, `readiness`, `build-number`, `config`, and the whole
local build surface. `release_approve`'s absence is the load-bearing one: an
approval gate an agent can open by itself is not a gate.

`release_start` over MCP accepts `ipa_path`, `group`, `ship`, `metadata_dir` and
`account`. `--no-precheck` and `--replace-in-review` have no MCP equivalent —
start such a release from the CLI.

Details and threat model: [Agents.md](Agents.md).

---

## See also

- [Release.md](Release.md) — the release machine in depth
- [Validation.md](Validation.md) — the four validation layers
- [AgentGuide.md](AgentGuide.md) — the end-to-end agent playbook
- [Build.md](Build.md) — targets, destinations, build errors
