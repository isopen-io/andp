## 1.10.2 - 2026-07-21
### v1.2 loose ends closed (review coverage gaps)
- Permanent 4xx on a CDN asset PUT is now non-retryable (upload_rejected) instead
  of being labelled retryable; 5xx stays retryable
- An empty locale dir is skipped (no phantom localization / no-op PATCH)
- Added coverage: preview skip idempotency, multi-locale, hidden/tooling dirs,
  multi-chunk transfer MD5, existing_filenames pagination, resume of
  metadata_pending. 210 tests

## 1.10.1 - 2026-07-21
### v1.2 hardening (pre-release code review)
- BUG 1 (critical): per-FILE idempotency for screenshots/previews (a partial set
  no longer drops the missing media on retry, which previously shipped silently)
- BUG 2: service.publish always returns a dict (wraps ASCAPIError/network errors)
- i18n: text read as UTF-8; an empty .txt no longer overwrites the field with ""
- machine passes the pinned version_id (no re-resolve); standalone publish checks
  version editability; metadata_pushed state renamed metadata_pending
- hidden/tooling dirs skipped; shared byte-transfer helper. 201 tests

## 1.10.0 - 2026-07-21
### v1.2: release notes, screenshots & preview videos
- New: preview VIDEO upload (appPreviewSets/appPreviews) alongside screenshots
- Folder-convention publisher (deliver-style): release notes per locale +
  screenshots + previews per device, idempotent (skips populated media sets)
- `andp publish <bundle> <version> <dir>` standalone command
- `release start --ship --metadata <dir>`: pushes notes + media as a resumable
  machine step BEFORE the approval gate (also via MCP release_start metadata_dir)
- Documentation/Metadata.md: the folder convention. 197 tests.

## 1.9.1 - 2026-07-21
### v1.1 hardening (pre-release code review)
- BUG 1: write-ahead submission_id + strong-consistent resume by id — the App
  Store path can no longer create a second review submission on retry
- BUG 2: the submit gate reads allow_submit LIVE from andp.yml, so revoking it
  stops in-flight releases (was frozen at start)
- BUG 3: approval is bound to the plan (approved_ts + plan_hash; plan_changed if
  the pinned build/version moved after approval)
- BUG 4: blocking `release <ipa> --ship` is rejected (points to `release start
  --ship`) instead of silently ignoring the flag
- BUG 5/6/7: needs_approval + next_action surface in the agent view; absent/
  unknown version state rejected defensively; approve() normalizes old state
- 187 tests

## 1.9.0 - 2026-07-21
### v1.1: App Store distribution path (--ship)
- The release machine now ships to App Store review, not just TestFlight:
  version -> attach build -> compliance -> awaiting_approval -> submitted -> done
- Approval gate: `release poll` stops at awaiting_approval (needs_approval) and
  never crosses it; opened by `policy.allow_submit` (andp.yml) or the out-of-band
  `release approve <id>` — keeps the destructive submit explicit and auditable
- Correctness (design-reviewed): version editability via appVersionState with
  appStoreState fallback (READY_FOR_REVIEW accepted); idempotent 3-branch
  submission recovery with review_submission_conflict escalation; export
  compliance from andp.yml or the IPA Info.plist (compliance_undeclared else)
- CLI `release start --ship` / `release approve`; MCP release_start `ship` arg
  (no approve tool — approval is a human action); andp/policy.py
- Forward-compatible state loading (older state files gain new fields as
  defaults). 179 tests.

## 1.8.0 - 2026-07-21
### Agentic core: resumable, library-first, hardened
- New `andp/core`: typed error taxonomy (code/retryable/remediation), crash-safe
  state store (atomic writes + locking), and a resumable release **state machine**
- Releases are now stateful resources: `andp release start|poll|status|list|reset`
  advance a single persisted, non-blocking step at a time — crash-safe (write-ahead
  reserve, pinned build id), with retry_after on processing and typed failures
- `andp/service.py`: library layer both CLI and MCP call — MCP is now truly
  library-first (release tools drive the machine directly, not captured stdout)
- MCP v2: protocol 2025-03-26, honest tool annotations
  (readOnly/destructive/idempotent), structuredContent, submit policy-gated
- Fixed a real bug: `submit` now attaches a VALID build before review submission
- Pre-release code review found and fixed 7 blockers (no upload brick, typed
  transport/fs errors, MCP DoS-resilience, resume without the IPA, terminal
  reset, dropped an unverified API filter, reload-under-lock) — TDD
- Design + review logs: Documentation/Design/agentic-core.md; agent guide:
  Documentation/Agents.md. 164 tests.

