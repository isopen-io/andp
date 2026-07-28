"""CLI surface for build / run / test / targets: parsing, aggregation, display.

The envelope is the contract with agents: one entry per target, in the order
asked for, and an `ok` that is the conjunction of them all.
"""
from __future__ import print_function

import json
import sys

from ..errors import XcodeError
from . import destination as dest
from . import device, runner, simulator, targets

# Flags taking a value, mapped to the Target field they override.
VALUE_FLAGS = {"--scheme": "scheme", "--configuration": "configuration",
               "--platform": "platform", "--destination": "destination",
               "--os": "os"}
BOOL_FLAGS = ("--all", "--archive", "--no-build", "--logs")

DRY_RUN_BANNER = ("xcodebuild introuvable — DRY-RUN : rien n'a été compilé.\n"
                  "   → installez Xcode, ou lisez `dry_run` dans l'enveloppe JSON.")


def parse(args):
    """(names, flags) from a raw argument list.

    A value flag with nothing after it is a usage error, not a silent None:
    `andp build --scheme` would otherwise build the wrong thing.
    """
    names, flags = [], {"overrides": {}}
    for flag in BOOL_FLAGS:
        flags[flag.lstrip("-").replace("-", "_")] = False

    index = 0
    args = list(args)
    while index < len(args):
        token = args[index]
        if token in VALUE_FLAGS:
            if index + 1 >= len(args):
                raise XcodeError(
                    "Flag %s expects a value." % token,
                    code="bad_usage",
                    remediation="Example: %s <value>" % token,
                    context={"flag": token})
            flags["overrides"][VALUE_FLAGS[token]] = args[index + 1]
            index += 2
            continue
        if token in BOOL_FLAGS:
            flags[token.lstrip("-").replace("-", "_")] = True
            index += 1
            continue
        if token.startswith("-"):
            raise XcodeError(
                "Unknown flag: %s." % token,
                code="bad_usage",
                remediation="Known flags: %s." % ", ".join(
                    sorted(list(VALUE_FLAGS) + list(BOOL_FLAGS))),
                context={"flag": token})
        names.append(token)
        index += 1
    return names, flags


def _select(names, flags, project_root):
    """The targets to act on, honouring --all and the override flags."""
    overrides = flags["overrides"]
    if flags["all"]:
        if names:
            raise XcodeError(
                "--all and a named target are mutually exclusive.",
                code="bad_usage",
                remediation="Drop --all, or drop the target names.",
                context={"names": names})
        return targets.resolve_all(project_root, overrides=overrides)
    if not names:
        return [targets.resolve(None, project_root, overrides=overrides)]
    return [targets.resolve(name, project_root, overrides=overrides)
            for name in names]


def _entry(result):
    entry = {"target": result.target, "ok": result.ok,
             "duration": result.duration, "destination": result.destination,
             "log": result.log_path}
    if result.error is not None:
        entry["error"] = result.error.to_dict()
    return entry


def _dry_entry(target):
    return {"target": target.name, "ok": True, "duration": 0.0,
            "destination": dest.to_argument(target), "log": None,
            "skipped": "xcodebuild not available"}


def run_many(selected, action, project_dir, project_root, archive=False,
             run_process=None):
    """Run `action` over every target, sequentially, never stopping on failure.

    A broken visionOS target must not hide the state of the other four.
    """
    dry_run = not runner.xcodebuild_available()
    results = []
    for target in selected:
        if dry_run:
            results.append(_dry_entry(target))
            continue
        if action == "test":
            result = runner.test(target, project_dir, project_root,
                                 run_process=run_process)
        else:
            result = runner.build(target, project_dir, project_root,
                                  archive=archive, run_process=run_process)
        results.append(_entry(result))
    return {"command": action, "ok": all(r["ok"] for r in results),
            "dry_run": dry_run, "results": results}


def build_targets(selected, project_dir, project_root, archive=False,
                  run_process=None):
    return run_many(selected, "build", project_dir, project_root,
                    archive=archive, run_process=run_process)


def test_targets(selected, project_dir, project_root, run_process=None):
    return run_many(selected, "test", project_dir, project_root,
                    run_process=run_process)


def _print_envelope(envelope, json_mode):
    if json_mode:
        print(json.dumps(envelope))
        return 0 if envelope["ok"] else 1
    if envelope["dry_run"]:
        print(DRY_RUN_BANNER, file=sys.stderr)
    for entry in envelope["results"]:
        mark = "✅" if entry["ok"] else "❌"
        print("%s  %-16s %6.1fs  %s"
              % (mark, entry["target"], entry["duration"], entry["destination"]))
        if not entry["ok"]:
            error = entry["error"]
            print("   %s" % error["message"], file=sys.stderr)
            for line in error.get("context", {}).get("errors", []):
                print("     %s" % line, file=sys.stderr)
            print("   → %s" % error["remediation"], file=sys.stderr)
    return 0 if envelope["ok"] else 1


