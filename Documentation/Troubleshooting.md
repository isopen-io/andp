# Troubleshooting

Symptom → cause → fix. Ordered by where in a delivery you hit it.

**First reflex, always:** add `--json`. Every command returns a typed envelope
with `error.code`, `error.retryable` and `error.remediation` — the human line is
a rendering, the envelope is the contract.

---

## Configuration

### Everything runs in DRY-RUN and I have real credentials

ANDP is not reading the file you think it is.

```bash
andp config          # which file won, and everywhere else it looked
```

The cascade is: `$ANDP_CONFIG_DIR/secrets.yml` → `./.andp/secrets.yml` →
`~/.andp/secrets.yml` → `./secrets.example.yml` (the template, which *forces*
DRY-RUN). First found wins.

### `config_misplaced`

`./secrets.yml` at the repo root is no longer a level of the cascade. Rather
than silently dropping to DRY-RUN — a failure that only revealed itself at
upload, after a full build — ANDP refuses to start.

```bash
andp config migrate     # → .andp/secrets.yml, dir 0700, file 0600, never overwrites
```

### `config_not_found`

No file anywhere, not even the template. The error's `context.searched` lists
every path that was checked.

```bash
mkdir -p .andp && cp secrets.example.yml .andp/secrets.yml
```

### `account_not_found`

The `--account <id>` you passed has no block under `accounts:` in `secrets.yml`.

Full reference: [Configuration.md](Configuration.md).

---

## Credentials and authentication

### `andp verify` fails on `credentials`

The envelope names each field: `{"missing": ["issuer_id"]}`. A field still
holding a template placeholder counts as missing — that is deliberate, since a
placeholder is the single most common cause of a "why is this DRY-RUN" hour.

### `andp verify` fails on `jwt`

The private key is not a usable ES256 `.p8`. Almost always line breaks: the key
must keep its real newlines. In YAML use a block scalar:

```yaml
key_content: |
  -----BEGIN PRIVATE KEY-----
  …
  -----END PRIVATE KEY-----
```

### `andp verify` fails on `api_auth` (401 / 403)

- **401** — wrong `key_id` or `issuer_id`, or a revoked key.
- **403** — the key's role is too weak. Upload needs `DEVELOPER`; submission
  needs `ADMIN` or `APP_MANAGER`. Provisioning needs a **Team Key** — Individual
  Keys cannot do it at all.

### `andp verify` fails on `app_record`

The bundle id does not exist **on this account**. There is no `POST /v1/apps`:
the app record must be created once in the App Store Connect UI. Check you are
not pointing at the wrong account with `--account`.

---

## Building

### `no_project`

No `.xcodeproj` or `.xcworkspace` at the resolved directory. Resolution order:
`$ANDP_APP_DIR` → `project.dir` in `andp.yml` → the current directory.

### `ambiguous_scheme`

Several schemes and no `targets:` block in `andp.yml`. The error's remediation
hands back the YAML to paste.

### `target_not_found` / `bad_target_config`

An unknown target name, or an unknown field/platform. A misspelled
`platfrom: iOS` is an error, not a warning — otherwise it would silently build
the default platform.

### `build_failed`

`error.context.errors` holds the last ten `error:` lines from the log, and
`log` points at the full output under `.andp/build/logs/`. That is what
separates "the build failed" from *why*.

### The build says `dry_run: true` and compiled nothing

`xcodebuild` is not on the `PATH`. That is the **only** trigger for build
DRY-RUN — if xcodebuild exists and fails, you get `build_failed`, plainly.

### `simulator_boot_failed`

The one retryable code in the build layer: `simctl` fails transiently under
load. Retry. If it persists:

```bash
xcrun simctl list
xcrun simctl shutdown all && xcrun simctl erase all   # last resort
```

### Code signing (`xcodebuild` exit 65 / 70), missing profiles

```bash
./infrastructure/certificate-manager.sh list   # what the keychain actually has
```

