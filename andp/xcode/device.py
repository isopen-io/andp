"""devicectl — physical device, best effort.

Pairing, trust and provisioning stay the user's responsibility: a typed failure
is returned rather than a workaround attempted. Guessing here would produce
half-installed apps and a message that points nowhere.
"""
from ..errors import XcodeError
from .runner import run_process as _default_launcher


def install(udid, app, run_process=None):
    launcher = run_process or _default_launcher
    if launcher(["xcrun", "devicectl", "device", "install", "app",
                 "--device", udid, app]) != 0:
        raise XcodeError(
            "Install refused on device %s." % udid,
            code="device_install_failed",
            remediation=("Check the device is paired, unlocked, and that the "
                         "provisioning profile covers its identifier."),
            context={"udid": udid, "app": app})


def launch(udid, bundle, run_process=None):
    launcher = run_process or _default_launcher
    if launcher(["xcrun", "devicectl", "device", "process", "launch",
                 "--device", udid, bundle]) != 0:
        raise XcodeError(
            "Launching %s refused on device %s." % (bundle, udid),
            code="device_not_found",
            remediation="xcrun devicectl list devices",
            context={"udid": udid, "bundle_id": bundle})
