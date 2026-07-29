# Developer guide

How ANDP is built, and how to extend it without breaking its contracts.

> Ground rules and PR process: [CONTRIBUTING.md](../CONTRIBUTING.md).
> This page is the architecture behind them.

## 1. Repository layout

```
andp/                     the Python package — the product
  asc/                    App Store Connect
    auth.py               ES256 JWT, regenerated at 19 min
    client.py             JSON:API transport: pagination, 429/Retry-After, audit log
    apps.py               app record lookup
    builds.py             Build Upload API (reserve → transfer → commit), processing
    provisioning.py       bundle ids, certificates, profiles
    testflight.py         groups, testers, "What to Test", beta review
    appstore.py           versions, localizations, review submissions, release
    pricing.py            appPricePoints / appPriceSchedules
    availability.py       appAvailabilities v2
    agerating.py          the 2025 ageRatingDeclaration taxonomy
    assets.py             screenshots & preview videos (reserve → PUT → MD5 commit)
    metadata_manager.py   localized metadata sync
    config.py             account loading, placeholder detection
    managers.py           the Managers bundle passed around
    asc_manager.py        the CLI: parsing, dispatch, human rendering
  core/
    release.py            the release machine
    ipa.py                read metadata / compliance / bundle faults from an .ipa
    state.py              the state store (locking, atomic writes)
  xcode/
    targets.py            the andp.yml target model and inheritance
    destination.py        target → xcodebuild -destination
    runner.py             xcodebuild invocation, log capture, error extraction
    simulator.py          simctl: list, boot, install, launch
    device.py             devicectl
    commands.py           the build/run/test/targets CLI surface
  service.py              the library the CLI and MCP both call
  mcp.py                  the MCP server
  readiness.py            verdicts + GitHub Actions rendering
  precheck.py             read-only pre-submission validation
  publish.py              metadata/media folder push
  policy.py               andp.yml policy (cached by path+mtime)
  paths.py                the configuration cascade (pure, no error policy)
  errors.py               the typed error taxonomy
  buildnum.py             timestamp / commit build number strategies

infrastructure/           pipeline shell + analysis scripts
examples/meeshy/          the sample app, CI's integration fixture
tests/                    616 pytest tests
Documentation/            these docs
*.sh                      root-level wrappers, kept for existing CI callers
```

## 2. The layering rule

```
CLI (asc_manager.py)  ─┐
                       ├─► service.py ─► managers ─► client.py ─► ASC
MCP (mcp.py)          ─┘
```

**`service.py` is the single source of truth.** It contains pure functions that
return dicts — no printing, no `sys.exit`, no I/O beyond the API call. The CLI
owns human rendering; the MCP server owns the JSON-RPC envelope. Neither owns
behaviour.

This is what makes the MCP server library-first: it calls
`service.release_start(...)` directly instead of scraping a CLI's stdout. A bug
fixed in the service is fixed on both surfaces at once, and a test of the
service tests both.

**Consequences you must respect when adding a command:**

- New behaviour goes in `service.py` (or `core/` if it is machine logic), never
  in `asc_manager.py`.
- The handler in `asc_manager.py` does two things: parse arguments, render the
  result. If it contains an `if` about App Store semantics, it is in the wrong
  file.
- Return an envelope. Never raise out of a service function — `{ok: false,
  error: {...}}` is the contract, and an exception escaping breaks every agent
  consuming it.

## 3. TDD, non-negotiable

Every behaviour change lands with a test that failed first.

```bash
pip install -e . pytest
python3 -m pytest tests/ -q          # 616 tests, sub-second
python3 -m pytest tests/test_release.py -q
./infrastructure/tests/run_tests.sh  # full pipeline suite (macOS for some steps)
```

Tests use `FakeSession` (see `tests/conftest.py`), which records requests as
`{method, url, json}` dicts and replays a **queue** of `FakeResponse` objects.
That queue is positional: if your change adds or removes an API call, the queue
shifts and unrelated tests fail with confusing type errors. That failure is a
feature — it tells you the call sequence changed.

### Encode the *observed* contract

When the live API disagrees with Apple's documentation — and it does, see the
mandatory `app` relationship and `assetType: ASSET` in `builds.py` — the mock
encodes what the API **actually did**, with a comment citing the observation
date. A test that matches the docs and not reality is worse than no test.

### What a good test asserts