On CI, use a temporary keychain per build ([Security.md](Security.md#5-keychain-isolation-on-ci)).

Full build model: [Build.md](Build.md).

---

## Uploading

### `bundle_invalid` from `release start`

The `.ipa` carries a packaging fault Apple would accept and then silently drop
during processing. Nothing was uploaded and no release state was written — fix
the embedded extension's `Info.plist`, re-export, and start again.

The message names the offending `.appex` and the exact rule.
See [Validation.md §2](Validation.md#2-the-package-gate).

### The upload "succeeded" but no build ever appears

This is the failure `bundle_invalid` exists to prevent, and if you are seeing it
you almost certainly uploaded outside ANDP. Apple acknowledges the upload, then
rejects the package asynchronously during processing — there is no build to
inspect and often no error to read.

Run `andp release start <ipa> --json` on the same file: if it is one of the
detectable faults, you get the reason in a second instead of hours.

### `upload_incomplete` (retryable)

A build was reserved but is not visible yet. Inconclusive — so ANDP refuses to
re-upload rather than risk a duplicate. Poll again shortly. If it never appears,
`andp release reset <id>` and start over.

### `ipa_changed`

You started a release with one binary and are now pointing at a different one
for the same release id. Bump the build number for the new binary, or
`andp release reset <id>`.

---

## The release machine

### Stuck on `processing`

Normal. Apple's ingest takes minutes to hours. Respect `retry_after` (60s) and
keep polling. The poll budget is ~2 hours before `processing_timeout`.

### Stuck on `review_canceling`

Also normal, and only reachable with `--replace-in-review`. Cancellation is
asynchronous: ASC reports `CANCELING` and only then releases the version. Keep
polling.

### Parked on `awaiting_approval` with `needs_approval: true`

That is the gate working. Cross it deliberately:

```bash
andp release approve <release_id>
```

…or set `policy.allow_submit: true` in `andp.yml` to pre-authorise. The policy
is read live on every poll.

### `needs_precheck_fix: true`

Precheck found real blockers. Read `precheck_report.checks` — usually missing
screenshots or an empty description. Fix them (`andp publish`, or the ASC UI),
then poll again. The release is **parked, not failed**.

### `plan_changed`

The build or version changed after the approval was recorded, so the approval no
longer describes what would be submitted. Re-run `andp release approve <id>`.

### `version_not_editable`

That marketing version is published, in review, or in a state ANDP does not
recognise. Bump the version — or, if the pending submission is stale and you
mean to replace it, `--replace-in-review`
([Release.md §5](Release.md#5-replacing-a-build-that-is-already-in-review)).

### `submission_not_found`

With `--replace-in-review`: the version reads as in-review but no pending
submission was found to cancel. Version and submission disagree, so ANDP refuses
to guess. Inspect the submission in the App Store Connect UI.

### `compliance_undeclared`

Export compliance is not declared anywhere. Either:

```yaml
# andp.yml
compliance:
  uses_non_exempt_encryption: false
```

or add `ITSAppUsesNonExemptEncryption` to the app's `Info.plist`.

### `review_submission_conflict`

There is an open review submission referencing a *different* version. ANDP will
not submit the wrong thing — resolve it in the App Store Connect UI, then retry.

### `release_terminal` when starting

That release already finished. Use a new build number, or
`andp release reset <id>` to discard the state.

### A release is genuinely wedged

```bash
andp release status <id> --json    # read `history` — every state it went through
andp release reset  <id>           # discard local state only
```

`reset` does not un-upload a build or un-submit a review; nothing local can.

Full machine reference: [Release.md](Release.md).

---

## Store configuration

### `price_point_not_found`

The price must match an **exact** base-territory `customerPrice` from Apple's
price points — not an arbitrary decimal. Use `free` for zero.

### `unknown_territory` / `empty_territories`

Territories are ISO ids (`USA`, `FRA`, `DEU`). An empty set is refused outright
because it would delist the app; delisting is a UI-only operation on purpose.

### `invalid_age_rating`

A field name or value is not in the 2025 declaration taxonomy. The message names
which.

Full reference: [StoreConfig.md](StoreConfig.md).

---

## CI

### The readiness gate is green on a fork PR

It should be `unverified` (exit 3), not green. Check you are not passing
`--allow-unverified` unintentionally. Without credentials the gate must never
report `ready` — that is the whole reason the verdict is tri-state.

### `ModuleNotFoundError: No module named 'requests'` / `yaml` / `jwt`

```bash
./infrastructure/bootstrap.sh      # or: pip install -e .
```

### `xcodegen: command not found`

```bash
brew install xcodegen              # or ./infrastructure/bootstrap.sh
```

### `project.yml` validation errors

```bash
./infrastructure/validate-project.sh
```

---

## Rate limits and transient failures

`rate_limited` (429), `asc_unavailable` (5xx) and `network_error` all carry
`retryable: true` and leave the release state unchanged. Retry the same call —
the client already honours `Retry-After`. The API budget is roughly 3500
requests/hour per key.

If an agent is hammering, it is ignoring `retry_after`. That field is part of
the contract, not a suggestion.

---

## Still stuck

- `andp <command> --json` — the typed envelope, with `remediation` and `context`
- `andp release status <id> --json` — read `history`
- `ANDP_AUDIT_LOG=/tmp/audit.jsonl andp …` — every mutation, one JSON line each
- `.andp/build/logs/` — full xcodebuild output
- `metrics/` — logs from previous pipeline runs
