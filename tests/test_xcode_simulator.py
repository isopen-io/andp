"""simctl et devicectl — via lanceur injecté, aucun processus réel."""
import json

import pytest

from andp.errors import XcodeError
from andp.xcode import device, simulator
from andp.xcode.targets import Target

DEVICES = {"devices": {
    "com.apple.CoreSimulator.SimRuntime.iOS-17-0": [
        {"udid": "AAA", "name": "iPhone 15", "state": "Shutdown",
         "isAvailable": True},
        {"udid": "BBB", "name": "iPhone 15 Pro", "state": "Booted",
         "isAvailable": True},
        {"udid": "CCC", "name": "iPhone 14", "state": "Shutdown",
         "isAvailable": False}],
    "com.apple.CoreSimulator.SimRuntime.xrOS-1-0": [
        {"udid": "VVV", "name": "Apple Vision Pro", "state": "Shutdown",
         "isAvailable": True}]}}


class FakeProcess(object):
    def __init__(self, code=0, stdout=""):
        self.calls = []
        self.code = code
        self.stdout = stdout

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        handle = kwargs.get("stdout")
        if handle is not None and hasattr(handle, "write"):
            handle.write(self.stdout)
        return self.code


def _t(**kwargs):
    base = dict(name="dev", scheme="S", platform="iOS", destination="generic",
                configuration="Debug", os=None)
    base.update(kwargs)
    return Target(**base)


def _listing():
    return FakeProcess(0, json.dumps(DEVICES))


def test_find_by_name():
    assert simulator.find(_t(destination="iPhone 15"),
                          run_process=_listing())["udid"] == "AAA"


def test_generic_prefers_a_booted_simulator():
    """Sans nom, on prend celui qui tourne déjà — pas de boot inutile."""
    assert simulator.find(_t(), run_process=_listing())["udid"] == "BBB"


def test_generic_filters_by_platform():
    """visionOS s'appelle xrOS dans simctl — la correspondance doit tenir."""
    assert simulator.find(_t(platform="visionOS"),
                          run_process=_listing())["udid"] == "VVV"


def test_unavailable_devices_are_skipped():
    with pytest.raises(XcodeError) as excinfo:
        simulator.find(_t(destination="iPhone 14"), run_process=_listing())
    assert excinfo.value.code == "simulator_not_found"
    assert "iPhone 14" not in excinfo.value.context["available"]


def test_missing_name_lists_what_exists():
    with pytest.raises(XcodeError) as excinfo:
        simulator.find(_t(destination="iPhone 99"), run_process=_listing())
    assert excinfo.value.context["available"] == ["iPhone 15", "iPhone 15 Pro"]


def test_no_simulator_for_the_platform():
    with pytest.raises(XcodeError) as excinfo:
        simulator.find(_t(platform="tvOS"), run_process=_listing())
    assert excinfo.value.code == "simulator_not_found"
    assert excinfo.value.context["platform"] == "tvOS"


def test_unreadable_listing_yields_no_candidates():
    with pytest.raises(XcodeError) as excinfo:
        simulator.find(_t(), run_process=FakeProcess(0, "not json"))
    assert excinfo.value.code == "simulator_not_found"


def test_boot_waits_for_readiness():
    fake = FakeProcess(0)
    simulator.boot("AAA", run_process=fake)
    assert fake.calls[0] == ["xcrun", "simctl", "boot", "AAA"]
    assert "bootstatus" in fake.calls[1]


def test_boot_failure_is_retryable():
    """La seule opération réessayable de la couche."""
    with pytest.raises(XcodeError) as excinfo:
        simulator.boot("AAA", run_process=FakeProcess(1))
    assert excinfo.value.code == "simulator_boot_failed"
    assert excinfo.value.retryable is True


def test_install_and_launch():
    fake = FakeProcess(0)
    simulator.install("AAA", "/tmp/My.app", run_process=fake)
    simulator.launch("AAA", "com.me.app", run_process=fake)
    assert fake.calls[0] == ["xcrun", "simctl", "install", "AAA", "/tmp/My.app"]
    assert fake.calls[1] == ["xcrun", "simctl", "launch", "AAA", "com.me.app"]


def test_install_failure_is_typed():
    with pytest.raises(XcodeError) as excinfo:
        simulator.install("AAA", "/tmp/My.app", run_process=FakeProcess(1))
    assert excinfo.value.code == "install_failed"


def test_launch_failure_is_typed():
    with pytest.raises(XcodeError) as excinfo:
        simulator.launch("AAA", "com.me.app", run_process=FakeProcess(1))
    assert excinfo.value.code == "launch_failed"


def test_stream_logs_filters_on_the_bundle():
    fake = FakeProcess(0)
    simulator.stream_logs("AAA", "com.me.app", run_process=fake)
    assert "com.me.app" in " ".join(fake.calls[0])
    assert "stream" in fake.calls[0]


def test_bundle_id_is_read_from_the_app_plist(tmp_path):
    app = tmp_path / "My.app"
    app.mkdir()
    (app / "Info.plist").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        '<plist version="1.0"><dict>'
        '<key>CFBundleIdentifier</key><string>com.me.app</string>'
        '</dict></plist>')
    assert simulator.bundle_id(str(app)) == "com.me.app"


def test_bundle_id_missing_plist_raises(tmp_path):
    with pytest.raises(XcodeError) as excinfo:
        simulator.bundle_id(str(tmp_path / "Nope.app"))
    assert excinfo.value.code == "app_not_found"


def test_bundle_id_without_the_key_raises(tmp_path):
    app = tmp_path / "My.app"
    app.mkdir()
    (app / "Info.plist").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        '<plist version="1.0"><dict>'
        '<key>CFBundleName</key><string>My</string></dict></plist>')
    with pytest.raises(XcodeError) as excinfo:
        simulator.bundle_id(str(app))
    assert excinfo.value.code == "app_not_found"


def test_device_install_uses_devicectl():
    fake = FakeProcess(0)
    device.install("UDID", "/tmp/My.app", run_process=fake)
    assert fake.calls[0][:3] == ["xcrun", "devicectl", "device"]
    assert "--device" in fake.calls[0]


def test_device_install_failure_mentions_provisioning():
    with pytest.raises(XcodeError) as excinfo:
        device.install("UDID", "/tmp/My.app", run_process=FakeProcess(1))
    assert excinfo.value.code == "device_install_failed"
    assert "provisioning" in excinfo.value.remediation


def test_device_launch_failure_is_typed():
    with pytest.raises(XcodeError) as excinfo:
        device.launch("UDID", "com.me.app", run_process=FakeProcess(1))
    assert excinfo.value.code == "device_not_found"