Behaviour through the public surface, not implementation:

```python
def test_replace_in_review_cancels_then_reattaches_and_submits(...):
    ...
    # The old submission was cancelled BEFORE the new one was created.
    patched = [i for i, r in enumerate(session.requests) if ...]
    created = [i for i, r in enumerate(session.requests) if ...]
    assert patched[0] < created[0]
```

Ordering, idempotency and refusals are the properties worth pinning. "This
function was called" is not.

## 4. Adding a CLI command

1. **Write the failing test** — in `tests/`, against `service.*` if it has
   behaviour, and a CLI test asserting the envelope and exit code.
2. **Implement in `service.py`**, returning `{command, ok, ...}`.
3. **Add the handler** in `asc_manager.py` and register it in `COMMANDS`.
4. **Add it to `CREDENTIAL_FREE`** if it must work without credentials
   (`config`, the build surface, offline `build-number` strategies).
5. **Update `USAGE`** in `asc_manager.py` — it is the `--help`.
6. **Expose it over MCP** only if an agent should have it. Ask whether an agent
   holding this tool defeats a guardrail: that is why `release_approve` is not
   an MCP tool.
7. **Document it** in [CLI.md](CLI.md) and, if it is a feature rather than a
   flag, its own section or page.

## 5. Adding an error code

Codes are a **public contract** — agents branch on them. Adding one is cheap;
changing one is breaking.

```python
raise AndpError(
    code="submission_not_found",         # stable, snake_case, specific
    message="Version 1.2.0 reads as 'WAITING_FOR_REVIEW' but no pending …",
    retryable=False,                     # can the SAME call succeed later?
    remediation="Inspect the submission in App Store Connect; …",
    context={"searched": [...]},         # optional: what was inspected
)
```

`retryable` is the field agents act on, so get it right: it means *the identical
call may succeed later without anything changing*. A rate limit is retryable. A
malformed IPA is not.

Then document it in the taxonomy table of the page that owns the feature.

## 6. Working on the release machine

`core/release.py` has invariants that tests enforce and reviewers should
re-check on every change:

- **One external mutation per `step()`.** Two mutations in one step means a
  crash between them is unrecoverable.
- **Persist before returning.** `step()` writes state under a lock, having
  re-read it under that lock first.
- **Write-ahead any irreversible intent.** The upload reservation id is saved
  before bytes move, so resume can distinguish "reserved" from "never reserved".
- **Waiting states never become terminal.** `prechecked`, `awaiting_approval`
  and `review_canceling` park; they do not fail. A read error there must not
  force a re-upload.
- **New state fields go in `_FIELD_DEFAULTS`.** Older state files on disk must
  keep loading after an upgrade.

Design record: [Design/agentic-core.md](Design/agentic-core.md).
Reference: [Release.md](Release.md).

## 7. Adding a build target platform

Nothing in a script. Declare it in `andp.yml`:

```yaml
targets:
  dev-vision:
    platform: visionOS
    destination: "Apple Vision Pro"
```

Adding a *platform name* to ANDP itself means touching `xcode/targets.py`
(validation) and `xcode/destination.py` (the `-destination` string). Unknown
platforms are rejected rather than defaulted — a misspelled `platfrom: iOS` must
not silently build something else. Model: [Build.md](Build.md).

## 8. Coding standards

- **Python** — PEP 8, standard library first. Three runtime dependencies total
  (`requests`, `PyYAML`, `PyJWT`); adding a fourth needs a real argument.
- **No Ruby, no Fastlane, no CocoaPods.** The whole point is Apple-native
  tooling plus the official API.
- **Comments explain *why*.** The code already says what. A comment that
  restates the line below it is noise; a comment recording why the API forced an
  odd shape is the most valuable thing in the file.
- **Bash** — `set -e`, `[[ ]]`, quote everything, support `--help`.
- Root `*.sh` scripts stay thin wrappers over `andp` subcommands, keeping their
  positional signatures so existing CI callers do not break.

## 9. Before you open the PR

```bash
python3 -m pytest tests/ -q      # green
```

- One logical change, with the reasoning in the description.
- `CHANGELOG.md` updated under *Unreleased*.
- Docs updated in the same PR — a feature nobody can find is not shipped.
- No credentials anywhere: not in code, tests, fixtures or CI files. Test
  fixtures use placeholder ids and deliberately truncated, non-functional PEM
  fragments.
