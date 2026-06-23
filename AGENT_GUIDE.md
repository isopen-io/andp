# ANDP Agent Guide

Welcome, Agent. You are tasked with evolving the Apple Native Delivery Platform (ANDP). This guide provides the operational context needed to maintain and extend the platform.

## Agent Responsibilities
1.  **Strict Adherence to Philosophy:** Never introduce dependencies on Ruby, Fastlane, or CocoaPods. Always favor Swift, Python, and Bash using Apple's native CLI tools.
2.  **Verify via `project.yml`:** Any change to the build process must be reflected or validated against the `project.yml` contract.
3.  **Test Everything:** Every new script or tool must have a corresponding validation step (unit or integration test).
4.  **Update `ITERATIONS.md`:** When completing a task, update the roadmap to reflect progress.

## Operational Workflow
1.  **Context Loading:** Read `README.md`, `ITERATIONS.md`, and `AGENTS.md` (if present).
2.  **Validation:** Before making changes, run `./infrastructure/validate-project.sh` to ensure the current state is consistent.
3.  **Implementation:**
    - Source code goes in `Apps/`, `Features/`, or `Packages/`.
    - Orchestration logic goes in `infrastructure/`.
    - Entry points (wrappers) remain in the root directory.
4.  **Documentation:** Update the `Documentation/` folder if logic changes.

## Tooling Reference
- **Project Generation:** `xcodegen`
- **Builds:** `xcodebuild`
- **Artifacts:** `xcarchive`, `ipa`, `pkg`
- **API:** App Store Connect API (Python-based client in `infrastructure/asc/`)

## Future Iterations Hook
When picking up a new iteration, check the next "Goal" in `ITERATIONS.md` and decompose it into specific, testable components.
