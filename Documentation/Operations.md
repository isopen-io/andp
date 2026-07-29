# Operations guide

For whoever runs ANDP in CI and keeps the runners alive.

## 1. Requirements

| | Needed for |
|---|---|
| Python 3.9+ | everything |
| `requests`, `PyYAML`, `PyJWT` | the package (installed by `pip install -e .`) |
| macOS + Xcode | building, signing, simulators |
| XcodeGen | project generation (`brew install xcodegen`) |

**The publishing surface does not need macOS.** `verify`, `upload`, `release`,
`precheck`, `readiness`, `store` and `publish` are pure HTTP — they run on Linux
runners. Only `build` / `run` / `test` need Xcode, and they need no credentials.

That split is worth exploiting: gate your PRs with `readiness` on cheap Linux
runners, and reserve macOS minutes for actual builds.

```bash
./infrastructure/prepare-remote-node.sh   # provision a new CI runner
./infrastructure/bootstrap.sh             # dependencies on an existing one
```

## 2. Credentials in CI

Never a committed file. Inject through the platform's secret store and write the
file at runtime:

```yaml
- run: |
    mkdir -p .andp && chmod 700 .andp
    cat > .andp/secrets.yml <<'YAML'
    accounts:
      primary:
        asc_api:
          key_id: "${{ secrets.ASC_KEY_ID }}"
          issuer_id: "${{ secrets.ASC_ISSUER_ID }}"
          key_content: |
    YAML
    printf '%s\n' "${{ secrets.ASC_PRIVATE_KEY }}" | sed 's/^/          /' >> .andp/secrets.yml
    chmod 600 .andp/secrets.yml
```

Or skip it: the provided GitHub Actions take `key-id` / `issuer-id` /
`private-key` inputs and handle this themselves
([PublishReadiness.md](PublishReadiness.md)).

`$ANDP_CONFIG_DIR` overrides the whole runtime namespace — useful when a runner
shares a workspace between jobs and you want isolation:

```bash
export ANDP_CONFIG_DIR=/run/andp-$JOB_ID
```

It takes the head of the credential cascade **and** redirects `build/`,
`metrics/` and `artifacts/`. Full cascade: [Configuration.md](Configuration.md).

### Least privilege

| Operation | Minimum role |
|---|---|
| Build upload | `DEVELOPER` |
| App Review submission | `ADMIN` or `APP_MANAGER` |
| Provisioning (bundle ids, certs, profiles) | a **Team Key** — Individual Keys cannot |

Give CI a key that can upload and nothing more, unless CI genuinely submits.

## 3. Multiple teams and accounts

```yaml
accounts:
  team_a:
    asc_api: { key_id: …, issuer_id: …, key_content: | … }
  team_b:
    asc_api: { key_id: …, issuer_id: …, key_content: | … }
```

Every command takes `--account <id>` (default `primary`). The account id is part
of the release id, so two accounts publishing the same bundle never collide in
`.andp/state/`.

## 4. The runtime namespace

Everything ANDP writes lives under `.andp/` — one gitignored directory.

| Path | Contents | Safe to delete? |
|---|---|---|
| `.andp/secrets.yml` | credentials | **no** |
| `.andp/state/` | in-flight releases | **no** while a release is in flight |
| `.andp/build/` | archives, exported IPAs, `.xcresult` | yes |
| `.andp/build/logs/` | full xcodebuild output | yes |
| `.andp/metrics/`, `.andp/artifacts/` | pipeline analytics, reports | yes |

**Clear `.andp/build/` between CI runs.** Leave `.andp/state/` alone: deleting a
state file mid-release does not cancel anything on Apple's side, it just loses
track of what already happened. To discard a release deliberately, use
`andp release reset <id>` — which at least tells you it existed.

On an ephemeral runner, state does not persist between jobs. That is fine for
TestFlight; for a `--ship` release that parks at `awaiting_approval`, either run
the poll loop in one job or persist `.andp/state/` as an artifact between them.

## 5. The audit trail

```bash
export ANDP_AUDIT_LOG=/var/log/andp/audit.jsonl
```

Every API **mutation** (POST/PATCH/DELETE) is appended as one JSON line —
`ts`, `method`, `path`, `status`. Reads are not logged, so the file stays small
and every line is something that changed state.

Turn this on wherever an agent publishes. "What exactly did it do?" should
always be answerable, and it is the only artifact that answers it after the
context is gone.

## 6. Monitoring

```bash
andp release list --json     # every release and its state
```

Worth alerting on:

- a release in `processing` for more than ~2 h → it will hit `processing_timeout`
- a release in `awaiting_approval` → someone needs to act
- a release in `failed` → read `error.code`
- `state: unreadable` in the list → a corrupted state file

Pipeline analytics land in `metrics/`:

| File | Contents |
|---|---|
| `build_metrics.json` | build duration and status |
| `test_metrics.json` | test results and coverage |
| `ai_analysis.json` | quality risks from the AI layer |

```bash
./infrastructure/generate-dashboard.sh          # → dashboard.html
./infrastructure/governance-report.sh --full    # SBOM + security + quality
```

## 7. Rate limits

~3500 requests/hour per API key, reported in the `X-Rate-Limit` header. The
client honours `Retry-After` on 429 automatically, and `rate_limited` is
returned as **retryable** with the state unchanged.

The one thing that actually breaks this: a poll loop ignoring `retry_after`.
That field is part of the contract. Several parallel releases against the same
key share the budget — stagger them if you run a large matrix.

## 8. Maintenance

**Rotating an API key.** Create the new key in App Store Connect first, update
`key_id` + `key_content`, run `andp verify` to prove it works, *then* revoke the
old one. Not the other way around.

**Upgrading ANDP.** State files carry a schema version and unknown-to-old fields
are filled from defaults, so a release started before an upgrade keeps polling
after it. Still worth draining in-flight releases before a major bump.

**Xcode / XcodeGen.** `brew upgrade xcodegen`. A new Xcode can change
`-destination` resolution; `andp targets` shows what ANDP thinks it will build,
before you find out from a failed archive.

## See also

- [Configuration.md](Configuration.md) — the cascade and typed config errors
- [Security.md](Security.md) — secret handling, keychain isolation, guardrails
- [Troubleshooting.md](Troubleshooting.md) — symptom → cause → fix
- [PublishReadiness.md](PublishReadiness.md) — the CI gates
