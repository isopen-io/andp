## 2025-05-15 - [Infrastructure Optimization]
**Learning:** Checking for Python dependencies via `python3 -c "import module"` is significantly faster (~0.1s) than running `pip install` (~1.6s) even when dependencies are already satisfied. Similarly, `cmp -s` provides a massive speedup for visual regression tests when images are identical, avoiding the overhead of Swift execution.
**Action:** Always prefer lightweight pre-checks before invoking heavy package managers or compilers in infrastructure scripts.
