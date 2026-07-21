# Design — Publish-readiness GitHub Actions

> Goal (user request): *"crée les actions Github permettant de vérifier si une
> application iOS peut être publiée sur TestFlight sans soucis ou sur AppStore
> sans soucis. Le début de notre porte d'entrée."*

Two CI-native readiness gates, plus the library primitive that powers them, so
a repo can answer — on every PR/push, with a red/green check and a readable
report — **"can this iOS app go to TestFlight cleanly?"** and **"can this
version go to the App Store cleanly?"**

This is the *entry point* (`porte d'entrée`): the cheapest, most honest signal a
team (or an agent) can gate on before spending build minutes or a review slot.

## 0. What each question actually means

| Question | Primitive | Green means | Red means |
|---|---|---|---|
| Can I deliver to **TestFlight** without issues? | `verify [bundle]` | credentials sign (ES256), authenticate against the live API, **and** the app record exists | placeholder/missing creds, unusable key, API rejects auth, or no app record |
| Can I publish this version to the **App Store** without issues? | `precheck <bundle> <version>` | version editable, a build is attached, description present, ≥1 screenshot (0 errors) | any of those missing, or version/app not found, or no credentials |

`verify` is intentionally a **preflight**: it proves the *upload path is
unblocked*; it does not build or upload. `precheck` is a **read-only**
pre-submission validator; `ok:true` is necessary, not sufficient (Apple still
validates synchronously at submit — surfaced in the report's note).

Non-goal: replacing the delivery workflow (`andp-release.yml`). These gates
*precede* it — they say whether it's worth running.

## 1. Architecture (library-first, no stdout scraping)

```
verify logic ──► service.verify()           ┐
                                             ├─► readiness.py (pure normalize + render)
precheck ──────► service.precheck()          ┘
                     │
                     ▼
        service.readiness_testflight() / readiness_appstore()
                     │            (normalized verdict)
        ┌────────────┼─────────────────────────────┐
        ▼            ▼                               ▼
   CLI `andp      MCP (future)          GitHub side-effects:
   readiness …`                         $GITHUB_STEP_SUMMARY (markdown),
                                        $GITHUB_OUTPUT (ready/reason/…),
                                        ::error:: / ::warning:: annotations
                     ▲
        ┌────────────┴───────────────┐
        ▼                            ▼
 .github/actions/testflight-  .github/actions/appstore-
 readiness/action.yml         readiness/action.yml
                     ▲
                     │ workflow_call
        .github/workflows/publish-readiness.yml  (runs both, one report)
```

### 1.1 `service.verify(bundle_id=None, account="primary") -> dict`  (NEW, extracted)

Today the verify *logic* lives inside `asc_manager._cmd_verify`, tangled with
`print()`. Extract the checks into a pure library function returning the same
envelope the CLI already emits:

```json
{"command": "verify", "ok": bool,
 "checks": [{"name": "credentials|jwt|api_auth|app_record", "ok": bool,
             "detail": "...", "missing": ["issuer_id", ...]?}],
 "app": {"id": "...", "name": "...", "bundle_id": "..."}?}
```

Rules (identical to current behavior, so existing tests stay green):
- dry-run (placeholders) → `ok:false`, single failing `credentials` check with
  `missing:[...]` (verify is the one command that **fails** in dry-run — honesty).
- JWT sign fail → `ok:false`, failing `jwt` check.
- API rejects → `ok:false`, failing `api_auth` check.
- bundle given & not found → `ok:false`, failing `app_record` check.
- Never prints, never raises (wraps `ASCAuthError`/`ASCAPIError`).

`_cmd_verify` is **refactored to delegate**: call `service.verify()`, then
reproduce the exact human lines + `PREFLIGHT PASSED/FAILED` epilogues from the
returned checks (epilogue chosen by which check failed). Existing 6 verify
tests are the regression guard.

### 1.2 `andp/readiness.py` (NEW, pure — the normalizer + renderer)

`verify` and `precheck` have *different* result shapes. Normalize both to one
**verdict** so the CLI, the actions, and (later) MCP render identically:

```json
{"command": "readiness", "target": "testflight|appstore",
 "ready": bool, "reason": "one line",
 "bundle_id": "...", "version": "..."?,  "app": {...}?,
 "credentials_ready": bool,
 "blockers": [{"id": "...", "detail": "..."}],
 "warnings": [{"id": "...", "detail": "..."}],
 "note": "..."?, "checks": [ ...passthrough... ]}
```

Pure functions (fully unit-testable, no I/O):
- `testflight_verdict(verify_result) -> verdict`
  - `ready = verify_result["ok"]`
  - `blockers` = failing checks → `{id:name, detail}`
  - `credentials_ready = False` iff a failing check is named `credentials`
  - `reason` = success line, else the first blocker's detail
- `appstore_verdict(precheck_result) -> verdict`
  - error envelope (`no_credentials`/`app_not_found`/`version_not_found`/…) →
    `ready:false`, one blocker `{id:error.code, detail:error.message}`,
    `credentials_ready = (code != "no_credentials")`
  - otherwise `ready = precheck["ok"]`; `blockers` = `level=="error"` checks,
    `warnings` = `level=="warning"` checks; carry `note`
- `render_markdown(verdict) -> str` — the `$GITHUB_STEP_SUMMARY` block: a verdict
  headline (✅/❌), bundle/version, blocker table, warning table, the note.
- `render_annotations(verdict) -> list[str]` — `::error title=…::id: detail` per
  blocker, `::warning …::` per warning (GitHub workflow-command lines).
- `render_outputs(verdict) -> dict` — flat `{ready, reason, blockers, warnings,
  credentials_ready}` for `$GITHUB_OUTPUT` (`ready` = `"true"/"false"`).

### 1.3 `service.readiness_testflight` / `readiness_appstore`

Thin library glue: call `service.verify` / `service.precheck`, hand the raw
result to the matching `*_verdict`, return the verdict. No printing.

### 1.4 CLI `andp readiness <testflight|appstore> <bundle> [version] [--json] [--soft]`

- Dispatches to the service, gets a verdict.
- `--json` → print verdict JSON to **stdout** (only).
- else → print a human summary to stdout.
- **GitHub side-effects, gated on env presence (so it's inert locally):**
  - `GITHUB_STEP_SUMMARY` set → append `render_markdown`.
  - `GITHUB_OUTPUT` set → append `render_outputs` lines.
  - `GITHUB_ACTIONS` set → print `render_annotations` to **stderr** (keeps
    `--json` stdout clean; annotations are best-effort UX, not the source of truth).
- **Exit code = the gate:** `0` if `ready`; `1` if not — **unless `--soft`**,
  which always exits `0` (report-only; used by fork PRs / warn-only mode). The
  verdict JSON/summary still reports `ready:false` truthfully under `--soft`.
- Usage error (bad target / missing args) → exit `2`.
- `appstore` requires `version`; `testflight` ignores a version arg.

### 1.5 Composite actions (thin wrappers)

`.github/actions/testflight-readiness/action.yml` and
`.github/actions/appstore-readiness/action.yml` — a composite that:
1. `pip install` the package (from `github.action_path`'s repo root, i.e. two
   levels up — see §3.2 risk).
2. Writes a locked-down `secrets.yml` from `key-id`/`issuer-id`/`private-key`
   inputs (same `umask 077` + `mktemp -d` pattern as the existing root action).
3. Runs `python3 -m andp readiness <target> <bundle> [version]` with `--soft`
   iff `fail-on: never`. The CLI writes the summary + outputs itself.
4. The run step has `id: gate`; action `outputs` map to `steps.gate.outputs.*`
   (`ready`, `reason`, `blockers`, `warnings`, `credentials-ready`).

Inputs: `key-id`, `issuer-id`, `private-key` (required), `bundle-id` (required),
`version` (appstore: required; if empty, fall back to `./VERSION`), `fail-on`
(`errors` default | `never`), `working-directory` (default `.`).

### 1.6 Reusable workflow `.github/workflows/publish-readiness.yml`

`on: workflow_call` with `scheme`/`app-dir`/`version`/`fail-on` inputs and
`secrets: inherit`. Two jobs (or one job, two steps) on `ubuntu-latest` (no Mac
needed — these are API calls, not builds): TestFlight gate, then App Store gate.
Each publishes its Step Summary. Documented usage snippet in README.

## 2. Edge cases the tests must cover (TDD RED list)

**service.verify**
1. dry-run/placeholder creds → ok:false, credentials blocker names missing fields.
2. unusable ES256 key → ok:false, jwt blocker.
3. API 401 → ok:false, api_auth blocker.
4. bundle not found → ok:false, app_record blocker; `app` absent.
5. bundle found → ok:true; `app` populated; filter[bundleId] used.
6. no bundle → ok:true; hits `GET /v1/apps?limit=1`.

**readiness.py (pure)**
7. testflight_verdict maps ok:true → ready, no blockers, credentials_ready:true.
8. testflight_verdict on missing-creds verify → credentials_ready:false.
9. appstore_verdict on clean precheck → ready:true, warnings carried.
10. appstore_verdict with error envelope `version_not_found` → ready:false, one
    blocker, credentials_ready:true.
11. appstore_verdict `no_credentials` → credentials_ready:false.
12. appstore_verdict with error-level checks → blockers; warning-level → warnings.
13. render_markdown contains verdict + each blocker/warning id.
14. render_annotations emits one `::error` per blocker, `::warning` per warning,
    and escapes newlines in detail (GitHub requires `%0A`).
15. render_outputs `ready` is the string `"true"`/`"false"`.

**service.readiness_* (integration over FakeSession)**
16. readiness_testflight ready path (queue app lookup) → ready:true.
17. readiness_testflight app-not-found → ready:false, blocker id `app_record`.
18. readiness_appstore clean → ready:true.
19. readiness_appstore version-not-found → ready:false.

**CLI `andp readiness`**
20. testflight ready → exit 0, `--json` prints verdict with `ready:true`.
21. appstore not-ready → exit 1.
22. `--soft` on a not-ready result → exit 0 but JSON still `ready:false`.
23. bad target → exit 2.
24. appstore without version → exit 2.
25. GITHUB env set → writes markdown to `$GITHUB_STEP_SUMMARY` file and
    `ready=…` to `$GITHUB_OUTPUT` file (assert file contents; use tmp files).
26. `--json` mode: stdout is pure JSON (annotations went to stderr).

**Actions/workflow** — validated by YAML lint + a doc example; the *logic* is all
in tested Python, the YAML is a thin wrapper (kept deliberately dumb).

## 3. Risks / open questions (fed to design review)

- **R1 (dry-run honesty vs fork PRs).** verify fails without creds. A fork PR has
  no secrets → hard red. Mitigation: `fail-on: never` + `credentials_ready` output
  lets a caller detect "skipped for lack of creds" vs "genuinely not ready".
  Is `--soft` returning exit 0 the right default carve-out, or should a distinct
  exit code (e.g. 3) mark "unknown/no-creds" so callers can branch? **Decide.**
- **R2 (annotations channel).** Are `::error::` lines parsed by the runner from
  **stderr**? If not, they won't render (summary + exit code still correct).
  Alternative: in non-json mode print them to stdout. **Decide the channel.**
- **R3 (`$GITHUB_OUTPUT` scoping).** The CLI appends to the file; those become the
  *invoking step's* outputs. The composite step needs an `id` and the action must
  map outputs. Verify multiline-safe (`reason` could contain `\n`? keep it one line).
- **R4 (install path).** Nested action at `.github/actions/*/action.yml`: does
  `${{ github.action_path }}` point at the action dir (need repo root for
  `pip install`)? The reusable workflow avoids this by `pip install` from checkout.
  **Decide** whether the composite installs from PyPI-style path or the workflow
  handles install and the action assumes `andp` present.
- **R5 (version source).** appstore needs a version. Explicit input vs `./VERSION`
  fallback vs IPA. Keep explicit + `VERSION` fallback; document.
- **R6 (secrets in logs).** Reuse the root action's exact `mktemp`+`umask 077`+
  heredoc-via-printf pattern; never echo the key; `set -euo pipefail`.

## 4. Non-goals

- No building/signing/uploading in the gate (that's `andp-release.yml`).
- No new MCP tools in this iteration (verdict is MCP-ready; wire later).
- No mutation of App Store Connect (both primitives are read-only).

## 5. Design-review resolutions (adversarial review, pre-code)

**B1 (BLOCKER — extraction site would break verify tests 2–5).** The verify CLI
tests patch `asc_manager.make_managers` (via `fake_transport`), while the new
readiness integration tests patch `service.make_managers` (via `_real`). A
`_cmd_verify` that delegates to a *self-loading* `service.verify()` would build
managers at the wrong patch site → tests 2–5 hit the real network. **Resolution:
mirror the precheck split.** Pure core `service.verify_checks(account, managers,
bundle_id)` (managers may be `None` in dry-run) returns the envelope; it does NO
loading. `_cmd_verify` passes `main()`'s already-built managers into
`verify_checks` (CLI patch site unchanged). `service.verify(bundle_id, account)`
is a thin loader (`_managers_for` → `verify_checks`) used by `readiness_*` and
the readiness integration tests.

**B2 (BLOCKER — install path off by one).** `${{ github.action_path }}` for a
nested action is `<root>/.github/actions/<name>` — the package root (pyproject)
is **three** levels up, not two, and `github.workspace` is the *caller's* repo
for external consumers. **Resolution:** the composite installs with
`pip install "$(cd "$GITHUB_ACTION_PATH/../../.." && pwd)"` (correct for dogfood
AND external `uses: isopen-io/andp/.github/actions/...@ref`).

**B3 (BLOCKER — `$GITHUB_OUTPUT` `name=value` corrupts/spoofs on multiline).**
`reason`/`detail` can carry API-error newlines → `name=value` breaks the file or
injects fake outputs. **Resolution:** `render_outputs` writer uses a **heredoc**
per value with a unique delimiter (`{name}<<__ANDP_<uuid>__ … __ANDP_<uuid>__`);
`blockers`/`warnings` serialize to compact single-line JSON. Confirmed: a child
process appending to `$GITHUB_OUTPUT` yields the invoking composite step's
outputs (so `steps.gate.outputs.*` + action `outputs:` mapping works).

**S1 (annotations channel).** Workflow commands render reliably from **stdout**,
not stderr; the CI path runs the CLI without `--json` anyway. **Resolution:**
emit `::error::`/`::warning::` to **stdout** when `GITHUB_ACTIONS` is set and not
`--json`; suppress under `--json` (JSON already carries blockers/warnings).

**S2 + S3 + S7 (honesty: usage/unknown must not go green as "ready").** A
tri-state status replaces the boolean-only gate:

| status | meaning | exit | `ready` output | headline |
|---|---|---|---|---|
| `ready` | evaluated, 0 blockers | 0 | `true` | ✅ |
| `not_ready` | evaluated, genuine blocker | 1 (→0 with `--soft`) | `false` | ❌ |
| `unverified` | couldn't evaluate: no/placeholder creds, `config_error`, or a **retryable** API error (429/5xx/network) | 3 (→0 with `--allow-unverified`) | `unknown` | ⚪ |
| usage error | bad target / missing version | 2 (never softened) | — | — |

`--soft` maps only `not_ready`(1)→0. `--allow-unverified` maps only
`unverified`(3)→0. Usage(2) and truly-internal failures never soften. The action
maps inputs → flags: `fail-on: never`→`--soft`; `require-credentials: false`
(default)→`--allow-unverified` (so fork PRs **skip** green with `ready=unknown`,
never a false ✅; a downstream job gating on `outputs.ready == 'true'` correctly
does not proceed). `credentials_ready` output = "creds present & non-placeholder"
(NOT "creds valid") — documented so a 401 (`ready=false`) isn't misread.

**Status derivation.** testflight: `unverified` iff a failing check is
`credentials` OR any blocker is `retryable`; else `not_ready`. appstore: on the
error envelope, `unverified` iff `no_credentials`/`config_error`/`retryable`,
else `not_ready` (app/version-not-found are *genuine* blockers); on the checks
path, `not_ready` iff any `error`-level check. `verify_checks` tags the
`api_auth` check `retryable:true` for a 429/5xx `ASCAPIError`.

**S4 (human verify lines not reproducible from `detail`).** `_cmd_verify`'s
renderer special-cases the `credentials` check (one line per `missing[]` entry,
not the generic detail) and owns a failing-check→epilogue map + the PASSED line.
Documented so the naive "print every detail" path (which fails test 1) is avoided.

**S5 (`VERSION` fallback under `cd`).** Resolve `version` in YAML **before**
`cd "$WORKDIR"` (read `${working-directory}/VERSION`), pass as an explicit arg;
empty → CLI exits 2 (usage), never a silent `0.0.0`.

**S6 (verdict info loss).** Blockers carry `remediation` when present; the
appstore verdict shows `bundle_id`/`version` (run_precheck returns no app
identity — accepted, noted).

**N1** output names: underscore in `$GITHUB_OUTPUT`, action maps
`credentials-ready: ${{ steps.gate.outputs.credentials_ready }}`. **N2** add a
JSON-envelope shape test for `verify_checks`. **N3** reusable workflow uses two
**separate jobs** so a red TestFlight gate still lets the App Store gate report.
**N4** only `detail` strings (Apple's `errors[].detail`, never request headers)
reach the summary — no JWT leakage.

## 6. Code-review resolutions (adversarial review, pre-commit)

**B1 (BLOCKER — TestFlight gate crashed on a network error).** `verify_checks`
caught only `ASCAuthError`/`ASCAPIError`; a `requests` network exception
(ConnectionError/Timeout/SSLError) escaped → uncaught crash, false red, empty
`--json` stdout, and the summary/outputs writes never ran. It also broke the
docstring ("never raises") and the design's "network → unverified" rule (which
the App Store path already honored via `precheck`'s `from_unexpected`).
**Fixed:** `verify_checks` now has a trailing `except Exception` that classifies
via `from_unexpected` (network names → `retryable=True`) and returns a retryable
`api_auth` blocker, so `_status` yields `unverified`. Test:
`test_verify_checks_network_error_is_retryable_not_raised`. This also hardens the
plain `andp verify` CLI against the same crash.

**S1 (SHOULD-FIX — `credentials_ready` disagreed across gates on config_error).**
appstore reported `credentials_ready=True` for `config_error` while testflight
reported `False`. **Fixed:** `appstore_verdict` treats `config_error` (and
`no_credentials`) as `credentials_ready=False` — one consistent signal. Test:
`test_appstore_config_error_is_unverified_and_creds_not_ready`.

**NITs applied:** `render_markdown` routes the app name and reason through
`_cell` (escape `|`/newlines); the `fail-on: never` input doc now says "green
when ready or not_ready" (not "always green"). The `ref: inputs.andp-ref` note
(caller-controlled `workflow_call` input into `checkout`'s `ref:`, not shell —
no injection) is acknowledged and accepted.

Everything else the reviewer checked — the exit-code state machine, the 8 pinned
verify tests' envelope fidelity, the `managers=None`-for-all-dry-run change, the
Actions secret handling and `$GITHUB_OUTPUT` heredoc plumbing — was confirmed
correct. **274 tests green.**
