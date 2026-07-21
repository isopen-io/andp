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
