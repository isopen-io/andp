"""Traduction cible → argument -destination. Fonction pure, entièrement testée."""
import pytest

from andp.errors import XcodeError
from andp.xcode import destination
from andp.xcode.targets import Target


def _t(**kwargs):
    base = dict(name="t", scheme="S", platform="iOS", destination="generic",
                configuration="Debug", os=None)
    base.update(kwargs)
    return Target(**base)


def test_generic_destination():
    assert destination.to_argument(_t()) == "generic/platform=iOS"


def test_named_simulator():
    assert destination.to_argument(_t(destination="iPhone 15")) == \
        "platform=iOS Simulator,name=iPhone 15"


def test_named_simulator_with_runtime():
    assert destination.to_argument(_t(destination="iPhone 15", os="17.0")) == \
        "platform=iOS Simulator,name=iPhone 15,OS=17.0"


def test_physical_device_by_id():
    assert destination.to_argument(_t(destination="id=00008030-ABC")) == \
        "platform=iOS,id=00008030-ABC"


def test_ipados_is_an_alias_for_ios():
    """xcodebuild ne connaît pas iPadOS — la distinction est dans le nom."""
    assert destination.to_argument(_t(platform="iPadOS", destination="iPad Air")) == \
        "platform=iOS Simulator,name=iPad Air"


def test_visionos_simulator():
    assert destination.to_argument(_t(platform="visionOS",
                                      destination="Apple Vision Pro")) == \
        "platform=visionOS Simulator,name=Apple Vision Pro"


def test_watchos_simulator():
    assert destination.to_argument(_t(platform="watchOS",
                                      destination="Apple Watch Series 9 (45mm)")) == \
        "platform=watchOS Simulator,name=Apple Watch Series 9 (45mm)"


def test_tvos_simulator():
    assert destination.to_argument(_t(platform="tvOS", destination="Apple TV")) == \
        "platform=tvOS Simulator,name=Apple TV"


def test_generic_for_every_platform():
    for platform in ("iOS", "watchOS", "tvOS", "macOS", "visionOS"):
        assert destination.to_argument(_t(platform=platform)) == \
            "generic/platform=%s" % platform


def test_macos_refuses_a_named_simulator():
    with pytest.raises(XcodeError) as excinfo:
        destination.to_argument(_t(platform="macOS", destination="Mon Mac"))
    assert excinfo.value.code == "bad_target_config"
    assert "generic" in excinfo.value.remediation


def test_macos_accepts_a_device_id():
    assert destination.to_argument(_t(platform="macOS", destination="id=ABC")) == \
        "platform=macOS,id=ABC"


def test_is_simulator():
    assert destination.is_simulator(_t(destination="iPhone 15")) is True
    assert destination.is_simulator(_t(destination="id=ABC")) is False
    assert destination.is_simulator(_t(destination="generic")) is False
    assert destination.is_simulator(_t(platform="macOS")) is False


def test_is_device():
    assert destination.is_device(_t(destination="id=ABC")) is True
    assert destination.is_device(_t(destination="iPhone 15")) is False
    assert destination.is_device(_t(destination="generic")) is False


def test_sdk_platform_normalises_only_ipados():
    assert destination.sdk_platform(_t(platform="iPadOS")) == "iOS"
    assert destination.sdk_platform(_t(platform="visionOS")) == "visionOS"
