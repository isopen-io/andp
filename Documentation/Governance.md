# ANDP Governance & Security Guide

This document describes the automated governance and security tools implemented in ANDP.

## Localization Governance
The `localization-manager.sh` script validates that all strings files across different languages have consistent keys.

- **Tool:** `infrastructure/localization-validator.py`
- **Reference Language:** `en.lproj`
- **How it works:** It scans `.lproj` directories, parses `.strings` files, and compares keys against the reference.

## Accessibility Governance
Accessibility is validated as part of the test reporting process.

- **Tool:** `infrastructure/accessibility-validator.py`
- **Scope:** Scans `Apps/` for SwiftUI/UIKit components lacking `accessibilityLabel` or `accessibilityIdentifier`.
- **Integration:** Integrated into `./test-report.sh`.

## Security Platform
The security platform ensures that the codebase is free of secrets and that builds are properly signed.

- **Secret Scanning:** `infrastructure/security-auditor.sh` scans for common secret patterns (API keys, tokens).
- **Certificate Management:** `infrastructure/certificate-manager.sh` provides a centralized way to discover signing identities and mapping provisioning profiles.

## Release & Versioning
- **`version-manager.sh`:** Handles semantic versioning and build numbers.
- **`release-manager.sh`:** Automates changelog generation and git tagging.
- **`artifact-manager.sh`:** Organizes build outputs for distribution.
