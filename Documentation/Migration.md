# Migration Guide: Moving to ANDP

ANDP is designed to be a native replacement for Fastlane and Tuist. This guide outlines the steps to migrate your existing projects.

## 1. From Fastlane

### Concepts Mapping
| Fastlane | ANDP |
|----------|------|
| Fastfile | Shell scripts (`build.sh`, `test.sh`, etc.) |
| Appfile  | `project.yml` + `secrets.yml` |
| Scan     | `test.sh` |
| Gym      | `archive.sh` |
| Match    | `infrastructure/certificate-manager.sh` |
| Deliver  | `asc-manager.sh` |
| Pilot    | `asc-manager.sh` |

### Steps to Migrate
1. **Remove Fastlane:** Delete `Fastfile`, `Appfile`, `Deliverfile`, and the `fastlane/` folder.
2. **Define project.yml:** Use XcodeGen to define your project structure. Map your schemes and configurations.
3. **Configure Secrets:** Copy `secrets.example.yml` to `secrets.yml` and fill in your ASC API keys and Team IDs.
4. **Update CI Pipelines:** Replace `bundle exec fastlane <lane>` calls with direct script execution (e.g., `./build.sh`).

## 2. From Tuist

### Concepts Mapping
| Tuist | ANDP |
|-------|------|
| `Project.swift` | `project.yml` |
| `tuist generate` | `./generate.sh` (XcodeGen) |
| `tuist build` | `./build.sh` |
| `tuist test` | `./test.sh` |

### Steps to Migrate
1. **Convert Project Definition:** Translate your `Project.swift` logic into the declarative `project.yml` format used by XcodeGen.
2. **Handle Dependencies:** If using Tuist's dependency management, migrate to standard Swift Package Manager definitions in `project.yml`.
3. **Switch CLI:** Replace `tuist` commands with ANDP's native wrappers.

## 3. Benefits of Migration
- **Zero Ruby Dependency:** Eliminate `Gemfile`, `Gemfile.lock`, and Ruby environment issues.
- **Pure Native Tooling:** Direct usage of `xcodebuild` ensures compatibility with the latest Apple features.
- **Faster Execution:** Reduced overhead compared to Fastlane's plugin architecture.
- **Enhanced Governance:** Built-in accessibility, localization, and security auditing.
