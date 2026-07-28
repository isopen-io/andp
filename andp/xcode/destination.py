"""Target to `-destination` argument. A pure module.

xcodebuild does not know `iPadOS` — that is iOS, the distinction being made by
the simulator's name. The alias is accepted because it is what one naturally
writes.
"""
from ..errors import XcodeError

GENERIC = "generic"
DEVICE_ID_PREFIX = "id="
_ALIASES = {"iPadOS": "iOS"}


def sdk_platform(target):
    """The platform name xcodebuild understands."""
    return _ALIASES.get(target.platform, target.platform)


def is_simulator(target):
    """True when the destination names a simulator."""
    if target.platform == "macOS":
        return False
    return (target.destination != GENERIC
            and not target.destination.startswith(DEVICE_ID_PREFIX))


def is_device(target):
    """True when the destination pins a physical device by UDID."""
    return target.destination.startswith(DEVICE_ID_PREFIX)


def to_argument(target):
    platform = sdk_platform(target)

    if target.destination == GENERIC:
        return "generic/platform=%s" % platform

    if is_device(target):
        return "platform=%s,%s" % (platform, target.destination)

    if target.platform == "macOS":
        # No macOS simulator: translating would produce an argument xcodebuild
        # rejects later, with a message that never points back at andp.yml.
        raise XcodeError(
            "macOS has no simulator: `destination: %s` is invalid."
            % target.destination,
            code="bad_target_config",
            remediation="Use `destination: generic` for a macOS target.",
            context={"target": target.name, "destination": target.destination})

    argument = "platform=%s Simulator,name=%s" % (platform, target.destination)
    if target.os:
        argument += ",OS=%s" % target.os
    return argument
