# ANDP — Apple Native Delivery Platform

[![ANDP Pipeline](https://github.com/isopen-io/andp/actions/workflows/pipeline.yml/badge.svg)](https://github.com/isopen-io/andp/actions/workflows/pipeline.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**API-first App Store Connect publishing.** ANDP builds, signs, verifies and publishes Apple apps using only Apple-supported tooling and the official App Store Connect API — no altool, no Transporter, no Ruby.

> **Meeshy, the app in `examples/meeshy/`, is a sample app.** It exists to exercise and demonstrate the tooling (it is also the integration fixture for CI). ANDP itself is the product: the `andp` Python package, the pipeline scripts, and the governance layer.

## Why ANDP

- **Honest preflight** — `andp verify [bundle_id]` proves publishing will work *before* you build: credentials completeness (field-by-field placeholder detection), ES256 JWT signing, live API authentication, app record lookup. It exits 1 when publishing is impossible, and tells you exactly why.
- **It refuses to ship a doomed package** — embedded extensions are read out of the `.ipa` before a single byte moves. A packaging fault Apple would accept and then *silently drop during processing* becomes an immediate `bundle_invalid`, not three hours of watching a build that never appears.
- **Pure Build Upload API** — uploads use Apple's HTTP reserve/upload/commit flow (GA late 2025). The implementation encodes the *observed* API contract, including behaviors the documentation does not show (mandatory `app` relationship, `assetType: ASSET`, mandatory `uti`).
- **Provisioning by API** — bundle IDs, certificates and App Store profiles are created through the API (`provisioning.py`), which also works when the API key lacks xcodebuild's cloud-signing permission.
- **The IPA is the source of truth** — upload metadata (bundle id, version, build) is read from the IPA's own Info.plist, so ANDP publishes apps built anywhere, not just in this repo.
- **Resumable releases** — a release is a persisted state machine, not a blocking call. One external effect per step, written to disk before returning; a crash loses nothing and it never re-uploads.
- **Governance built in** — every pipeline run can emit a CycloneDX SBOM, a security audit, a governance report and a productivity dashboard.
- **Multi-account native** — every command takes `--account` (see `secrets.example.yml`).
- **Agent-native** — every command speaks `--json`, `andp release` drives IPA→TestFlight in one call, and `python3 -m andp.mcp` exposes publishing as MCP tools with policy guardrails (App Review submission off by default) and a JSONL audit trail. See [`Documentation/Agents.md`](Documentation/Agents.md).

---

## "Why not just let the agent do it by hand?"

It can. An agent has a shell, `curl`, and enough knowledge to sign a JWT. The
question is not *can it* — it is **what it costs, every single time**, because
none of what it learns survives the session.

### The incident this tool was built from

On 2026-07-28 a real delivery was completed by hand, agent-driven, without ANDP.
Everything below is measured from that session — not a benchmark, one honest
data point.

The upload reported success. `No errors uploading`. Then **nothing** — no build
in App Store Connect, no build in TestFlight, no error. Three hours of polling
before anyone concluded something was actually wrong. The cause was one
misplaced key in an embedded extension's `Info.plist`: `NSExtensionActivationRule`
sitting under `NSExtension` instead of inside `NSExtensionAttributes`. Apple had
accepted the bytes and dropped the package during processing, asynchronously.

Then the fixed build could not replace the old one, because the version was
already `WAITING_FOR_REVIEW`. That took discovering — by trial and error against
the live API — that the submission had to be cancelled first, that the endpoint
listing "open" submissions does not show submissions that were actually *sent*,
and that cancellation is asynchronous so the version stays locked for a while
afterwards.

### The same delivery, two ways

| Step | Agent by hand | With ANDP |
|---|---|---|
| Detect the fatal packaging fault | not detected — 3 h of silence, then `xcrun altool --validate-app` on a hunch | `release start` → `bundle_invalid` in **~1 s**, offline, naming the `.appex` |
| Authenticate to ASC | hand-roll ES256 JWT, write the `.p8` to disk, `chmod`, remember to delete it | automatic |
| Find the pending submission | 2 wrong endpoints before the right filter | `find_in_review_submission` |
| Cancel it | discover `PATCH canceled:true` by trial | one state transition |
| Wait out the cancellation | didn't know it was async — first retry failed on a locked version | `review_canceling` polls until editable |
| Re-attach the build + resubmit | 4 hand-written REST calls, no idempotency | 3 machine states, write-ahead persisted |
| Recover from a crash mid-way | unknown state; inspect ASC by hand and guess | `release poll` resumes exactly where it stopped |

### Iterations, time, tokens

Measured from that session; the ANDP column is the same work re-run through the
tool. "Turns" = agent round trips, the most honest unit here — it is what you
actually pay for and wait on.

| Phase | By hand | With ANDP |
|---|---|---|
| Diagnose the silent rejection | ~25 turns + **3 h** wall-clock | 1 turn, ~1 s |
| Discover the cancel/resubmit path | ~20 turns (2 dead ends) | 0 — encoded |
| Execute the resubmission | ~12 turns | 1 command + ~4 polls |
| Fix and re-verify | ~13 turns | unchanged |
| **Total** | **~70 turns · ~4 h** | **~8 turns · ~12 min** |
| Approx. billed tokens | **~3–5 M** input (largely cached) · ~70 k output | ~300 k input · ~6 k output |

Token figures are orders of magnitude from one Claude Code session on a large
repo, not a controlled measurement — the turn count is the number to trust.

### What that costs

The token line is the small one. It is the human hours and the calendar that
hurt.

| | By hand | With ANDP | Saved |
|---|---|---|---|
| Agent tokens (@ ~$5/M in, ~$25/M out, illustrative) | ~$20–27 | ~$1.70 | **~$20–25** |
| Engineer time (@ $100/h) | 4 h → $400 | 0.2 h → $20 | **$380** |
| **Per incident** | **~$425** | **~$22** | **~$400** |
| Release slot in Apple's queue | forfeited *twice* (blind resubmit) | forfeited once, deliberately, behind a flag | 1 review cycle |

Apply your own rates — the shape holds. **The token saving is ~5 % of the
benefit; the other 95 % is the four hours and the lost review cycle.** Anyone
selling you an agent tool on token savings alone is measuring the wrong thing.

### The argument that actually matters: it compounds

A hand-driven agent pays the discovery cost **on every delivery**. It does not
remember that the Build Upload API needs an `app` relationship the docs never
mention, that a sent submission is invisible to the "open submissions" filter,
or that cancellation is asynchronous. Each session rediscovers all of it, often
by making the same mistake.

ANDP paid that cost **once**, and it is now 616 tests.

| | Hand-driven agent | ANDP |
|---|---|---|
| Cost of the 1st delivery | high | high (already paid, by us) |
| Cost of the 10th | **the same** | ~1 command |
| Knowledge of past failures | none — context is gone | encoded as tested behaviour |
| Silent-rejection detection | rediscovered, or missed again | a regression test |
| Crash mid-delivery | unknown state, inspect by hand | resumes from disk |
| Accidental submission to review | possible | gated, plan-bound, audited |

A tool is compressed, verified experience. That is the whole pitch: not that an
agent *cannot* publish an app by hand, but that it should not have to learn
Apple's undocumented edges from scratch, at production cost, every time.

> **When ANDP is not worth it:** a one-off upload to TestFlight on an app with
> no extensions and no App Store submission. `xcrun altool` is fine. The value
> starts the first time something fails in a way the API does not tell you about.

---

## Quickstart

### 1. Install

```bash
pip install -e .        # installs the `andp` CLI
# or, without installing:
python3 -m andp verify
```

### 2. Give it credentials

Create an App Store Connect API key (**Team Key** — Individual Keys cannot do
provisioning) in *App Store Connect → Users and Access → Integrations*. The `.p8`
file downloads **once**.

```bash
mkdir -p .andp && cp secrets.example.yml .andp/secrets.yml
```

```yaml
# .andp/secrets.yml — never committed
accounts:
  primary:
    asc_api:
      key_id:    "ABCDE12345"
      issuer_id: "69a6de89-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      key_content: |
        -----BEGIN PRIVATE KEY-----
        …
        -----END PRIVATE KEY-----
```

Not sure where ANDP is reading from? `andp config` tells you which file won and
where else it looked.

### 3. Prove it works — before building anything

```bash
$ andp verify me.your.app
ASC publish preflight (account 'primary'):
  ✅ credentials — key_id ABCDE12345, issuer_id set, private key present
  ✅ JWT signed (ES256)
  ✅ API authentication accepted
  ✅ app found: YourApp (me.your.app) — id 6786703445
PREFLIGHT PASSED — the tool can publish to App Store Connect.
```

This is the one command that fails instead of degrading to DRY-RUN — its whole
job is to tell the truth. Exit 1 means don't start the build yet.

> The app *record* must exist once in App Store Connect (`POST /v1/apps` does not
> exist). Everything after that is API-driven.

### 4. Build a signed IPA

Use ANDP, or any pipeline you already have — ANDP reads the metadata from the
binary, so it publishes IPAs built anywhere.

```bash
andp targets                 # what can be built, with resolved destinations
andp build prod --archive    # → .andp/build/exported/
```

### 5. Ship it

**To TestFlight**, one blocking call:

```bash
andp release build/exported/App.ipa --group "Beta"
```

**To the App Store**, as a resumable machine:

```bash
andp release start build/exported/App.ipa --ship --metadata ./metadata --json
# → {"release_id":"primary-me-your-app-1-2-0-1257","state":"created","next":"poll"}

andp release poll primary-me-your-app-1-2-0-1257 --json
# → {"state":"processing","retry_after":60}      … wait, poll again
# → {"state":"awaiting_approval","needs_approval":true}

andp release approve primary-me-your-app-1-2-0-1257   # the one deliberate step
andp release poll    primary-me-your-app-1-2-0-1257 --json
# → {"state":"done","terminal":true}
```

Each `poll` performs **at most one external effect** and persists state before
returning. Kill it anywhere; the next `poll` continues. It never re-uploads.

The submit gate is never crossed automatically — see
[Release.md](Documentation/Release.md#42-it-refuses-to-submit-to-app-review-on-its-own).

### Also worth knowing

```bash
andp precheck me.your.app 1.2.0      # read-only: will Apple reject this?
andp store apply me.your.app         # price, territories, age rating from andp.yml
andp build-number me.your.app --strategy max-build --floor 1254
andp testflight me.your.app "Beta" add tester@example.com
andp release list --json             # every release and where it is
```

Add `--json` to any command for a structured, agent-friendly envelope. Without
real credentials every command (except `verify`) runs in DRY-RUN — it validates
inputs, prints what it would do, and exits 0 so CI stays green.

**Next:** [CLI reference](Documentation/CLI.md) · [the release machine](Documentation/Release.md) · [all documentation](Documentation/README.md)

---

## Gate your PRs with the preflight (GitHub Action)

```yaml
- uses: isopen-io/andp@v1
  with:
    key-id: ${{ secrets.ASC_KEY_ID }}
    issuer-id: ${{ secrets.ASC_ISSUER_ID }}
    private-key: ${{ secrets.ASC_PRIVATE_KEY }}   # the raw .p8 contents
    bundle-id: me.your.app     # optional: also checks the app record exists
```

The job fails — with the exact reason — whenever publishing cannot work: placeholder or missing credentials, a key the live API rejects, or a missing app record. Cheapest release insurance you can add to a pipeline.

### Publish-readiness gates (TestFlight / App Store)

Two richer checks answer, on every PR, *can this app go to TestFlight cleanly?* and *can this version go to the App Store cleanly?* — each with a readable job-summary report and a tri-state verdict (✅ ready / ❌ not_ready / ⚪ unverified, so a fork PR never goes falsely green):

```yaml
- uses: isopen-io/andp/.github/actions/testflight-readiness@v1
  with: { key-id: ${{ secrets.ASC_KEY_ID }}, issuer-id: ${{ secrets.ASC_ISSUER_ID }},
          private-key: ${{ secrets.ASC_PRIVATE_KEY }}, bundle-id: me.your.app }

- uses: isopen-io/andp/.github/actions/appstore-readiness@v1
  with: { key-id: ${{ secrets.ASC_KEY_ID }}, issuer-id: ${{ secrets.ASC_ISSUER_ID }},
          private-key: ${{ secrets.ASC_PRIVATE_KEY }}, bundle-id: me.your.app, version: "1.2.0" }
```

Or both at once via the reusable workflow `isopen-io/andp/.github/workflows/publish-readiness.yml@v1`. See [`Documentation/PublishReadiness.md`](Documentation/PublishReadiness.md). The same logic is a CLI: `andp readiness testflight <bundle>` / `andp readiness appstore <bundle> <version>`. A single unified action is also published: [`isopen-io/ios-publish-readiness@v1`](https://github.com/isopen-io/ios-publish-readiness).

Full pipeline as a reusable workflow instead:

```yaml
jobs:
  release:
    uses: isopen-io/andp/.github/workflows/andp-release.yml@v1
    with: { scheme: MyApp, app-dir: ., andp-ref: v1 }
    secrets: inherit
```

## Building and running

`andp build`, `andp run` and `andp test` drive Xcode from the `targets:` block of
`andp.yml` — every scheme, on every platform your project declares. None of them
need App Store Connect credentials.

```bash
andp targets                    # what can be built, with resolved destinations
andp build --all                # every declared target, sequentially
andp build prod --archive       # archive + export to .andp/build/exported/
andp run dev-ios --logs         # boot, install, launch, follow the logs
andp test --all --json          # structured result per target
```

See [Build](Documentation/Build.md) for the target model, destinations, the JSON
envelope and the error codes.

## Pipeline scripts

The shell layer drives a full delivery pipeline against the app in `$ANDP_APP_DIR` (default: `examples/meeshy`):

```bash
./generate.sh                        # XcodeGen project generation
./build.sh <Scheme> Release iphoneos # wrapper around `andp build`
./test.sh <Scheme>                   # wrapper around `andp test` + quality report
./archive.sh <Scheme> && ./sign.sh build/<Scheme>.xcarchive
./asc-manager.sh upload build/exported/<Scheme>.ipa
./infrastructure/governance-report.sh --full   # SBOM + security + AI quality
```

Point `ANDP_APP_DIR` at any XcodeGen-based app directory to drive another project with the same pipeline.

## Repository layout

- `andp/` — the Python package
  - `andp/asc/` — App Store Connect: auth, client, apps, builds, provisioning, TestFlight, App Store, pricing, availability, age rating, CLI
  - `andp/core/` — the release machine, IPA reading and bundle validation, state store
  - `andp/xcode/` — build / run / test / targets, destinations, simulators, devices
  - `andp/service.py` — the library both the CLI and the MCP server call
  - `andp/mcp.py` — the MCP server
- `infrastructure/` — pipeline scripts: validation, analytics, governance, SBOM, security audit, dashboards
- `examples/meeshy/` — the sample app (Apps/, packages/, project.yml) used by CI as integration fixture
- `tests/` — 616 pytest tests (contract tests encode the live API behavior)
- `Documentation/` — [start here](Documentation/README.md)

## CI

`.github/workflows/pipeline.yml` runs the full pipeline on the example app: bootstrap → validate → infrastructure tests → governance → build → archive → sign → upload. Jenkins, Azure Pipelines and GitLab CI definitions are kept aligned.

## Documentation

**[Documentation index →](Documentation/README.md)** — every guide, with reading paths.

The essentials:

- [`Documentation/CLI.md`](Documentation/CLI.md) — every command, flag and exit code, in one place
- [`Documentation/Release.md`](Documentation/Release.md) — the release machine: states, guarantees, replacing a build already in review, recovery
- [`Documentation/Validation.md`](Documentation/Validation.md) — the four gates (credentials, package, metadata, CI) and what each cannot catch
- [`Documentation/PublishReadiness.md`](Documentation/PublishReadiness.md) — the CI entry point: TestFlight & App Store readiness gates
- [`Documentation/AgentGuide.md`](Documentation/AgentGuide.md) — **the end-to-end agent playbook**: from code to a live App Store submission
- [`Documentation/Agents.md`](Documentation/Agents.md) — why ANDP is agent-native (the three primitives, guardrails, threat model)
- [`Documentation/Configuration.md`](Documentation/Configuration.md) — the `.andp/` namespace, the resolution cascade, typed configuration errors
- [`Documentation/Build.md`](Documentation/Build.md) — targets, destinations, the build envelope
- [`Documentation/StoreConfig.md`](Documentation/StoreConfig.md) — pricing, territory availability, and age rating via `andp.yml`
- [`Documentation/Metadata.md`](Documentation/Metadata.md) — the `deliver`-style metadata/media folder convention
- [`Documentation/ASC-API.md`](Documentation/ASC-API.md) — the App Store Connect API layer (auth, DRY-RUN convention, API limits)
- [The Build Upload API contract you'll actually hit](Documentation/articles/build-upload-api-observed-contract.md) — the three undocumented requirements, with verbatim errors
- [Publishing a Capacitor app without Appflow](Documentation/articles/capacitor-without-appflow.md) — the migration path, proven in production

## License

Apache-2.0 — see [LICENSE](LICENSE). Security reports: see [SECURITY.md](SECURITY.md).
