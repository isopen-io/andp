# Troubleshooting Guide

Common issues encountered when using ANDP and their solutions.

## 1. Project Generation Failures
**Issue:** `xcodegen` command not found.
- **Solution:** Run `./infrastructure/bootstrap.sh` or `brew install xcodegen`.

**Issue:** `project.yml` validation errors.
- **Solution:** Run `./infrastructure/validate-project.sh` to check for missing directories or malformed YAML.

## 2. Build & Signing Issues
**Issue:** `xcodebuild` exit code 65 or 70.
- **Solution:** This is often related to code signing. Ensure `secrets.yml` has the correct `development_team`. If on CI, ensure `CI=true` environment variable is set to enable signing bypass.

**Issue:** Missing Provisioning Profiles.
- **Solution:** Use `./infrastructure/certificate-manager.sh list` to verify identities are available in the keychain.

## 3. Test Failures
**Issue:** Simulator failed to boot.
- **Solution:** Run `./simulator-manager.sh list` to check available devices. Use `xcrun simctl shutdown all && xcrun simctl erase all` as a last resort.

**Issue:** Visual regression false positives.
- **Solution:** Update the baseline images in `Tests/VisualBaselines/` if the UI change is intentional.

## 4. App Store Connect Issues
**Issue:** `ModuleNotFoundError: No module named 'requests'`.
- **Solution:** Run `./infrastructure/bootstrap.sh` to install Python dependencies.

**Issue:** 401 Unauthorized from ASC API.
- **Solution:** Check your `issuer_id` and `key_id` in `secrets.yml`. Ensure the private key has the correct line breaks.

## 5. Getting Help
- Check the `Documentation/` folder for specific guides.
- Run scripts with no arguments to see usage instructions.
- Inspect `metrics/` for detailed logs of previous runs.
