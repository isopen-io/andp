# Validation — finding out before Apple tells you

Every failed delivery is the same story told at a different distance: something
was wrong, and you learned about it later than you could have. ANDP has four
validation layers, each catching a different class of problem at the earliest
moment it is *knowable*.

| Layer | Question | Needs | Cost | Command |
|---|---|---|---|---|
| **1. Credentials** | Can I publish at all? | credentials | 2 API calls | `andp verify [bundle]` |
| **2. Package** | Will Apple silently drop this binary? | the `.ipa` | zero, offline | automatic in `release start` |
| **3. Metadata** | Will Apple reject this submission? | credentials + a version | ~10 API calls | `andp precheck <bundle> <ver>` |
| **4. CI gate** | Is this branch shippable? | credentials | 1 + 3 | `andp readiness …` |

They are ordered by how early they can run, not by importance. Layer 2 needs no
network and no account: it is the cheapest check in the tool and it catches the
most expensive failure.

---

## 1. The credentials gate — `verify`

**The failure it prevents:** starting a 30-minute build, an archive, and an
upload on credentials that were never going to work.

`verify` is deliberately the one command that **fails in DRY-RUN**. Every other
command degrades gracefully to a plan when unconfigured; `verify`'s entire job
is to tell the truth about whether publishing can happen, so degrading would
defeat it.

```console
$ andp verify me.your.app
ASC publish preflight (account 'primary'):
  ✅ credentials — key_id ABCDE12345, issuer_id set, private key present
  ✅ JWT signed (ES256)
  ✅ API authentication accepted
  ✅ app found: YourApp (me.your.app) — id 6786703445
PREFLIGHT PASSED — the tool can publish to App Store Connect.
```

Four checks, in dependency order, stopping at the first failure:

1. **credentials** — field-by-field completeness, with placeholder detection.
   A field left as `YOUR_KEY_ID_HERE` is *missing*, not present.
2. **jwt** — the private key actually signs an ES256 token. Catches a truncated
   or line-mangled `.p8` before any network call.
3. **api_auth** — Apple accepts the token (`GET /v1/apps`). Catches a wrong
   `issuer_id`, a revoked key, or a key whose role is too weak.
4. **app_record** — the bundle id exists on *this* account. Only run when you
   pass a bundle id.

Failure names the exact blocker:

```json
{"command":"verify","ok":false,
 "checks":[{"name":"credentials","ok":false,"missing":["issuer_id"]}]}
```

Exit 0 when publishing is possible, 1 when it is not.

> **What it cannot tell you:** anything about your binary or your metadata. A
> green `verify` means the *door is open*, not that what you are carrying will
> get through it.

---

## 2. The package gate

**The failure it prevents:** an upload that reports success into total silence.

This is the nastiest failure mode in App Store delivery. You upload. `altool`
says `No errors uploading`. And then nothing: the build never appears in App
Store Connect, TestFlight shows nothing, and the only trace is an email that may
or may not arrive. There is no build to inspect, because Apple rejected the
package *during processing*, asynchronously, after acknowledging the upload.

Since the fault is readable from the `.ipa` itself, ANDP reads it — with
`zipfile` and `plistlib`, no network, no account, before a single byte moves:

```console
$ andp release start build/App.ipa --ship --json
{"command":"release_start","ok":false,
 "error":{"code":"bundle_invalid","retryable":false,
   "message":"NSExtensionActivationRule sits directly under NSExtension in bundle
              MeeshyShareExtension.appex: it belongs inside NSExtensionAttributes…",
   "remediation":"Fix the embedded extension's Info.plist and re-export the IPA.
                  Uploading as-is succeeds, then the build silently never appears."}}
```

### The rules

| id | Fault |
|---|---|
| `extension_activation_rule_misplaced` | `NSExtensionActivationRule` sits directly under `NSExtension` instead of inside `NSExtensionAttributes` |
| `extension_attributes_missing` | an extension point that requires `NSExtensionAttributes` has none |

Both are read from every embedded `.appex`'s `Info.plist`.

### Two deliberate design choices

**The extension-point list is an allow-list, not a heuristic.** Only
`com.apple.share-services`, `com.apple.services` and `com.apple.ui-services` are
checked for required attributes. An extension point that is not on the list is
left alone rather than guessed at — a notification extension legitimately has no
activation rule, and a false positive here would block a real release over a
rule ANDP invented. The list grows when a real rejection proves a new entry,
never before.

**An unreadable package yields no findings.** If the `.ipa` cannot be parsed,
validation returns nothing and the release proceeds. Validation must never be
the thing that breaks a delivery.

### How it was verified

Against the two real binaries from the incident that motivated it: the build
Apple silently rejected is **refused**, naming the offending `.appex`; the build
Apple had accepted **passes**. Exact detection, zero false positive.

