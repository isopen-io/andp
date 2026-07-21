# Publish readiness — the CI entry point

Two GitHub Actions answer, on every PR/push, with a red/green check and a
readable report:

- **TestFlight readiness** — *can this iOS app be delivered to TestFlight without
  issues?* (credentials sign, authenticate against the live API, and the app
  record exists)
- **App Store readiness** — *can this version be submitted to the App Store
  without issues?* (version editable, a build attached, description present, at
  least one screenshot)

They are the cheapest, most honest signal to gate on **before** spending build
minutes or a review slot. Under the hood they run the read-only `verify` and
`precheck` primitives — no build, no upload, no mutation of App Store Connect.

## The tri-state verdict (why a fork PR never goes falsely green)

Each gate produces one of three states — never a bare pass/fail:

| Status | Meaning | Check result | `ready` output |
|---|---|---|---|
| ✅ **ready** | evaluated, zero blockers | green (exit 0) | `true` |
| ❌ **not_ready** | evaluated, a genuine blocker (fixable) | red (exit 1) | `false` |
| ⚪ **unverified** | couldn't evaluate: no/placeholder credentials (fork PR), malformed config, or a transient API error (rate limit / 5xx / network) | green *skip* by default (exit 3, softened) | `unknown` |

A fork PR has no secrets, so it reports **⚪ Unverified** and does **not** block —
but the summary is clearly not a ✅, and the `ready` output is `unknown`, so a
downstream job gating on `outputs.ready == 'true'` correctly does not proceed.

## Use it — composite actions (any app repo)

```yaml
# .github/workflows/readiness.yml in your app repo
on: [pull_request]
jobs:
  testflight:
    runs-on: ubuntu-latest
    steps:
      - uses: isopen-io/andp/.github/actions/testflight-readiness@main
        with:
          key-id:      ${{ secrets.ASC_KEY_ID }}
          issuer-id:   ${{ secrets.ASC_ISSUER_ID }}
          private-key: ${{ secrets.ASC_PRIVATE_KEY }}
          bundle-id:   me.your.app

  appstore:
    runs-on: ubuntu-latest
    steps:
      - uses: isopen-io/andp/.github/actions/appstore-readiness@main
        with:
          key-id:      ${{ secrets.ASC_KEY_ID }}
          issuer-id:   ${{ secrets.ASC_ISSUER_ID }}
          private-key: ${{ secrets.ASC_PRIVATE_KEY }}
          bundle-id:   me.your.app
          version:     "1.2.0"     # or omit and keep a ./VERSION file
```

No `actions/checkout` is required — the action installs ANDP from its own
downloaded copy. Both actions run on `ubuntu-latest` (they are API calls, not
builds).

### Inputs (both actions)

| input | required | default | notes |
|---|---|---|---|
| `key-id`, `issuer-id`, `private-key` | yes | — | pass repository secrets, never literals |
| `bundle-id` | yes | — | the app to check |
| `version` | app store: no | `''` | falls back to `<working-directory>/VERSION`; empty ⇒ the job fails loudly (usage) |
| `working-directory` | no | `.` | where to find `VERSION` |
| `fail-on` | no | `errors` | `errors` fails the check when *not_ready*; `never` reports only (green when ready or not_ready) |
| `require-credentials` | no | `false` | `false`: missing creds ⇒ ⚪ skip green; `true`: missing creds ⇒ fail |

### Outputs (for downstream gating)

`ready` (`true`/`false`/`unknown`), `status`, `reason`, `credentials-ready`,
`blockers` (JSON), and `warnings` (JSON, App Store only). Note
`credentials-ready` means *credentials were present & non-placeholder* — **not**
that they are valid (a rejected key is `ready=false`, `credentials-ready=true`).

```yaml
      - id: gate
        uses: isopen-io/andp/.github/actions/testflight-readiness@main
        with: { key-id: ..., issuer-id: ..., private-key: ..., bundle-id: me.your.app }
      - if: steps.gate.outputs.ready == 'true'
        run: echo "Safe to build & upload."
```

## Use it — reusable workflow (both gates in one call)

```yaml
jobs:
  readiness:
    uses: isopen-io/andp/.github/workflows/publish-readiness.yml@main
    with:
      bundle-id: me.your.app
      version: "1.2.0"        # omit to run only the TestFlight gate
    secrets:
      key-id:      ${{ secrets.ASC_KEY_ID }}
      issuer-id:   ${{ secrets.ASC_ISSUER_ID }}
      private-key: ${{ secrets.ASC_PRIVATE_KEY }}
```

The App Store gate is skipped automatically when no `version` is provided. The
two gates run as **separate jobs**, so a red TestFlight gate still lets the App
Store gate report its own summary.

## Use it — the CLI (agents, local, any CI)

```bash
andp readiness testflight me.your.app            # exit 0 ready / 1 not_ready / 3 unverified
andp readiness appstore  me.your.app 1.2.0
andp readiness testflight me.your.app --json     # the verdict envelope on stdout
andp readiness appstore  me.your.app 1.2.0 --soft            # not_ready -> exit 0
andp readiness testflight me.your.app --allow-unverified     # unverified -> exit 0
```

When `$GITHUB_STEP_SUMMARY` / `$GITHUB_OUTPUT` / `$GITHUB_ACTIONS` are set (i.e.
inside Actions) the command also writes the markdown report, the step outputs
(heredoc-safe), and `::error::/::warning::` annotations. Locally, those are
inert — you just get the verdict.

The verdict (`--json`):

```json
{"command":"readiness","target":"appstore","status":"not_ready","ready":false,
 "credentials_ready":true,"reason":"App Store not ready: no build attached",
 "bundle_id":"me.your.app","version":"1.2.0",
 "blockers":[{"id":"no_build","detail":"no build attached"}],
 "warnings":[{"id":"keywords_empty","detail":"keywords are empty"}],
 "note":"ok does not guarantee acceptance: ..."}
```

`ready:true` is necessary, not sufficient — Apple still validates synchronously
at submit; the `note` says what is not checked.

## Semantics & safety

- **Read-only.** Neither gate mutates App Store Connect.
- **Honest.** `verify`/`precheck` fail (or report unverified) when publishing
  genuinely can't work; a transient rate-limit or network blip is `unverified`,
  not a false red.
- **Secret-safe.** The private key is written to a `umask 077` temp `secrets.yml`
  that is removed on exit; only Apple's own error text (never request headers)
  reaches the report — no JWT leakage.
- **Fork-safe.** Missing secrets ⇒ ⚪ Unverified skip (green, `ready=unknown`) by
  default, never a false ✅; set `require-credentials: true` to fail instead.
