# ANDP documentation

Every feature, the why and the how. Start with the path that matches what you
are trying to do.

## Reading paths

**I want to ship an app today.**
[Quickstart](../README.md#quickstart) → [CLI.md](CLI.md) → [Release.md](Release.md)

**I want to gate my PRs.**
[PublishReadiness.md](PublishReadiness.md) → [Validation.md](Validation.md)

**I am an AI agent (or I am wiring one up).**
[Agents.md](Agents.md) *(why)* → [AgentGuide.md](AgentGuide.md) *(how)* → [Release.md](Release.md)

**I am migrating off Fastlane or Tuist.**
[Migration.md](Migration.md) → [Build.md](Build.md) → [Metadata.md](Metadata.md)

**Something is broken.**
[Troubleshooting.md](Troubleshooting.md) → [Validation.md](Validation.md)

**I want to extend ANDP.**
[Developer.md](Developer.md) → [Design/](Design/) → [Architecture/Diagrams.md](Architecture/Diagrams.md)

---

## Reference

### Publishing

| Doc | What it covers |
|---|---|
| [Release.md](Release.md) | The release machine: every state, its guarantees, `--replace-in-review`, recovery |
| [Validation.md](Validation.md) | The four gates — credentials, package, metadata, CI — and what each cannot catch |
| [PublishReadiness.md](PublishReadiness.md) | The CI entry point: GitHub Actions, reusable workflow, tri-state verdict |
| [Metadata.md](Metadata.md) | The `deliver`-style folder tree for release notes, screenshots and previews |
| [StoreConfig.md](StoreConfig.md) | Pricing, territory availability and age rating, declared in `andp.yml` |
| [ASC-API.md](ASC-API.md) | The App Store Connect API layer: auth, endpoints, limits, what is impossible by API |

### Building

| Doc | What it covers |
|---|---|
| [Build.md](Build.md) | `build` / `run` / `test` / `targets`: the target model, destinations, error codes |
| [BuildNumber.md](BuildNumber.md) | `build-number`: the three strategies and which are monotonic |

### Operating

| Doc | What it covers |
|---|---|
| [CLI.md](CLI.md) | Every command, every flag, every exit code |
| [Configuration.md](Configuration.md) | The `.andp/` namespace, the credential cascade, typed config errors |
| [Security.md](Security.md) | Secret handling, the audit trail, the guardrails and their honest limits |
| [Operations.md](Operations.md) | Runners, multi-account, artifacts, key rotation |
| [Troubleshooting.md](Troubleshooting.md) | Symptom → cause → fix |

### Agents

| Doc | What it covers |
|---|---|
| [Agents.md](Agents.md) | Why ANDP is agent-native: the three primitives, guardrails, threat model |
| [AgentGuide.md](AgentGuide.md) | The end-to-end playbook: loop contract, full surface, error taxonomy, worked example |

### Contributing

| Doc | What it covers |
|---|---|
| [Developer.md](Developer.md) | Repo layout, TDD workflow, how to add a command |
| [Migration.md](Migration.md) | Coming from Fastlane or Tuist |
| [Governance.md](Governance.md) | The quality, accessibility, localization and supply-chain layer |
| [Architecture/Diagrams.md](Architecture/Diagrams.md) | System, container, component and sequence diagrams |

### Design records

Written before the code, kept as the rationale afterwards.

| Doc | Decision |
|---|---|
| [Design/agentic-core.md](Design/agentic-core.md) | Why a resumable state machine, and its invariants |
| [Design/build-number.md](Design/build-number.md) | Why three strategies, and why `commit` is not monotonic |
| [Design/publish-readiness-actions.md](Design/publish-readiness-actions.md) | Why a tri-state verdict rather than pass/fail |
| [Design/store-config-parity.md](Design/store-config-parity.md) | Reaching, and exceeding, `deliver` parity |

### Articles

| Doc | Subject |
|---|---|
| [articles/build-upload-api-observed-contract.md](articles/build-upload-api-observed-contract.md) | The three undocumented Build Upload API requirements, with verbatim errors |
| [articles/capacitor-without-appflow.md](articles/capacitor-without-appflow.md) | Publishing a Capacitor app without Appflow |

---

## Conventions in these docs

- **Every result is a typed envelope.** `{command, ok, …}`, or
  `{command, ok:false, error:{code, message, retryable, remediation}}`.
  Documented behaviour is always the envelope, never the human line.
- **Exit codes are part of the contract.** 0 success · 1 failed · 2 usage ·
  3 unverified (`readiness` only).
- **DRY-RUN is a first-class mode.** Without real credentials, commands return a
  plan and exit 0. `verify` is the deliberate exception.
- **Anything irreversible is named as such** in the doc that introduces it.