## 1.7.0 - 2026-07-20
### H3: agent-native publishing
- `--json` on every command: structured envelopes (checks, stages, app/build ids) an agent can reason about — no prose parsing
- `andp release <ipa> [--group G]`: one-shot IPA -> upload -> wait for Apple processing -> TestFlight group link, with per-stage results
- MCP server (`python3 -m andp.mcp`): verify/upload/release/status/testflight_add/submit as native agent tools (JSON-RPC over stdio)
- Policy guardrails (`andp.yml`): App Review submission refused for agents unless `policy.allow_submit: true`
- Audit trail: `ANDP_AUDIT_LOG` appends every API mutation (POST/PATCH/DELETE) as JSONL
- `Documentation/Agents.md`: the agent-native publishing guide
- 98 tests (18 new), verify --json validated against the live API

## 1.6.0 - 2026-07-20
### H2: public readiness
- License: Apache-2.0; CONTRIBUTING.md (TDD + observed-contract rules); SECURITY.md (credentials handling policy, private reporting)
- GitHub Action `isopen-io/andp` (action.yml): App Store Connect publish preflight as a PR gate — script validated end-to-end against the live API
- Articles: the observed Build Upload API contract (three undocumented requirements with verbatim errors) and the Capacitor-without-Appflow migration guide
- Full-history secret scan: no real key, issuer or secrets.yml ever committed; test fixtures use placeholder ids and an annotated inert PEM fragment
- README: CI badge, license badge, Action snippet, articles section

## 1.5.0 - 2026-07-20
### ANDP is the product (H1: package extraction)
- Repository restructured: the tool is the product, Meeshy is a sample app moved to `examples/meeshy/` (all pipeline scripts now target `$ANDP_APP_DIR`, default `examples/meeshy`)
- `andp` Python package extracted from `infrastructure/asc` (`andp.asc.*`, relative imports); `pip install -e .` provides the `andp` CLI, `python3 -m andp` works without install
- Tests moved to `tests/` with package imports (80 passing); wrappers `asc-manager.sh`/`metadata-manager.sh` call the package
- Reusable GitHub workflow `.github/workflows/andp-release.yml` (`workflow_call`: scheme, app-dir, andp-ref, upload) — consumable by any app repo; `pipeline.yml` dogfoods it
- README rewritten around the product positioning; docs updated to the new layout
- Proven live on an external Capacitor app (Rekonect): verify preflight, API-created distribution profile, real Build Upload, build VALID on App Store Connect

## 1.4.0 - 2026-07-20
### Iteration 11 Consolidation
- Merged Iteration 11 enterprise hardening (#58): governance report, SBOM generator, telemetry collector, asset validator, AI quality layer (dead code, nesting heuristics, design compliance score)
- Merged Iteration 9 platform expansion (#47): MeeshyTV (tvOS) and MeeshyWatch (watchOS) app targets, multi-window detection in ai-analyzer
- Merged YAML LibYAML CSafeLoader optimization with SafeLoader fallback (#72)
- Merged dashboard generation optimization: single Python process, quoted heredoc, per-section error handling (#68)
- Merged ContentView UX refactor: semantic Labels, extracted performLogout() with success haptics, combined accessibility elements (#56), logoutButton accessibility identifier (#42)
- Cherry-picked tooling fixes (#20): RTL detection in localization-validator, VERSION/BUILD_NUMBER restore in infrastructure tests, iPad orientation check, Localization Governance report section
- Aligned all four CI definitions (GitHub Actions, Jenkins, Azure, GitLab): governance audit + dashboard + artifacts everywhere, validation + infrastructure tests everywhere
- Closed 36 superseded bot-generated PRs after content-level dedup; pruned all merged branches

## 1.3.3 - 2026-06-30
### Initial Release
- 0f55f3d chore: ensure accessibility-validator.py is removed after UX merges
- 301264a 🎨 Palette: Enhance Login UX with feedback and accessibility
- e5f69c6 🎨 Palette: Enhance Accessibility and UX of Main Landing Screen
- 7fc2242 chore: remove redundant accessibility-validator.py again after cherry-pick
- ffe8d37 ⚡ Bolt: I have optimized the security audit and resolved the CI infrastructure blockers.
- b634316 chore: cleanup before merge
- 79baccb ⚡ Bolt: Unified single-pass static analysis
- 7507c2c ⚡ Bolt: Unified single-pass static analysis
- 4d9f632 Merge pull request #12 from isopen-io/sama-iteration-6-modular-governance-9800560955657982166

## 1.3.0 - 2026-06-24
- Implemented Governance & Security Platform (Iteration 3)
- Added Localization, Accessibility, and Security validators
- Added Version, Artifact, and Release management scripts
- Added Infrastructure integration tests
