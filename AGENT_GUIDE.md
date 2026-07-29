# Contributing to ANDP as an agent

You are working **on** ANDP. If you are looking for how to *use* ANDP to publish
an app — the release machine, the CLI/MCP surface, the error taxonomy — that is
[`Documentation/AgentGuide.md`](Documentation/AgentGuide.md).

## Non-negotiables

1. **TDD.** Every behaviour change lands with a test that failed first.
   `python3 -m pytest tests/ -q` must stay green (616 tests, sub-second).
2. **No Ruby, no Fastlane, no CocoaPods.** Apple-native tooling plus the
   official App Store Connect API. A fourth runtime dependency needs an argument.
3. **Encode the *observed* API contract.** When the live API disagrees with
   Apple's documentation — and it does — the mock encodes what the API actually
   did, with a comment citing the observation date.
4. **DRY-RUN stays honest.** Without real credentials, commands return a plan
   and exit 0. `verify` is the deliberate exception: its contract is to fail
   when publishing is impossible.
5. **Never weaken secrets handling.** No credentials in code, tests, fixtures or
   CI files.

## Where code goes

| Kind | Location |
|---|---|
| Behaviour (the thing being done) | `andp/service.py`, or `andp/core/` if it is machine logic |
| App Store Connect calls | `andp/asc/` |
| Local Xcode tooling | `andp/xcode/` |
| Argument parsing + human rendering | `andp/asc/asc_manager.py` — **and nothing else** |
| Pipeline orchestration | `infrastructure/`, with a thin root wrapper |

If a handler in `asc_manager.py` contains an `if` about App Store semantics, it
is in the wrong file. Full layering rule and the checklist for adding a command:
[`Documentation/Developer.md`](Documentation/Developer.md).

## Workflow

1. Read `README.md`, `ITERATIONS.md`, and the doc that owns the area you are
   touching.
2. Write the failing test.
3. Implement the minimum that passes it.
4. Update `CHANGELOG.md` under *Unreleased*, and `ITERATIONS.md` when you close
   an iteration goal.
5. **Update the documentation in the same change.** A feature nobody can find is
   not shipped. New error codes go in the taxonomy table of the page that owns
   the feature.

## Invariants worth re-reading before touching them

- **`core/release.py`** — one external mutation per `step()`; persist before
  returning; write-ahead any irreversible intent; waiting states never become
  terminal; new state fields go in `_FIELD_DEFAULTS`.
- **Error codes are a public contract.** Agents branch on them. Adding one is
  cheap, changing one is breaking. `retryable` means *the identical call may
  succeed later without anything changing*.
- **The MCP surface is a security boundary.** Before exposing a tool, ask whether
  an agent holding it defeats a guardrail — that is why `release_approve` is not
  an MCP tool.

## Tooling

`xcodegen` · `xcodebuild` · `xcrun simctl` / `devicectl` · `codesign` ·
the App Store Connect API (`andp/asc/`).
