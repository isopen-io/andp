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

## 2026-06-26 - [Regex Search Optimization]
**Learning:** Pre-compiling regex patterns and combining multiple search strings into a single "OR" pattern (e.g., `(A|B|C)`) significantly reduces function call overhead and execution time in static analysis scripts. In `accessibility-validator.py`, this approach reduced `re.search` calls from 900 to 309 for the current codebase (~65% reduction).
**Action:** Consolidate multiple related string searches into single-pass regex operations and pre-compile patterns used in loops to improve static analysis performance.

## 2026-06-27 - [Tool Consolidation & Directory Exclusion]
**Learning:** Consolidating multiple specialized static analysis tools into a single-pass analyzer with directory exclusion (e.g., .git, .xcresult) significantly reduces CI overhead. In this codebase, merging accessibility and quality analysis into a single optimized Python script reduced test-report execution time by ~38% while improving issue reporting with line numbers.
**Action:** Always look for opportunities to merge sequential file-scanning tools and implement explicit directory exclusions for build/test artifacts to optimize filesystem traversal.

## 2026-06-27 - [Unified Static Analysis Consolidation]
**Learning:** Merging disparate static analysis scripts (Accessibility, Localization, Architecture) into a single-pass tool eliminates redundant filesystem traversals and Python process spawns. This architectural consolidation improves CI reporting speed by roughly 50% for these checks while maintaining full diagnostic parity.
**Action:** Always look for opportunities to merge tools that operate on the same source files and directory trees to minimize I/O and process overhead.

## 2026-06-28 - [Inner-Loop Optimization via Pre-indexing]
**Learning:** In static analysis tools that check multi-line context windows (e.g., verifying if a modifier exists within 20 lines of a component), repeated string concatenation and regex searching in the inner loop is extremely expensive. Pre-calculating a list of line indices matching the modifiers and using a membership check (e.g., `any(i <= idx < i + 20 for idx in modifier_indices)`) reduces complexity and avoids massive memory allocations.
**Action:** When performing sliding-window context checks in large files, pre-index pattern matches to avoid redundant work in the inner loop.

## 2026-06-29 - [Reverse-Pass Lookahead Optimization]
**Learning:** Implementing lookahead checks (e.g., "is modifier X within 20 lines after component Y?") using a reverse-pass through file lines allows for O(1) state tracking. By iterating from the end of the file, the "nearest future" location of a modifier is always known when a component is encountered, eliminating the need for nested loops or pre-indexed list traversals (`any(i <= idx < i + 20 for idx in modifier_indices)`). Combined with an `INTEREST_PATTERN` pre-filter to skip irrelevant lines, this approach significantly reduces regex engine overhead and improves cache locality.
**Action:** For static analysis patterns requiring forward-looking context, prefer a reverse-pass with state variables over forward-pass lookahead or pre-indexing to achieve O(N) complexity with minimal overhead.
