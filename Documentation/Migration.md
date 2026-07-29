# Migrating to ANDP

ANDP replaces Fastlane and Tuist with Apple-native tooling plus the official App
Store Connect API. No Ruby, no Gemfile, no plugin system.

## 1. From Fastlane

### What maps to what

| Fastlane | ANDP | Notes |
|---|---|---|
| `Fastfile` lanes | `andp` subcommands + your CI YAML | there is no lane DSL; the pipeline is your CI file |
| `Appfile` | `.andp/secrets.yml` + `andp.yml` | credentials vs. declarative config, split deliberately |
| `gym` / `build_app` | `andp build <target> --archive` | archive + export in one step |
| `scan` / `run_tests` | `andp test [--all]` | `.xcresult` path in the envelope |
| `pilot` / `upload_to_testflight` | `andp release <ipa> --group "Beta"` | one blocking call, or the resumable machine |
| `deliver` / `upload_to_app_store` | `andp publish` + `andp store apply` + `andp release start --ship` | split: media/text, store settings, submission |
| `precheck` | `andp precheck <bundle> <version>` | read-only, same intent |
| `match` | `andp` provisioning (`asc/provisioning.py`) | by API; no shared git repo of certificates |
| `sigh` | provisioning by API | profiles are created, not downloaded from a cache |
| `produce` | — | `POST /v1/apps` does not exist; create the record once in the UI |
| `latest_testflight_build_number` + increment | `andp build-number <bundle> --strategy max-build` | prints only the number on stdout |
| `deliver --skip_binary_upload` for metadata | `andp publish <bundle> <ver> <dir>` | idempotent per file |
| `Deliverfile` screenshots tree | the same folder convention | see [Metadata.md](Metadata.md) |

### Steps

1. **Keep your metadata tree.** ANDP reads the `deliver`-style layout —
   `<locale>/description.txt`, `<locale>/screenshots/<DISPLAY_TYPE>/*.png`. Point
   `andp publish` at it and nothing needs moving. One difference: device folders
   use Apple's raw display types (`APP_IPHONE_67`), with no aliasing, so what you
   name is what Apple gets.

2. **Move credentials.**
   ```bash
   mkdir -p .andp && cp secrets.example.yml .andp/secrets.yml
   ```
   Fill `key_id`, `issuer_id`, `key_content` from the same API key Fastlane used.

3. **Prove it before deleting anything.**
   ```bash
   andp verify me.your.app
   ```
   This is the migration's actual checkpoint. Green means the API path works
   with your key; nothing else needs to be true yet.

4. **Declare targets** in `andp.yml` if you want `andp build`/`test`
   ([Build.md](Build.md)). You can skip this entirely and keep building with
   whatever you have — ANDP reads bundle id, version and build number from the
   IPA itself, so it publishes binaries built anywhere.

5. **Replace the lanes**, one at a time. `bundle exec fastlane beta` becomes
   `andp release build/App.ipa --group Beta`. There is no big-bang cutover:
   upload with ANDP while still building with Fastlane if you like.

6. **Delete** `Fastfile`, `Appfile`, `Deliverfile`, `Matchfile`, `Gemfile`,
   `Gemfile.lock` and `fastlane/` — once step 5 has run green at least once.

### What you gain beyond removing Ruby

- **A resumable release.** `pilot` blocks for the whole processing wait and a
  crash loses it. `andp release start` + `poll` persists after every step.
- **Pre-upload package validation.** A malformed embedded extension is caught
  offline in ~1 s instead of surfacing as an upload that "succeeded" and a build
  that never appears ([Validation.md](Validation.md)).
- **Territory availability**, which `deliver` does not cover
  ([StoreConfig.md](StoreConfig.md)).
- **A typed envelope on every command** — `--json` everywhere, with
  `error.code` / `retryable` / `remediation`.
- **The current API models.** Pricing is `appPriceSchedules` (the tier system is
  gone), availability is `appAvailabilities` v2, age rating is the 2025
  declaration, submission is Review Submissions (`appStoreVersionSubmissions` was
  removed in ASC 4.0).

### What you lose

Be aware before you commit:

- **No lane DSL.** Orchestration lives in your CI file or a shell script. If you
  had complex Ruby in a `Fastfile`, it needs a new home.
- **No plugin ecosystem.** Anything Fastlane did via a community plugin
  (Slack notifications, Crashlytics upload, changelog generation) is yours to
  wire up. ANDP does delivery, not everything around it.
- **`match`'s shared certificate repo has no equivalent.** ANDP creates
  provisioning material through the API rather than syncing an encrypted git
  repo. If your team depends on that workflow specifically, plan for it.

## 2. From Tuist

| Tuist | ANDP |
|---|---|
| `Project.swift` | `project.yml` (XcodeGen) |
| `tuist generate` | `./generate.sh` |
| `tuist build` | `andp build` |
| `tuist test` | `andp test` |
| `tuist cache` | — no equivalent |

1. Translate `Project.swift` into XcodeGen's declarative `project.yml`.
2. Move Tuist-managed dependencies to Swift Package Manager definitions in
   `project.yml`.
3. Declare the build matrix in `andp.yml`'s `targets:` block, then
   `andp targets` to see exactly what resolves.

ANDP has no answer to Tuist's binary caching. If that is the reason you use
Tuist, keep it for building and use ANDP only for publishing — they compose
fine, since ANDP takes an `.ipa` from anywhere.

## 3. Coexistence

Nothing here is all-or-nothing. The clean seam is the `.ipa`: whatever produces
one, ANDP can publish it. The usual order is publish-first (the part that keeps
breaking), then build, then project generation — or never, if your build already
works.

## See also

- [CLI.md](CLI.md) — the full command surface
- [Build.md](Build.md) — the target model, if you adopt `andp build`
- [Metadata.md](Metadata.md) — the folder convention `deliver` users already have
- [StoreConfig.md](StoreConfig.md) — pricing, territories, age rating
