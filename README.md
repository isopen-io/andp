# ANDP — Apple Native Delivery Platform

[![ANDP Pipeline](https://github.com/isopen-io/andp/actions/workflows/pipeline.yml/badge.svg)](https://github.com/isopen-io/andp/actions/workflows/pipeline.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**API-first App Store Connect publishing.** ANDP builds, signs, verifies and publishes Apple apps using only Apple-supported tooling and the official App Store Connect API — no altool, no Transporter, no Ruby.

> **Meeshy, the app in `examples/meeshy/`, is a sample app.** It exists to exercise and demonstrate the tooling (it is also the integration fixture for CI). ANDP itself is the product: the `andp` Python package, the pipeline scripts, and the governance layer.

## Why ANDP

- **Honest preflight** — `andp verify [bundle_id]` proves publishing will work *before* you build: credentials completeness (field-by-field placeholder detection), ES256 JWT signing, live API authentication, app record lookup. It exits 1 when publishing is impossible, and tells you exactly why.
- **Pure Build Upload API** — uploads use Apple's HTTP reserve/upload/commit flow (GA late 2025). The implementation encodes the *observed* API contract, including behaviors the documentation does not show (mandatory `app` relationship, `assetType: ASSET`, mandatory `uti`).
- **Provisioning by API** — bundle IDs, certificates and App Store profiles are created through the API (`provisioning.py`), which also works when the API key lacks xcodebuild's cloud-signing permission.
- **The IPA is the source of truth** — upload metadata (bundle id, version, build) is read from the IPA's own Info.plist, so ANDP publishes apps built anywhere, not just in this repo.
- **Governance built in** — every pipeline run can emit a CycloneDX SBOM, a security audit, a governance report and a productivity dashboard.
- **Multi-account native** — every command takes `--account` (see `secrets.example.yml`).
- **Agent-native** — every command speaks `--json`, `andp release` drives IPA→TestFlight in one call, and `python3 -m andp.mcp` exposes publishing as MCP tools with policy guardrails (App Review submission off by default) and a JSONL audit trail. See [`Documentation/Agents.md`](Documentation/Agents.md).

## Install

```bash
pip install -e .        # installs the `andp` CLI
# or, without installing:
python3 -m andp verify
```

## Quickstart

```bash
cp secrets.example.yml secrets.yml   # fill in key_id, issuer_id, key_content (never committed)

andp verify me.your.app              # preflight: can I publish?
andp upload build/Your.ipa           # Build Upload API (reads version from the IPA)
andp release build/Your.ipa --group "Beta"   # upload -> wait VALID -> TestFlight group
andp status me.your.app 42           # poll processing state
andp testflight me.your.app "Beta" add tester@example.com
andp submit me.your.app 1.2.0        # App Review submission
```

Add `--json` to any command for a structured, agent-friendly envelope.

Without real credentials every command (except `verify`) runs in DRY-RUN mode — it validates inputs, prints what it would do, and exits 0 so CI stays green.

## Gate your PRs with the preflight (GitHub Action)

```yaml
- uses: isopen-io/andp@main
  with:
    key-id: ${{ secrets.ASC_KEY_ID }}
    issuer-id: ${{ secrets.ASC_ISSUER_ID }}
    private-key: ${{ secrets.ASC_PRIVATE_KEY }}
    bundle-id: me.your.app     # optional: also checks the app record exists
```

The job fails — with the exact reason — whenever publishing cannot work: placeholder or missing credentials, a key the live API rejects, or a missing app record. Cheapest release insurance you can add to a pipeline.

Full pipeline as a reusable workflow instead:

```yaml
jobs:
  release:
    uses: isopen-io/andp/.github/workflows/andp-release.yml@main
    with: { scheme: MyApp, app-dir: ., andp-ref: main }
    secrets: inherit
```

## Pipeline scripts

The shell layer drives a full delivery pipeline against the app in `$ANDP_APP_DIR` (default: `examples/meeshy`):

```bash
./generate.sh                        # XcodeGen project generation
./build.sh <Scheme> Release iphoneos # build (analytics recorded)
./test.sh <Scheme>                   # simulator tests + quality report
./archive.sh <Scheme> && ./sign.sh build/<Scheme>.xcarchive
./asc-manager.sh upload build/exported/<Scheme>.ipa
./infrastructure/governance-report.sh --full   # SBOM + security + AI quality
```

Point `ANDP_APP_DIR` at any XcodeGen-based app directory to drive another project with the same pipeline.

## Repository layout

- `andp/` — the Python package (`andp.asc`: auth, client, apps, builds, provisioning, TestFlight, App Store, CLI)
- `infrastructure/` — pipeline scripts: validation, analytics, governance, SBOM, security audit, dashboards
- `examples/meeshy/` — the sample app (Apps/, packages/, project.yml) used by CI as integration fixture
- `tests/` — pytest suite for the package (contract tests encode the live API behavior)
- `Documentation/` — guides, including `Documentation/ASC-API.md` (the API research and conventions)

## CI

`.github/workflows/pipeline.yml` runs the full pipeline on the example app: bootstrap → validate → infrastructure tests → governance → build → archive → sign → upload. Jenkins, Azure Pipelines and GitLab CI definitions are kept aligned.

## Documentation

- [`Documentation/AgentGuide.md`](Documentation/AgentGuide.md) — **the end-to-end agent playbook**: from code to a live App Store submission (state machine, full CLI/MCP/service surface, error taxonomy, worked example)
- [`Documentation/Agents.md`](Documentation/Agents.md) — why ANDP is agent-native (the three primitives, guardrails, threat model)
- [`Documentation/StoreConfig.md`](Documentation/StoreConfig.md) — pricing, territory availability, and age rating via `andp.yml`
- [`Documentation/Metadata.md`](Documentation/Metadata.md) — the `deliver`-style metadata/media folder convention
- [`Documentation/ASC-API.md`](Documentation/ASC-API.md) — the App Store Connect API layer (auth, DRY-RUN convention, API limits, verify preflight)
- [The Build Upload API contract you'll actually hit](Documentation/articles/build-upload-api-observed-contract.md) — the three undocumented requirements, with verbatim errors
- [Publishing a Capacitor app without Appflow](Documentation/articles/capacitor-without-appflow.md) — the migration path, proven in production

## License

Apache-2.0 — see [LICENSE](LICENSE). Security reports: see [SECURITY.md](SECURITY.md).
