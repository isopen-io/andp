# ANDP Governance & Security Guide

This document describes the automated governance and security tools implemented in ANDP.

## Design Governance (Iteration 10)
Design governance ensures consistency across platforms and responsiveness for all device types.

- **Tool:** `infrastructure/ai-analyzer.py`
- **Rules:**
    - Detects Safe Area overrides (`.ignoresSafeArea()`) that might break layout on notched devices.
    - Detects fixed frames (`.frame(width:height:)`) that hinder dynamic responsiveness.
    - Flags restrictive navigation styles (`.stack`) that may break multi-column iPad layouts.
- **Scorecard:** Generates a "Design Compliance Score" (0-100%).

## Asset Governance (Iteration 10)
Asset governance verifies the integrity and completeness of the design system across all targets.

- **Tool:** `infrastructure/asset-validator.sh`
- **Scope:**
    - Verifies presence of `AppIcon` and `AccentColor` for application targets.
    - Ensures all targets defined in `project.yml` have their required `.xcassets` folders.
    - Validates target-specific asset requirements.

## Visual Regression Governance
Visual regressions are tracked to prevent unintended UI changes.

- **Tool:** `infrastructure/visual-compare.sh`
- **Reporting:** Side-by-side diffs are automatically embedded in the Developer Productivity Dashboard.

## Localization Governance
The `localization-manager.sh` script validates that all strings files across different languages have consistent keys.

- **Tool:** `infrastructure/localization-validator.py`
- **Reference Language:** `en.lproj`
- **How it works:** It scans `.lproj` directories, parses `.strings` files, and compares keys against the reference.

## Accessibility Governance
Accessibility is validated via static analysis and runtime reporting.

- **Tool:** `infrastructure/ai-analyzer.py` (Static) and `accessibility-validator.py` (Runtime)
- **Scope:** Scans for missing accessibility modifiers, hint coverage, and Dynamic Type compliance (fixed font sizes).

## Security Platform
The security platform ensures that the codebase is free of secrets and that builds are properly signed.

- **Secret Scanning:** `infrastructure/security-auditor.sh` scans for common secret patterns (API keys, tokens).
- **Supply Chain Security:** `infrastructure/sbom-generator.sh` generates CycloneDX SBOMs for dependency tracking.
- **Certificate Management:** `infrastructure/certificate-manager.sh` provides a centralized way to discover signing identities and mapping provisioning profiles.

## Release & Versioning
- **`version-manager.sh`:** Handles semantic versioning and build numbers.
- **`release-manager.sh`:** Automates changelog generation and git tagging.
- **`artifact-manager.sh`:** Organizes build outputs for distribution.
