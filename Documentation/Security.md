# Security Architecture & Guide

ANDP prioritizes security through isolation, auditing, and native tool integration.

## 1. Secret Management
ANDP uses a tiered approach to secrets:
- **`secrets.example.yml`**: A public template showing required keys.
- **`secrets.yml`**: A local-only file (git-ignored) containing actual credentials.
- **Environment Variables**: CI/CD systems should inject secrets as environment variables, which the scripts are designed to prioritize.

## 2. Automated Auditing
The `infrastructure/security-auditor.sh` script performs:
- **Secret Scanning**: Scans source code for patterns matching API keys, tokens, and passwords.
- **Signature Verification**: Uses `codesign -vvvv` to ensure build artifacts (IPA, APP) are correctly signed and haven't been tampered with.

## 3. Signing Security
- **Identity Discovery**: `infrastructure/certificate-manager.sh` uses the macOS Keychain to safely discover valid signing identities.
- **Account Isolation**: Supports multiple Apple Developer accounts via the `accounts` structure in `secrets.yml`.

## 4. Keychain Isolation
On CI runners, it is recommended to create a temporary keychain for each build:
```bash
security create-keychain -p "" build.keychain
security unlock-keychain -p "" build.keychain
# ... import certificates ...
# ... build ...
security delete-keychain build.keychain
```

## 5. Security Compliance Reports
The `./test-report.sh` integrates security audit results into the final quality report, providing a single view of the project's security posture.
