"""devicectl — physical device, best effort.

Pairing, trust and provisioning stay the user's responsibility: a typed failure
is returned rather than a workaround attempted. Guessing here would produce
half-installed apps and a message that points nowhere.
"""
from ..errors import XcodeError
from .runner import _capture


def install(udid, app, run_process=None):
    # Captured, not inherited: devicectl chatter on stdout would land ahead of
    # the JSON envelope and make it unparsable.
    code, _ = _capture(["xcrun", "devicectl", "device", "install", "app",
                        "--device", udid, app], None, run_process)
    if code != 0:
        raise XcodeError(
            "Install refused on device %s." % udid,
            code="device_install_failed",
            remediation=("Check the device is paired, unlocked, and that the "
                         "provisioning profile covers its identifier."),
            context={"udid": udid, "app": app})


def launch(udid, bundle, run_process=None):
    code, _ = _capture(["xcrun", "devicectl", "device", "process", "launch",
                        "--device", udid, bundle], None, run_process)
    if code != 0:
        raise XcodeError(
            "Launching %s refused on device %s." % (bundle, udid),
            code="device_not_found",
            remediation="xcrun devicectl list devices",
            context={"udid": udid, "bundle_id": bundle})
