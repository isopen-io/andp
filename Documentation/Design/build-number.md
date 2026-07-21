# Design — ANDP-native build number management

> User direction: *"il faut intégrer dans ANDP un moyen de gérer le build avec
> la logique fastlane ou la logique timestamp ou la logique HEX commit."*

ANDP reads the build number (`CFBundleVersion`) from the IPA and uploads it —
today the *incrementing* is delegated to fastlane. This feature makes ANDP
compute the next build number itself, so a release pipeline no longer needs
fastlane just for the build number. ANDP computes it; the build step applies it
to the Xcode project **before** archiving (a signed IPA can't be re-versioned
without breaking its signature — so ANDP computes, it does not rewrite the IPA).

## 1. Command

```
andp build-number [bundle_id] --strategy <fastlane|timestamp|commit> [options] [--json]
```

Prints just the number on stdout (so it drops straight into a build step):

```bash
agvtool new-version -all "$(andp build-number me.app --strategy fastlane --floor 1254)"
# or:  xcodebuild ... CURRENT_PROJECT_VERSION="$(andp build-number --strategy timestamp)"
```

`--json` → `{"command":"build_number","ok":true,"strategy":"fastlane",
"build_number":"1255","monotonic":true,"source":{...}}`.

Exit 0 on success; 1 on an error envelope (bad creds, app not found, no SHA…);
2 on usage (unknown/absent strategy, missing required arg).

## 2. Strategies

### 2.1 `fastlane` — ASC-aware, sequential (the max+1 logic)
`build = max(floor, latest_asc_build) + 1`.
- Needs `bundle_id` + real credentials.
- `--floor N` (default 0): the local project's current build number, so we never
  go *below* it even if ASC lags (a build still PROCESSING). This is exactly the
  meeshy Fastfile guard `max(get_build_number, latest_testflight_build_number)+1`.
- `latest_asc_build` = the **numeric maximum** `CFBundleVersion` across the app's
  recent builds (any processing state), via a new
  `BuildsManager.latest_build_number(app_id)`.
- **Monotonic: yes.** Safe for App Store (each build strictly higher).

### 2.2 `timestamp` — time-based, no ASC query
`build = utcnow().strftime(fmt)`, default `fmt = "%Y%m%d%H%M"` (`--format` to
override).
- No credentials, no bundle_id.
- **Monotonic: yes** (time only moves forward).
- **Collision window:** two builds within the same `fmt` resolution collide.
  Default to minute resolution; document that a same-minute re-run repeats.
  (`%Y%m%d%H%M%S` for second resolution if a team releases very frequently.)

### 2.3 `commit` — from the git commit (hex), unique/traceable
`build = int(sha[:digits], 16)`.
- `--sha` (default `$GITHUB_SHA`); `--digits` (default 7 → max 0xFFFFFFF =
  268,435,455, safely within a `CFBundleVersion` integer component).
- No credentials.
- **Monotonic: NO** — a hash does not increase with history. Unique and
  traceable to a commit, fine for ad-hoc/internal builds, but App Store rejects a
  build number not higher than the previous one for the same marketing version.
  The verdict/JSON carries `monotonic:false` and the human output warns.

## 3. Library-first shape

- `andp/buildnum.py` (pure): `timestamp_build(clock, fmt)`,
  `commit_build(sha, digits)`, plus `to_int_versions(list)` numeric parser.
- `BuildsManager.latest_build_number(app_id) -> int` — fetch recent builds
  (`GET /v1/builds?filter[app]=…&sort=-uploadedDate`, paginated via `get_all`
  bounded to a page), parse every `attributes.version` numerically, return the
  max (0 if none). **Numeric max, not the API's lexicographic `sort=-version`**
  (which would rank "9" above "1000").
- `service.build_number(strategy, bundle_id=None, floor=0, fmt=None, sha=None,
  digits=7, account="primary", clock=None) -> dict` — dispatches; wraps
  ASCAPIError/AndpError/Exception into the typed error envelope; dry-run only
  affects `fastlane` (no creds → error, since a real ASC lookup is required).
