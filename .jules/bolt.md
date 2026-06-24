## 2025-05-15 - [Infrastructure Optimization]
**Learning:** Checking for Python dependencies via `python3 -c "import module"` is significantly faster (~0.1s) than running `pip install` (~1.6s) even when dependencies are already satisfied. Similarly, `cmp -s` provides a massive speedup for visual regression tests when images are identical, avoiding the overhead of Swift execution.
**Action:** Always prefer lightweight pre-checks before invoking heavy package managers or compilers in infrastructure scripts.

## 2025-05-15 - [Swift 6 Actor Isolation Fix]
**Learning:** Swift 6 defaults (`SWIFT_DEFAULT_ACTOR_ISOLATION: MainActor`) can cause build failures in app extensions (like Notification Service) where system overrides are `nonisolated`. Setting `nonisolated` explicitly for these targets resolves the conflict.
**Action:** Ensure app extension targets in `project.yml` have appropriate isolation settings to match system framework expectations in Swift 6.
