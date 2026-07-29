# Security

ANDP handles App Store Connect API keys and code-signing material. This page is
what it does about that, and — just as important — what it does **not** claim to
protect you from.

> Reporting a vulnerability: [SECURITY.md](../SECURITY.md). Do not open a public
> issue.

## 1. Where credentials live

| | Path | Committed |
|---|---|---|
| Template | `secrets.example.yml` | yes — **placeholders only** |
| Real credentials | `.andp/secrets.yml` | never — `.andp/` is gitignored wholesale |
| Declarative config | `andp.yml` | yes — policy, store desired-state, targets |

The resolution cascade is `$ANDP_CONFIG_DIR/secrets.yml` → `./.andp/secrets.yml`
→ `~/.andp/secrets.yml` → `./secrets.example.yml`. The template is deliberately
last and forces DRY-RUN.

`andp config migrate` creates `.andp/` at `0700` and the file at `0600`, and
**never overwrites** an existing target.

### Placeholder detection is a security control

`AccountConfig.is_configured()` treats a field still holding a template value as
*missing*. Without it, a half-filled `secrets.yml` would produce a run that looks
configured and silently does nothing — and the way people respond to that is by
pasting credentials into places they should not.

### The legacy location is refused, not ignored

`./secrets.yml` at the repo root is no longer read. If one is present, ANDP fails
with `config_misplaced` rather than dropping to DRY-RUN. A credentials file that
is present but unread is worse than one that is absent: it looks handled.

## 2. What happens to the private key

The `.p8` is read from the resolved `secrets.yml`, held in memory, and used for
exactly one thing: signing an ES256 JWT. It is never logged, never printed, never
written elsewhere, and never sent anywhere — only the resulting signature goes
over the wire.

Tokens are short-lived by Apple's rule (20 minutes maximum) and regenerated at
19 minutes with a 60 s margin.

## 3. Least privilege

| Operation | Minimum role |
|---|---|
| Build upload | `DEVELOPER` |
| App Review submission | `ADMIN` or `APP_MANAGER` |
| Provisioning (bundle ids, certificates, profiles) | a **Team Key** |

Individual Keys cannot do provisioning at all. Give CI the weakest key that does
its job: a runner that only uploads has no business holding a key that can submit
to review.

## 4. The audit trail

```bash
export ANDP_AUDIT_LOG=/var/log/andp/audit.jsonl
```

Every **mutation** (POST/PATCH/DELETE) is appended as one JSON line: `ts`,
`method`, `path`, `status`. Reads are not logged.

This is the control that survives the session. Agent context is gone tomorrow;
the audit line saying `PATCH /v1/reviewSubmissions/sub-old` at 23:41 is not.
Turn it on wherever automation publishes.

## 5. Keychain isolation on CI

Signing identities live in the macOS Keychain. On a shared runner, create a
throwaway keychain per build so one job cannot sign with another's identity:

```bash
security create-keychain -p "" build.keychain
security unlock-keychain -p "" build.keychain
# … import certificates, build …
security delete-keychain build.keychain
```

`./infrastructure/certificate-manager.sh list` shows what a runner can actually
sign with — the first thing to check on an `exit 65`.

## 6. Guardrails on irreversible actions

| Action | Guardrail |
|---|---|
| Submit to App Review | refused unless `policy.allow_submit: true` **or** an explicit `release approve` |
| An approval after the plan changed | invalidated — `plan_changed`, re-approval required |
| Shrinking territory availability | annotated `destructive` for MCP hosts |
| Delisting entirely (zero territories) | refused outright — UI-only on purpose |
| Replacing a submission in review | opt-in flag, CLI-only, no MCP tool |
| Approving a release | **no MCP tool** — CLI/library only |

The policy is read **live** on every poll, not captured at start. Revoking
`allow_submit` in `andp.yml` stops an in-flight release at the gate.

Approvals are bound to a plan hash (`build_id:version_id`) and timestamped, so an
approval cannot be silently reused for a different binary.

## 7. Threat model — the honest version

**What the gate actually stops.** For an **MCP-only** agent, the gate is real:
`submit` is refused by the server without policy, and `release_approve` is not
exposed as a tool at all. There is no sequence of MCP calls that submits to App
Review on its own.

**What it does not stop.** An agent with a shell — Claude Code, Cursor, Codex —
can run `andp submit`, or edit `andp.yml` and flip `allow_submit`. The effective
enforcement there is **the host's permission prompt on the command**, not ANDP.

ANDP does not pretend to sandbox a shell-wielding agent. Its job is to make the
irreversible action **explicit, annotated, gated and audited**, so the host and
the human can see it coming. If your threat model includes an agent you do not
trust with a shell, the control you need is at the host, not here.

## 8. Supply chain

```bash
./infrastructure/sbom-generator.sh              # CycloneDX JSON
./infrastructure/security-auditor.sh            # secret scan + vuln match + signature check
./infrastructure/governance-report.sh --full    # all of the above, consolidated
```

- **SBOM** — a CycloneDX inventory from `project.yml` and resolved dependencies.
- **Secret scanning** — source scanned for API-key/token/password patterns.
- **Vulnerability matching** — the SBOM checked against known-vulnerability data.
- **Signature verification** — `codesign -vvvv` on the produced artefacts.

ANDP's own runtime surface is deliberately small: three dependencies
(`requests`, `PyYAML`, `PyJWT`), no Ruby, no plugin system. Fewer things to
audit, and no third-party code executing inside a release.

## 9. Rules the project enforces on itself

- No credentials in code, tests, fixtures or CI files. Test fixtures use
  placeholder ids and deliberately truncated, **non-functional** PEM fragments.
- `.andp/` is gitignored wholesale, plus the pre-`.andp/` locations, so a stale
  checkout cannot commit secrets just because the layout moved on.
- CI receives credentials only through the platform's secret store.

## See also

- [Configuration.md](Configuration.md) — the cascade and typed config errors
- [Operations.md](Operations.md) — CI credential injection, key rotation
- [Agents.md](Agents.md) — the guardrails from the agent's side
- [Governance.md](Governance.md) — the quality and compliance layer