- CLI `_cmd_build_number` → prints number or JSON; registered in COMMANDS.

Testability: `clock` and `sha` are injected (CLI uses real `datetime`/`$GITHUB_SHA`);
`fastlane` tested over a FakeSession build list.

## 4. Edge cases (TDD RED list)

**buildnum.py (pure)**
1. timestamp: fixed clock → exact string; format override honoured.
2. timestamp: monotonic across two increasing clocks.
3. commit: `int("a1b2c3d", 16)` for 7 digits; leading-zero SHA ok.
4. commit: uppercase/lowercase hex both parse.
5. commit: non-hex SHA → error.
6. commit: digits bound respected (default 7).

**BuildsManager.latest_build_number**
7. builds [ "9", "1000", "42" ] → returns 1000 (NUMERIC max, defeats lexicographic).
8. no builds → 0.
9. non-numeric / missing version entries skipped, not crash.
10. pagination: >1 page merged (get_all).

**service.build_number**
11. fastlane: floor=1254, asc_latest=1200 → "1255".
12. fastlane: floor=0, asc_latest=1300 → "1301".
13. fastlane: no builds, floor=0 → "1".
14. fastlane: dry-run (no creds) → error envelope (needs ASC).
15. fastlane: app not found → error.
16. timestamp: injected clock → value, monotonic:true.
17. commit: sha given → hex int, monotonic:false.
18. commit: no sha and no $GITHUB_SHA → error.
19. unknown strategy → error/usage.

**CLI**
20. `build-number me.app --strategy fastlane --floor 1254` (FakeSession) → prints "1255", exit 0.
21. `--strategy timestamp` → prints a value, exit 0, no creds needed.
22. `--strategy commit --sha deadbeef` → prints int, exit 0.
23. `--json` → envelope with strategy/build_number/monotonic.
24. missing/unknown strategy → exit 2.

## 5. Non-goals
- ANDP does not run xcodebuild/agvtool — it prints the number; the pipeline
  applies it. (A signed IPA cannot be re-versioned in place.)
