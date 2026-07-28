"""`andp run` — l'ordre boot → install → launch est le contrat."""
import json

import pytest

from andp.asc.asc_manager import main
from andp.xcode import commands
from andp.xcode.targets import Target

PLIST = ('<?xml version="1.0" encoding="UTF-8"?>'
         '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
         '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
         '<plist version="1.0"><dict>'
         '<key>CFBundleIdentifier</key><string>com.a</string>'
         '</dict></plist>')


class Recorder(object):
    def __init__(self, code=0, payload=""):
        self.calls = []
        self.code = code
        self.payload = payload

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        handle = kwargs.get("stdout")
        if handle is not None and hasattr(handle, "write"):
            handle.write(self.payload)
        return self.code

    def simctl_verbs(self):
        return [c[2] for c in self.calls if c[:2] == ["xcrun", "simctl"]]


def _t(**kwargs):
    base = dict(name="a", scheme="A", platform="iOS", destination="iPhone 15",
                configuration="Debug", os=None)
    base.update(kwargs)
    return Target(**base)


@pytest.fixture
def app(tmp_path):
    bundle = tmp_path / "A.app"
    bundle.mkdir()
    (bundle / "Info.plist").write_text(PLIST)
    return str(bundle)


@pytest.fixture(autouse=True)
def with_xcodebuild(tmp_path, monkeypatch):
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "xcodebuild").write_text("#!/bin/sh\n")
    monkeypatch.setenv("PATH", str(fake_bin))


@pytest.fixture
def simulated(monkeypatch, app):
    """app_path et simulator.find figés : on teste l'enchaînement, pas Xcode."""
    monkeypatch.setattr(commands.runner, "app_path", lambda *a, **k: app)

    def _find(target, run_process=None):
        return {"udid": "AAA", "name": "iPhone 15", "state": _find.state}

    _find.state = "Shutdown"
    monkeypatch.setattr(commands.simulator, "find", _find)
    return _find


def test_boots_installs_then_launches(tmp_path, simulated):
    recorder = Recorder()
    commands.run_target(_t(), str(tmp_path), str(tmp_path), build_first=False,
                        run_process=recorder)
    verbs = recorder.simctl_verbs()
    assert "boot" in verbs
    assert verbs.index("install") < verbs.index("launch")


def test_skips_boot_when_already_booted(tmp_path, simulated):
    """Booter un simulateur déjà démarré coûte du temps pour rien."""
    simulated.state = "Booted"
    recorder = Recorder()
    commands.run_target(_t(), str(tmp_path), str(tmp_path), build_first=False,
                        run_process=recorder)
    assert "boot" not in recorder.simctl_verbs()


def test_envelope_reports_the_chosen_simulator(tmp_path, simulated):
    envelope = commands.run_target(_t(), str(tmp_path), str(tmp_path),
                                   build_first=False, run_process=Recorder())
    entry = envelope["results"][0]
    assert entry["udid"] == "AAA"
    assert entry["simulator"] == "iPhone 15"
    assert entry["bundle_id"] == "com.a"


def test_a_failed_build_stops_before_install(tmp_path, monkeypatch, app):
    """Installer après un build raté lancerait un binaire périmé."""
    monkeypatch.setattr(commands.runner, "app_path", lambda *a, **k: app)
    installed = []
    monkeypatch.setattr(commands.simulator, "install",
                        lambda *a, **k: installed.append(a))
    envelope = commands.run_target(_t(), str(tmp_path), str(tmp_path),
                                   build_first=True,
                                   run_process=Recorder(code=65))
    assert envelope["ok"] is False
    assert installed == []
    assert envelope["results"][0]["error"]["code"] == "build_failed"


def test_logs_are_streamed_on_demand(tmp_path, simulated):
    recorder = Recorder()
    commands.run_target(_t(), str(tmp_path), str(tmp_path), build_first=False,
                        follow_logs=True, run_process=recorder)
    assert "spawn" in recorder.simctl_verbs()


def test_logs_are_not_streamed_by_default(tmp_path, simulated):
    recorder = Recorder()
    commands.run_target(_t(), str(tmp_path), str(tmp_path), build_first=False,
                        run_process=recorder)
    assert "spawn" not in recorder.simctl_verbs()


def test_physical_device_goes_through_devicectl(tmp_path, monkeypatch, app):
    monkeypatch.setattr(commands.runner, "app_path", lambda *a, **k: app)
    recorder = Recorder()
    envelope = commands.run_target(_t(destination="id=UDID-42"), str(tmp_path),
                                   str(tmp_path), build_first=False,
                                   run_process=recorder)
    assert all(c[1] == "devicectl" for c in recorder.calls)
    assert envelope["results"][0]["udid"] == "UDID-42"


def test_macos_launches_the_binary_directly(tmp_path, monkeypatch, app):
    monkeypatch.setattr(commands.runner, "app_path", lambda *a, **k: app)
    recorder = Recorder()
    envelope = commands.run_target(_t(platform="macOS", destination="generic"),
                                   str(tmp_path), str(tmp_path),
                                   build_first=False, run_process=recorder)
    assert recorder.calls == [[app]]
    assert envelope["ok"] is True


# --- surface CLI ----------------------------------------------------------

@pytest.fixture
def project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANDP_APP_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "andp.yml").write_text(
        "targets:\n  a:\n    scheme: A\n  b:\n    scheme: B\n")
    return tmp_path


def test_run_refuses_several_targets(project, capsys):
    rc = main(["run", "a", "b", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "bad_usage"


def test_run_declares_dry_run(project, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "")
    rc = main(["run", "a", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["dry_run"] is True


def test_run_needs_no_credentials(project, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "")
    main(["run", "a"])
    assert "App Store Connect credentials" not in capsys.readouterr().err


def test_run_on_an_unknown_target(project, capsys):
    rc = main(["run", "nope", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "target_not_found"
