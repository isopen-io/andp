# Build number — `andp build-number`

ANDP computes the next iOS build number (`CFBundleVersion`) so a release pipeline
no longer needs fastlane just for it. It **prints only the number on stdout**, so
it drops straight into a build step (apply it to the Xcode project *before*
archiving — a signed IPA can't be re-versioned):

```bash
agvtool new-version -all "$(andp build-number me.your.app --strategy fastlane --floor 1254)"
# or
xcodebuild ... CURRENT_PROJECT_VERSION="$(andp build-number --strategy timestamp)"
```

Add `--json` for the full envelope (`build_number`, `strategy`, `monotonic`,
`source`). Exit 0 on success, 1 on an error, 2 on usage.

## Strategies

| `--strategy` | Value | Monotonic? | Credentials? |
|---|---|---|---|
| **fastlane** | `max(--floor, latest ASC build) + 1` | ✅ yes | ✅ needs creds |
| **timestamp** | `utcnow().strftime(--format)` (default `%Y%m%d%H%M`) | ✅ yes | ❌ none |
| **commit** | `int(git short sha, 16)` | ❌ **no** | ❌ none |

### fastlane — sequential, App Store-safe
`max(--floor, latest ASC build) + 1`. `--floor` is the local project's current
build number (so you never go below it while ASC is still processing an upload) —
the same guard as fastlane's `max(get_build_number, latest_testflight_build_number)+1`.
The ASC lookup takes a **full, numeric** global max across all builds (it never
trusts the API's lexicographic sort, where `"9"` outranks `"1000"`). A global max
is ≥ any per-version max, so `+1` is always accepted.
> If the app uses **dotted** build numbers (`1.0.3`), those are ignored and the
> command warns (to stderr) that the number may be too low — pass `--floor`.

### timestamp — no ASC query
`utcnow().strftime(fmt)`, default minute resolution (`%Y%m%d%H%M` → `202607221830`).
Monotonic (time only moves forward). Two builds in the **same minute** collide —
use `--format %Y%m%d%H%M%S` if you release very frequently. Valid up to 18 digits
(Apple's `CFBundleVersion` limit).

### commit — unique, traceable, NOT monotonic
`int(sha[:digits], 16)` from `--sha` (default `$GITHUB_SHA`); `--digits` (default
7). Great for ad-hoc/internal builds and traceability, but a hash does **not**
increase with history: `monotonic:false`, and a stderr warning fires. **Do not**
use it for sequential App Store builds within a marketing version (Apple requires
each build strictly higher than the last).

## In CI

`timestamp`/`commit` need **no credentials and no `secrets.yml`** — they run in a
bare checkout:

```yaml
- run: |
    BUILD=$(andp build-number --strategy timestamp)
    (cd apps/ios && agvtool new-version -all "$BUILD")
```

`fastlane` needs the ASC credentials (a `secrets.yml`, or ANDP's usual env-based
setup). Keep the **same strategy within a marketing version** — the scales differ
wildly (commit ~1e8, fastlane ~1e3, timestamp ~2e11), so switching mid-version
can produce a *lower* number and Apple will reject it.
