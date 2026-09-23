# Bolt Performance Log

## 2026-07-01 - [LibYAML CSafeLoader Optimization]
**Learning:** Using PyYAML's LibYAML-backed `CSafeLoader` (via `getattr(yaml, 'CSafeLoader', yaml.SafeLoader)`) instead of pure-Python `safe_load` provides an ~8x performance speedup when parsing configuration and secrets YAML files across python scripts and tools.
**Action:** Always use `getattr(yaml, 'CSafeLoader', yaml.SafeLoader)` for parsing YAML in Python scripts.

## 2026-07-10 - [Dashboard Generator Single-Pass Python]
**Learning:** Consolidating multiple Python subprocess invocations and shell process forks (such as `ls -t | head` and `date`) into a single, cohesive Python script using a heredoc reduced execution time from ~0.95s to ~0.31s (~3x speedup).
**Action:** Prefer single-pass Python scripts for generating html/json artifacts instead of piping shell commands into Python.

## 2026-07-20 - [Single-Process Python Telemetry]
**Learning:** Consolidating multi-tool and multi-command pipelines (e.g., combining `date`, `tr`, `head`, `uname`, and `python` process invocations) in bash scripts into a single, native Python script with platform-native telemetry APIs reduces process-forking overhead by ~12x. This makes metric aggregation and file loading incredibly efficient and robust against shell escaping bugs.
**Action:** Prioritize single-process Python execution using the `platform` module for system metadata rather than spawning subshell pipelines like `uname` or `tr` / `head`.

## 2026-08-05 - [Target Configuration YAML Caching]
**Learning:** Caching parsed target configurations (`_load_yaml` in `andp/xcode/targets.py`) using `mtime` and absolute path keying eliminates redundant PyYAML file reading and parsing on repeated `load_targets` and `resolve` calls, giving a ~5.7x performance boost while maintaining safety via `copy.deepcopy()`.
**Action:** Ensure all YAML loading entry points in configuration models leverage `mtime`-based cached resolution with `copy.deepcopy()`.

## 2026-09-22 - [Single-Process SBOM Generation & UUID Performance]
**Learning:** In `infrastructure/sbom-generator.sh`, generating an SBOM by repeatedly spawning Python processes per dependency to read, modify, and re-write `sbom.json` created $N+1$ process forks and $N$ disk read/writes. Additionally, subshell pipelines like `tr | head` on `/dev/urandom` caused SIGPIPE (`tr: write error: Broken pipe`). Consolidating generation into a single Python pass using `uuid.uuid4()` and `CSafeLoader` eliminated process forks and pipe errors, boosting generation speed by ~10x.
**Action:** Consolidate multi-component file generation into single-pass Python executions and use native Python `uuid` instead of shell `/dev/urandom` pipelines.
