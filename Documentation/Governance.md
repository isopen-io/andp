# Governance

Two independent layers answer two different questions:

| Layer | Question | Where |
|---|---|---|
| **Delivery governance** | Was this release legitimate, and can we prove it? | the `andp` package |
| **Codebase governance** | Is the app itself accessible, localized, consistent, safe? | `infrastructure/` |

The first is enforced *during* a release and is not optional. The second is
analysis you run in CI and act on.

---

## Part 1 — Delivery governance

### Nothing irreversible happens by accident

| Action | Control |
|---|---|
| Submit to App Review | gated: `policy.allow_submit` or an explicit `release approve` |
| An approval after the plan changed | invalidated (`plan_changed`) — re-approval required |
| Delist territories | `destructive` annotation; an empty set refused outright |
| Replace a submission already in review | opt-in flag, CLI-only, no MCP tool |
| Approve a release | no MCP tool at all |

Policy is read **live** on every poll, so revoking `allow_submit` stops an
in-flight release rather than honouring the value captured at start.

Honest limits of these controls: [Security.md §7](Security.md#7-threat-model--the-honest-version).

### Everything that changed is recorded

```bash
export ANDP_AUDIT_LOG=/var/log/andp/audit.jsonl
```

One JSON line per **mutation** (POST/PATCH/DELETE): `ts`, `method`, `path`,
`status`. Reads are not logged, so every line in the file is something that
changed. This is the artifact that outlives the session that produced it.

### Every release is reconstructible

`.andp/state/<release_id>.json` holds the complete ordered `history` of states,
the pinned build and version ids, the IPA's SHA-256, and any recorded approval
with its timestamp and plan hash.

```bash
andp release list --json
andp release status <id> --json     # read `history`
```

### Every gate has a machine-readable verdict

`readiness` produces a tri-state verdict (`ready` / `not_ready` / `unverified`)
with blockers, warnings and remediation — as JSON, as a GitHub job summary, and
as step outputs. A gate that cannot evaluate reports `unverified`, never a false
green ([Validation.md §4](Validation.md#4-the-ci-gate--readiness)).

---

## Part 2 — Codebase governance

Run the whole set:

```bash
./infrastructure/governance-report.sh --full     # → governance_report.md
./infrastructure/generate-dashboard.sh           # → dashboard.html
```

### Design governance

- **Tool:** `infrastructure/ai-analyzer.py`
- **Rules:** Safe Area overrides (`.ignoresSafeArea()`) that break notched
  layouts; fixed frames (`.frame(width:height:)`) that block responsiveness;
  restrictive navigation styles (`.stack`) that break multi-column iPad layouts.
- **Output:** a Design Compliance Score (0–100 %).

### Asset governance

- **Tool:** `infrastructure/asset-validator.sh`
- **Scope:** `AppIcon` and `AccentColor` present for every application target;
  every target declared in `project.yml` has its required `.xcassets`.

### Accessibility governance

- **Tools:** `infrastructure/ai-analyzer.py` (static),
  `accessibility-validator.py` (runtime)
- **Scope:** missing accessibility modifiers, hint coverage, Dynamic Type
  compliance (fixed font sizes).

### Localization governance

- **Tool:** `infrastructure/localization-validator.py`
- **Reference:** `en.lproj`
- **How:** scans `.lproj` directories, parses `.strings`, compares keys against
  the reference so a missing translation is a CI failure rather than a shipped
  blank label.

### Visual regression

- **Tool:** `infrastructure/visual-compare.sh`
- **Output:** side-by-side diffs embedded in the productivity dashboard.
  Intentional UI changes need their baselines updated.

### Supply chain and secrets

- **`infrastructure/sbom-generator.sh`** — CycloneDX SBOM from `project.yml` and
  resolved dependencies.
- **`infrastructure/security-auditor.sh`** — secret pattern scan, SBOM matched
  against known vulnerabilities, `codesign -vvvv` signature verification.
- **`infrastructure/certificate-manager.sh`** — discovers signing identities in
  the Keychain and maps provisioning profiles.

Details: [Security.md](Security.md).

### Release and versioning helpers

| Script | Role |
|---|---|
| `version-manager.sh` | semantic versioning |
| `release-manager.sh` | changelog generation, git tagging |
| `artifact-manager.sh` | organises build outputs for distribution |

For the build number specifically, prefer `andp build-number` — it queries App
Store Connect for the real latest build rather than trusting a local file
([BuildNumber.md](BuildNumber.md)).

---

## See also

- [Security.md](Security.md) — secrets, guardrails, threat model
- [Validation.md](Validation.md) — the four pre-flight gates
- [Operations.md](Operations.md) — running all of this in CI
