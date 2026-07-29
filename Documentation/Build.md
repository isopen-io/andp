# Building, running and testing

ANDP builds what your project declares, on every platform it declares. The
matrix lives in `andp.yml`, not in a script.

```
andp build [targets...] [--all] [--archive]
andp run <target> [--no-build] [--logs]
andp test [targets...] [--all]
andp targets
```

None of these need App Store Connect credentials — a build does not talk to
Apple.

## Declaring targets

In `andp.yml`, at the root of your project:

```yaml
targets:
  defaults:
    scheme: Meeshy
    configuration: Debug
  dev-ios:
    platform: iOS
    destination: "iPhone 15"
  dev-vision:
    platform: visionOS
    destination: "Apple Vision Pro"
  watch:
    platform: watchOS
    destination: "Apple Watch Series 9 (45mm)"
  prod:
    platform: iOS
    destination: generic
    configuration: Release
```

`defaults` supplies the base; each named target overrides it field by field. A
target declaring only `platform: visionOS` inherits everything else. `defaults`
is never a target itself.

### Fields

| Field | Values | Default |
|---|---|---|
| `scheme` | an Xcode scheme name | inherited from `defaults` |
| `platform` | `iOS`, `iPadOS`, `watchOS`, `tvOS`, `macOS`, `visionOS` | `iOS` |
| `destination` | `generic`, `id=<UDID>`, or a simulator name | `generic` |
| `configuration` | `Debug`, `Release`, or any project configuration | `Debug` |
| `os` | a runtime version, e.g. `17.0` | latest available |

An unknown field or platform is an error, not a warning: a misspelled
`platfrom: iOS` would otherwise silently build for the default platform.

`iPadOS` is accepted and normalised to `iOS` — xcodebuild has no such platform
name; the distinction comes from the simulator you name.

### Destinations

| Form | Becomes | Use for |
|---|---|---|
| `generic` | `generic/platform=iOS` | archiving, compiling without a device |
| `"iPhone 15"` | `platform=iOS Simulator,name=iPhone 15` | a named simulator |
| `id=00008030-…` | `platform=iOS,id=00008030-…` | a physical device |

macOS has no simulator: a named destination there is refused.

### Where the Xcode project lives

Resolved in this order:

1. `$ANDP_APP_DIR`
2. `project.dir` in `andp.yml`
3. the current directory

```yaml
project:
  dir: examples/meeshy
```

With no `.xcodeproj` or `.xcworkspace` at the resolved directory, the command
fails once with `no_project` rather than letting every target rediscover the
same absence.

## Without a `targets:` block

ANDP asks the project. One application scheme becomes an implicit target named
`default`. Several schemes raise `ambiguous_scheme`, whose remediation hands
back the YAML to paste.

Unless you name one: `--scheme` answers the very question the project is being
asked, so an explicit scheme is honoured instead of the refusal. That is what
makes `./build.sh MyScheme Release iphoneos` work on a multi-scheme workspace
with no `andp.yml` — the case existing CI callers are in.

## Overrides

`--scheme`, `--configuration`, `--platform`, `--destination` and `--os` override
the resolved target. Priority, highest first:

1. the command-line flag
2. the named target in `andp.yml`
3. `defaults` in `andp.yml`
4. the field's default

## `andp build`

Targets are built **sequentially**, and a failure never stops the run — a broken
visionOS target must not hide the state of the other four. The exit code is `0`
only when every target succeeded.

`--archive` chains `archive` and `-exportArchive`, producing
`.andp/build/<target>.xcarchive` and `.andp/build/exported/` — the path `sign.sh`
already reads. It requires `destination: generic`; archiving for a simulator
produces nothing installable.

Each run writes its full xcodebuild output to
`.andp/build/logs/<target>-<action>.log`.

## `andp run`

For a simulator destination: boot (skipped if already booted) → build → locate
the `.app` → install → launch. With `--logs`, the app's log stream follows until
interrupted. `--no-build` launches what is already built.

