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