- No marketing-version bumping (that's a separate concern).
- `commit` is deliberately non-monotonic; we surface it, we don't "fix" it.

## 6. Design-review resolutions (adversarial review, pre-code)

**B1 (BLOCKER — DRY-RUN banner corrupts stdout).** `main()` prints the
"running in DRY-RUN mode" banner to **stdout** before dispatch; `$(andp
build-number …)` would capture it. **Fixed:** route that banner to **stderr**
(no test asserts it on stdout — verified). `_cmd_build_number` prints ONLY the
number to stdout; every warning goes to stderr.

**B2 (BLOCKER — windowed max under-shoots).** A `-uploadedDate` window can miss
the true max when marketing versions interleave, and the "`get_all` bounded to a
page" wording was contradictory. **Fixed:** `latest_build_number(app_id)` does a
**full** `get_all` over `/v1/builds?filter[app]=…` (limit 200/page, follows
`links.next`), parses each `attributes.version` as an **integer** and returns the
numeric **global max** (≥ any per-version max → `+1` always accepted by Apple).
`get_all` returns a **bare list** (not `{"data":…}`) — iterate it directly.
Non-integer/dotted or null (in-flight) versions are **skipped with a stderr
warning** (fastlane strategy assumes integer builds); `--floor` remains the
safety net for ASC eventual-consistency. The "monotonic/App-Store-safe" claim is
now conditional on this full scan (documented).

**S3 (utcnow deprecated).** Use `datetime.now(timezone.utc)` (not `utcnow()`);
the injected `clock` defaults to that. Don't collide with
`BuildsManager(clock=time.monotonic)` — different concept.

**S2 (monotonic honesty for custom `--format`).** Validate the timestamp value is
all-digits and ≤18 chars; with a **custom** `--format`, report
`monotonic:"assumed"` (only the default fixed-width format is provably
monotonic). Default `%Y%m%d%H%M` (12 digits) is valid — Apple's limit is **18
characters**, there is NO 2^32 per-component cap, so the size worry is a
non-issue.

**S4/S5 (commit footgun + cross-strategy).** Keep `commit` = `int(sha[:digits],
16)` per the user's "HEX commit" ask; it is **non-monotonic** → `monotonic:false`
in the envelope + a **stderr warning** ("not safe for sequential App Store
builds"). Add a doc warning (§5): the strategy must stay **stable within a
marketing version** (the scales differ wildly: commit ~1e8, fastlane ~1e3,
timestamp ~2e11 — switching can go backwards → Apple rejects). We surface `count`
(`git rev-list --count HEAD`) as a documented alternative but do NOT add it as a
4th strategy (shallow `fetch-depth:1` clones make it return 1 → also a footgun).

**S6 (no-creds must not fail at account load).** `load_account` raises
`ConfigError` when NO secrets file exists (`test_no_secrets_at_all_raises` pins
this — don't change it). **Fixed in `main()`:** on `ConfigError`, if the command
is `build-number`, continue with a synthetic **unconfigured** account
(`dry_run=True`, `managers=None`) so `timestamp`/`commit` run with zero secrets;
every other command still hard-fails as before. `timestamp`/`commit` never touch
the account/managers; `fastlane` reloads via `_managers_for` (like precheck) and,
unconfigured, returns a typed `no_credentials` envelope (S7).

**N1/N2 (exit codes).** `_cmd_build_number` validates the strategy and required
args **before** calling the service: unknown/absent `--strategy` → exit **2**;
`fastlane` without `bundle_id` → exit **2**. Service-level failures (bad creds,
app not found, non-hex sha) → error envelope → exit **1**.

**N3 (`--digits` bound).** Reject `--digits` that would exceed 18 chars (max 14
hex); default 7.

**N4 (`$GITHUB_SHA` hygiene).** Read it at call time (not import), `.strip()` it,
reject a `0x` prefix; non-hex → typed error.

## 7. Code-review resolutions (adversarial review, pre-commit)

**S1 (SHOULD-FIX — service raised instead of returning an envelope).** `int(floor)`
sat outside the try/except and the commit branch only caught `ValueError`, so an
MCP/library caller passing `floor`/`digits` as a JSON string or float escaped the
"never raises" contract (`ValueError`/`TypeError`). **Fixed:** `build_number`
coerces `floor`/`digits` to int at the top and returns a `bad_input` envelope on
failure. Tests: `test_fastlane_non_int_floor_is_envelope_not_crash`,
`test_commit_string_digits_coerced`, `test_commit_bad_digits_is_envelope_not_crash`.

**S2 (SHOULD-FIX — silent skip made `monotonic:true` a lie for dotted apps).**
`latest_build_number` skipped dotted/alphanumeric versions silently, so an app
using `1.0.3`-style build numbers got `latest=0` → `build "1"`, `monotonic:true`,
no warning → Apple rejects. **Fixed:** `latest_build_number` now returns
`(best, skipped)`; the fastlane envelope carries a `warning` (and `source.skipped`)
when non-integer versions were ignored, and the CLI prints it to stderr. Empty/
in-flight versions are skipped but not counted (nothing actionable). Tests:
`test_skips_non_integer_versions_and_counts_them`,
`test_fastlane_warns_when_dotted_versions_skipped`.

**N2 (isascii).** `timestamp_build` and `latest_build_number` require
`isascii() and isdigit()` so non-ASCII "digits" can't slip through.

**N3 (pre-existing crash, fixed while adjacent).** `andp --json` / `andp --account x`
with no command hit `args[0]` IndexError; `main()` now returns usage/exit 2.

**N1 (declined).** Custom `--format` reports `monotonic:false` (over-warn) rather
than the design's `"assumed"` — the safe direction; kept as a bool for a clean
envelope. All 373 tests green.
