# ANDP — Apple Native Delivery Platform

**API-first App Store Connect publishing.** ANDP builds, signs, verifies and publishes Apple apps using only Apple-supported tooling and the official App Store Connect API — no altool, no Transporter, no Ruby.

> **Meeshy, the app in `examples/meeshy/`, is a sample app.** It exists to exercise and demonstrate the tooling (it is also the integration fixture for CI). ANDP itself is the product: the `andp` Python package, the pipeline scripts, and the governance layer.

## Why ANDP

- **Honest preflight** — `andp verify [bundle_id]` proves publishing will work *before* you build: credentials completeness (field-by-field placeholder detection), ES256 JWT signing, live API authentication, app record lookup. It exits 1 when publishing is impossible, and tells you exactly why.
- **Pure Build Upload API** — uploads use Apple's HTTP reserve/upload/commit flow (GA late 2025). The implementation encodes the *observed* API contract, including behaviors the documentation does not show (mandatory `app` relationship, `assetType: ASSET`, mandatory `uti`).
- **Provisioning by API** — bundle IDs, certificates and App Store profiles are created through the API (`provisioning.py`), which also works when the API key lacks xcodebuild's cloud-signing permission.
- **The IPA is the source of truth** — upload metadata (bundle id, version, build) is read from the IPA's own Info.plist, so ANDP publishes apps built anywhere, not just in this repo.
- **Governance built in** — every pipeline run can emit a CycloneDX SBOM, a security audit, a governance report and a productivity dashboard.
- **Multi-account native** — every command takes `--account` (see `secrets.example.yml`).

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
andp status me.your.app 42           # poll processing state
andp testflight me.your.app "Beta" add tester@example.com
andp submit me.your.app 1.2.0        # App Review submission
```

Without real credentials every command (except `verify`) runs in DRY-RUN mode — it validates inputs, prints what it would do, and exits 0 so CI stays green.

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

Start with [`Documentation/ASC-API.md`](Documentation/ASC-API.md) for the App Store Connect API layer (auth, DRY-RUN convention, API limits, verify preflight).
