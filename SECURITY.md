# Security Policy

ANDP handles App Store Connect API keys and code-signing material. Treat every
issue in that area as sensitive.

## Reporting a vulnerability

**Do not open a public issue for security reports.** Email
**jcnm@sylorion.com** with the details (affected module, reproduction,
impact). You will receive an acknowledgement within 72 hours and a remediation
timeline within 7 days.

## Scope

- `andp/` package: JWT generation (`auth.py`), HTTP client (`client.py`),
  credentials loading (`config.py`), provisioning and upload flows.
- Pipeline scripts that touch signing material (`sign.sh`, `asc-manager.sh`).

## Handling credentials — rules the project enforces

- `secrets.yml` is **gitignored** and must never be committed. The committed
  `secrets.example.yml` contains placeholders only; `AccountConfig.is_configured()`
  detects them and forces DRY-RUN mode.
- The `.p8` private key is only ever read from `secrets.yml` (or the path the
  caller provides). It is never logged, printed, or uploaded anywhere except
  as an ES256 signature.
- CI runs must receive credentials through the platform's secret store
  (GitHub Actions secrets), never through committed files.
- API keys should follow least privilege: `DEVELOPER` role suffices for build
  upload; `ADMIN`/`APP_MANAGER` only where submission requires it.

## Supported versions

Only the latest release line receives security fixes.