def cmd_build(args, json_mode=False, project_root=".", run_process=None):
    names, flags = parse(args)
    selected = _select(names, flags, project_root)
    envelope = build_targets(selected, targets.project_dir(project_root),
                             project_root, archive=flags["archive"],
                             run_process=run_process)
    return _print_envelope(envelope, json_mode)


def cmd_test(args, json_mode=False, project_root=".", run_process=None):
    names, flags = parse(args)
    selected = _select(names, flags, project_root)
    envelope = test_targets(selected, targets.project_dir(project_root),
                            project_root, run_process=run_process)
    return _print_envelope(envelope, json_mode)


def cmd_targets(args, json_mode=False, project_root=".", run_process=None):
    """List resolved targets — so an agent discovers what it can build."""
    parse(args)
    resolved = targets.resolve_all(project_root)
    payload = {"command": "targets", "ok": True, "targets": [
        {"name": t.name, "scheme": t.scheme, "platform": t.platform,
         "destination": t.destination, "configuration": t.configuration,
         "os": t.os, "destination_argument": dest.to_argument(t)}
        for t in resolved]}
    if json_mode:
        print(json.dumps(payload))
        return 0
    for entry in payload["targets"]:
        print("%-16s %-10s %-10s %s" % (entry["name"], entry["scheme"],
                                        entry["configuration"],
                                        entry["destination_argument"]))
    return 0


def run_target(target, project_dir, project_root, build_first=True,
               follow_logs=False, run_process=None):
    """Build, install and launch one target. Returns the envelope."""
    dry_run = not runner.xcodebuild_available()
    if dry_run:
        return {"command": "run", "ok": True, "dry_run": True,
                "results": [_dry_entry(target)]}

    if build_first:
        result = runner.build(target, project_dir, project_root,
                              run_process=run_process)
        if not result.ok:
            # Installing a binary that failed to build would launch a stale one.
            return {"command": "run", "ok": False, "dry_run": False,
                    "results": [_entry(result)]}

    app = runner.app_path(target, project_dir, run_process=run_process)
    entry = {"target": target.name, "ok": True, "duration": 0.0,
             "destination": dest.to_argument(target), "log": None,
             "app": app}

    if target.platform == "macOS" and not dest.is_device(target):
        launcher = run_process or runner.run_process
        launcher([app])
        return {"command": "run", "ok": True, "dry_run": False,
                "results": [entry]}

    bundle = simulator.bundle_id(app)
    entry["bundle_id"] = bundle

    if dest.is_device(target):
        udid = target.destination[len(dest.DEVICE_ID_PREFIX):]
        device.install(udid, app, run_process=run_process)
        device.launch(udid, bundle, run_process=run_process)
        entry["udid"] = udid
        return {"command": "run", "ok": True, "dry_run": False,
                "results": [entry]}

    found = simulator.find(target, run_process=run_process)
    udid = found["udid"]
    entry["udid"] = udid
    entry["simulator"] = found.get("name")
    if found.get("state") != "Booted":
        simulator.boot(udid, run_process=run_process)
    simulator.install(udid, app, run_process=run_process)
    simulator.launch(udid, bundle, run_process=run_process)
    if follow_logs:
        simulator.stream_logs(udid, bundle, run_process=run_process)
    return {"command": "run", "ok": True, "dry_run": False, "results": [entry]}


def cmd_run(args, json_mode=False, project_root=".", run_process=None):
    names, flags = parse(args)
    if len(names) > 1:
        raise XcodeError(
            "`run` takes a single target (got: %s)." % ", ".join(names),
            code="bad_usage",
            remediation="Launching several apps at once has no meaning.",
            context={"names": names})
    selected = _select(names, flags, project_root)
    envelope = run_target(selected[0], targets.project_dir(project_root),
                          project_root, build_first=not flags["no_build"],
                          follow_logs=flags["logs"], run_process=run_process)
    if json_mode:
        print(json.dumps(envelope))
        return 0 if envelope["ok"] else 1
    if envelope["dry_run"]:
        print(DRY_RUN_BANNER, file=sys.stderr)
    entry = envelope["results"][0]
    if envelope["ok"]:
        print("✅  %s lancé sur %s"
              % (entry["target"], entry.get("simulator") or entry["destination"]))
        return 0
    print("   %s" % entry["error"]["message"], file=sys.stderr)
    return 1