With `destination: generic` — the default — `run` picks a simulator: the one
already booted for that platform, else the first available. That is what Xcode
does, and it is what makes `andp run` work on an auto-detected project. The
choice is reported in the envelope, never hidden.

For `id=<UDID>`, ANDP goes through `xcrun devicectl`, best effort: pairing,
trust and provisioning stay yours, and a failure is reported typed rather than
worked around.

`run` takes a single target.

## `andp test`

Runs the suite per target and writes `.andp/build/<target>.xcresult`. The path is
in the envelope, which is how `test.sh` feeds `test-report.sh`. Report
generation and visual-regression checks stay in shell.

## `andp targets`

Lists resolved targets with their effective fields after inheritance, and the
`-destination` argument each one produces. An agent discovers what it can build
without reading `andp.yml` or knowing the inheritance rules.

## DRY-RUN

When `xcodebuild` is not on the `PATH`, nothing is compiled and the envelope says
so:

```json
{"command": "build", "ok": true, "dry_run": true, "results": [...]}
```

A banner also goes to stderr in human mode. This keeps Linux CI green while
never claiming a build happened. DRY-RUN triggers on one condition only —
`xcodebuild` absent. If it exists and fails, that is `build_failed`, plainly.

## The JSON envelope

```json
{
  "command": "build",
  "ok": false,
  "dry_run": false,
  "results": [
    {"target": "dev-ios", "ok": true, "duration": 42.1,
     "destination": "platform=iOS Simulator,name=iPhone 15",
     "log": ".andp/build/logs/dev-ios-build.log"},
    {"target": "dev-vision", "ok": false, "duration": 8.3,
     "destination": "platform=visionOS Simulator,name=Apple Vision Pro",
     "log": ".andp/build/logs/dev-vision-build.log",
     "error": {"code": "build_failed", "retryable": false,
               "message": "xcodebuild exited with 65.",
               "remediation": "Read the full log: …",
               "context": {"errors": ["App.swift:12: error: …"]}}}
  ]
}
```

`ok` is the conjunction of every target's `ok`. Errors raised *before* any
execution — `target_not_found`, `no_project`, `ambiguous_scheme` — have no
`results`: they carry a single `error` at the root.

The `context.errors` field holds the last ten lines containing `error:` from the
build log. That is what separates "the build failed" from why.

## Error codes

| Code | Retryable | Meaning |
|---|---|---|
| `target_not_found` | no | no such target in `andp.yml` |
| `ambiguous_target` | no | several targets, none named, no `--all` |
| `ambiguous_scheme` | no | several schemes, no `targets:` block |
| `bad_target_config` | no | unknown field, platform, or invalid combination |
| `bad_usage` | no | malformed command line |
| `no_project` | no | no `.xcodeproj` or `.xcworkspace` found |
| `build_failed` | no | xcodebuild returned non-zero |
| `test_failed` | no | the test suite returned non-zero |
| `export_failed` | no | `-exportArchive` returned non-zero |
| `app_not_found` | no | the built product could not be located |
| `simulator_not_found` | no | no matching available simulator |
| `simulator_boot_failed` | **yes** | simctl fails transiently under load |
| `install_failed` / `launch_failed` | no | simctl refused the app |
| `device_install_failed` / `device_not_found` | no | devicectl refused |

`simulator_boot_failed` is the only retryable code here: everything else stays
broken until something changes, and retrying only wastes minutes.

## Shell scripts

`build.sh`, `build-matrix.sh` and `test.sh` are thin wrappers around these
commands, keeping their positional signatures for existing CI callers.

| Script | Runs |
|---|---|
| `./build.sh SCHEME CONFIG SDK` | `andp build --scheme … --configuration … --destination …` |
| `./build-matrix.sh` | `andp build --all` |
| `./test.sh SCHEME DEVICE OS` | `andp test --scheme … --destination … --os …` |

Adding a platform to the matrix is now an `andp.yml` change, not a script edit.

## See also

- [Configuration](Configuration.md) — the `.andp/` namespace and credential
  resolution
- [Migration](Migration.md) — coming from Fastlane or Tuist
