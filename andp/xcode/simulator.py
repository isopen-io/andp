"""simctl — find, boot, install, launch.

Booting is the only retryable operation in this package: simctl fails
transiently under load, which infrastructure/simulator-manager.sh already
handles by retrying three times.
"""
import json
import os
import plistlib

from ..errors import XcodeError
from . import destination as dest
from .runner import _capture
from .runner import run_process as _default_launcher

# simctl calls the visionOS runtime "xrOS", not "visionOS".
RUNTIME_TOKENS = {"iOS": "iOS", "iPadOS": "iOS", "watchOS": "watchOS",
                  "tvOS": "tvOS", "visionOS": "xrOS"}


def _list_devices(launcher=None):
    code, payload = _capture(
        ["xcrun", "simctl", "list", "devices", "available", "-j"], None, launcher)
    if code != 0:
        return {}
    try:
        return json.loads(payload).get("devices") or {}
    except (ValueError, AttributeError):
        return {}


def _candidates(target, launcher):
    token = RUNTIME_TOKENS.get(target.platform, target.platform)
    found = []
    for runtime, devices in _list_devices(launcher).items():
        if token not in runtime:
            continue
        for device in devices:
            if device.get("isAvailable", True):
                found.append(device)
    return found


def find(target, run_process=None):
    """The target's simulator.

    Without a name — `destination: generic`, the default — pick the one already
    booted, else the first available. That is what Xcode does, and it is what
    makes `andp run` work on an auto-detected project. The choice is not hidden:
    the caller puts it in the envelope.
    """
    candidates = _candidates(target, run_process)

    if dest.is_simulator(target):
        for device in candidates:
            if device.get("name") == target.destination:
                return device
        raise XcodeError(
            "No available simulator named `%s`." % target.destination,
            code="simulator_not_found",
            remediation="xcrun simctl list devices available",
            context={"target": target.name, "requested": target.destination,
                     "available": [d.get("name") for d in candidates]})

    for device in candidates:
        if device.get("state") == "Booted":
            return device
    if candidates:
        return candidates[0]
    raise XcodeError(
        "No %s simulator available." % target.platform,
        code="simulator_not_found",
        remediation="Install a %s runtime from Xcode." % target.platform,
        context={"target": target.name, "platform": target.platform})


def boot(udid, run_process=None):
    """Boot and wait.

    `simctl boot` fails on an already-booted device, so its exit code is not
    the signal — bootstatus is what decides.
    """
    launcher = run_process or _default_launcher
    launcher(["xcrun", "simctl", "boot", udid])
    if launcher(["xcrun", "simctl", "bootstatus", udid]) != 0:
        raise XcodeError(
            "Simulator %s did not boot." % udid,
            code="simulator_boot_failed", retryable=True,
            remediation="Retry; simctl fails transiently under load.",
            context={"udid": udid})


def install(udid, app, run_process=None):
    launcher = run_process or _default_launcher
    if launcher(["xcrun", "simctl", "install", udid, app]) != 0:
        raise XcodeError(
            "Install refused on %s." % udid,
            code="install_failed",
            remediation="Check the .app matches the simulator's platform.",
            context={"udid": udid, "app": app})


def launch(udid, bundle, run_process=None):
    launcher = run_process or _default_launcher
    if launcher(["xcrun", "simctl", "launch", udid, bundle]) != 0:
        raise XcodeError(
            "Launching %s refused on %s." % (bundle, udid),
            code="launch_failed",
            remediation="Check the bundle identifier, and that the app installed.",
            context={"udid": udid, "bundle_id": bundle})


def stream_logs(udid, bundle, run_process=None):
    """Follow the app's logs until interrupted."""
    launcher = run_process or _default_launcher
    return launcher(["xcrun", "simctl", "spawn", udid, "log", "stream",
                     "--predicate", 'subsystem == "%s"' % bundle])


def bundle_id(app):
    path = os.path.join(app, "Info.plist")
    if not os.path.exists(path):
        raise XcodeError(
            "No Info.plist in %s." % app,
            code="app_not_found",
            remediation="Build the target before running it.",
            context={"app": app})
    with open(path, "rb") as handle:
        load = getattr(plistlib, "load", None) or plistlib.readPlist
        data = load(handle)
    identifier = data.get("CFBundleIdentifier")
    if not identifier:
        raise XcodeError(
            "CFBundleIdentifier missing from %s." % path,
            code="app_not_found",
            remediation="Check the target's Info.plist in project.yml.",
            context={"app": app})
    return identifier