> **What it cannot tell you:** anything Apple checks that is not readable from
> the archive — entitlements against your provisioning profile, private API
> usage, asset catalog validity. This layer covers faults that are *statically
> visible and reliably fatal*, which is a small set on purpose.

---

## 3. The metadata gate — `precheck`

**The failure it prevents:** an App Review rejection for something you could
have read off the API five seconds earlier.

`precheck` is read-only. It never mutates anything, so it is safe to run in a
loop, in CI, on every PR.

```console
$ andp precheck me.your.app 1.2.0
  ❌ screenshots: [en-US] has no screenshots.
  ⚠️  keywords: [en-US] keywords are empty.
  ⚠️  pricing: No price schedule set (Apple requires a price or Free selection…).
PRECHECK FAILED — 1 errors, 2 warnings
```

**Errors** (block submission) are strictly the hard, reliably-detectable
requirements:

| id | Meaning |
|---|---|
| `version_editable` | the version is not in an editable/submittable state |
| `build_attached` | no build is attached to the version |
| `localizations` | the version has no localizations at all |
| `description` | a locale's description is empty |
| `screenshots` | a locale has zero screenshots (counted, not just "a set exists") |

**Warnings** (advisory, never blocking) cover the rest: empty `whatsNew`,
keywords, support URL, unset pricing / availability / age rating, and content
smells like a mention of Android or leftover `lorem ipsum` in reviewer-visible
text — both common, avoidable rejection causes.

The store-configuration warnings are **best-effort by construction**: each read
is individually guarded, so a failing advisory lookup skips that one warning
instead of turning the whole precheck into an error. The hard checks stand
regardless.

> **What it cannot tell you** — and the report says so itself, in its `note`
> field: age rating validity, app name/subtitle rules, pricing correctness, and
> per-device screenshot dimensions are not checked. `ok: true` is not a
> guarantee of acceptance. Apple remains the final authority, and it validates
> synchronously at submit — that 409's detail is surfaced verbatim in
> `error.message`.

Inside a `--ship` release, precheck runs automatically as the `prechecked`
state. A failing report sets `needs_precheck_fix` and **parks** the release
there — it does not fail it. Fix the content, poll again. Skip the stage
entirely with `--no-precheck` if you have your own gate.

---

## 4. The CI gate — `readiness`

Layers 1 and 3 answer developer questions. `readiness` answers a *pipeline*
question, with a shape a pipeline can act on.

```bash
andp readiness testflight me.your.app
andp readiness appstore  me.your.app 1.2.0
```

It normalizes both underlying result shapes into one **verdict** with a
tri-state status — and the third state is the whole point:

| Status | Meaning | Exit |
|---|---|---|
| `ready` | evaluated, zero blockers | 0 |
| `not_ready` | evaluated, a genuine fixable blocker | 1 |
| `unverified` | **could not evaluate** | 3 |

`unverified` covers: no or placeholder credentials, malformed config, or a
transient API error (rate limit, 5xx, network). Without it, a fork PR with no
secrets would report a green "ready" — a gate that lies in exactly the situation
it exists for. Retryable blockers are classified `unverified` too: a 429 is not
evidence that your app is unshippable.

Two flags let a pipeline choose its own strictness:

- `--soft` — downgrade `not_ready` to exit 0 (report, don't block)
- `--allow-unverified` — downgrade `unverified` to exit 0 (fork PRs pass)

### GitHub-native output

When `$GITHUB_STEP_SUMMARY`, `$GITHUB_OUTPUT` or `$GITHUB_ACTIONS` are present,
the same verdict is additionally rendered as a job-summary table, step outputs
(`ready`, `status`, `reason`, `blockers`, `blockers_count`, …) and
`::error::`/`::warning::` annotations. All three are side-effects only — the
command behaves identically without them, so local runs are not a different
code path.

Step outputs are written with a per-value random heredoc delimiter, because an
API-error `reason` can contain newlines and the `name=value` form corrupts on
(or is spoofable by) those.

Full CI wiring, actions and reusable workflows:
[PublishReadiness.md](PublishReadiness.md).

---

## Putting them in order

A pipeline that fails as early and as cheaply as possible:

```bash
andp verify me.your.app                     # 1. can I publish?           (2 calls)
andp build prod --archive                   #    … only now, build
andp release start build/exported/App.ipa \ # 2. package gate runs here, offline
     --ship --metadata ./metadata --json
andp release poll <id> --json               # 3. precheck runs inside the machine
```

and on every pull request, before any of that:

```yaml
- uses: isopen-io/andp/.github/actions/testflight-readiness@v1
  with: { key-id: …, issuer-id: …, private-key: …, bundle-id: me.your.app }
```

---

## See also

- [Release.md](Release.md) — the machine these gates sit inside
- [PublishReadiness.md](PublishReadiness.md) — the CI actions and workflows
- [CLI.md](CLI.md) — exact flags and exit codes
- [ASC-API.md](ASC-API.md) — what the API layer can and cannot do
