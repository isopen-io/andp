# Operations Guide

This guide is for DevOps engineers and platform maintainers managing ANDP.

## 1. Environment Setup
The platform requires:
- macOS (for `xcodebuild`, `codesign`, etc.)
- Xcode (latest stable recommended)
- XcodeGen (`brew install xcodegen`)
- Python 3.9+ with `PyYAML`, `requests`, and `pyjwt`.

Use `infrastructure/prepare-remote-node.sh` to automate the setup of new CI runners.

## 2. Managing Multiple Teams
ANDP supports multi-tenant configurations. Update `secrets.yml` with separate account blocks:
```yaml
accounts:
  team_a:
    asc_api: { ... }
    signing: { ... }
  team_b:
    asc_api: { ... }
    signing: { ... }
```
Invoke scripts with `--account <id>` or pass the account ID as an argument to `sign.sh`.

## 3. Monitoring & Analytics
Analytics are collected in the `metrics/` directory.
- `build_metrics.json`: Duration and status of builds.
- `test_metrics.json`: Test results and coverage.
- `ai_analysis.json`: Quality risks detected by the AI layer.

Use `./infrastructure/generate-dashboard.sh` to aggregate these into a `dashboard.html` report.

## 4. Maintenance Tasks
- **Updating XcodeGen:** Periodically run `brew upgrade xcodegen`.
- **Rotating API Keys:** Update the `key_content` in `secrets.yml` and rotate keys in App Store Connect.
- **Cleaning Artifacts:** The `build/` directory should be cleared between CI runs.
