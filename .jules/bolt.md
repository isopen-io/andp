## 2025-05-15 - [Infrastructure Optimization]
**Learning:** Checking for Python dependencies via `python3 -c "import module"` is significantly faster (~0.1s) than running `pip install` (~1.6s) even when dependencies are already satisfied. Similarly, `cmp -s` provides a massive speedup for visual regression tests when images are identical, avoiding the overhead of Swift execution.
**Action:** Always prefer lightweight pre-checks before invoking heavy package managers or compilers in infrastructure scripts.

## 2025-05-15 - [Swift 6 Actor Isolation Fix]
**Learning:** Swift 6 defaults (`SWIFT_DEFAULT_ACTOR_ISOLATION: MainActor`) can cause build failures in app extensions (like Notification Service) where system overrides are `nonisolated`. Setting `nonisolated` explicitly for these targets resolves the conflict.
**Action:** Ensure app extension targets in `project.yml` have appropriate isolation settings to match system framework expectations in Swift 6.

## 2026-06-25 - [Single-Pass Secret Scanning]
**Learning:** Combining multiple `grep` calls into a single call with an Extended Regular Expression (`grep -E "A|B|C"`) significantly reduces execution time (observed ~75% reduction) by avoiding multiple full-tree traversals and process spawning overhead. Additionally, case-insensitive directory names (e.g., `packages/` vs `Packages/`) can cause silent scanning failures on Linux CI runners; always verify target directory existence and casing.
**Action:** Prefer single-pass scans for multiple patterns and always validate target directory paths for cross-platform compatibility.

## 2026-06-26 - [Single-Pass Static Analysis]
**Learning:** Consolidating multiple sequential filesystem traversals and file reads into a single pass in Python-based static analysis scripts reduces disk I/O and processing overhead by up to 75% for four categories of analysis. This architectural efficiency ensures the tool remains performant as the codebase grows.
**Action:** Design static analysis tools to perform a single filesystem walk and file read, distributing the content to various analysis logics in memory.
