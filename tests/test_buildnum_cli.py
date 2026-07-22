"""CLI `andp build-number` — stdout carries ONLY the number; exit codes."""
import json

from andp import service
from andp.asc import asc_manager
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


def test_timestamp_stdout_is_only_the_number(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)   # no secrets file at all -> must still work
    code = asc_manager.main(["build-number", "--strategy", "timestamp"])
    out = capsys.readouterr()
    assert code == 0
    assert out.out.strip().isdigit()          # exactly the number
    assert "DRY-RUN" not in out.out           # banner went to stderr


def test_commit_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = asc_manager.main(["build-number", "--strategy", "commit", "--sha", "deadbeef"])
    out = capsys.readouterr()
    assert code == 0
    assert out.out.strip() == str(int("deadbee", 16))


def test_unknown_strategy_is_usage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert asc_manager.main(["build-number", "--strategy", "nope"]) == 2


def test_no_strategy_is_usage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert asc_manager.main(["build-number"]) == 2


def test_max_build_without_bundle_is_usage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert asc_manager.main(["build-number", "--strategy", "max-build"]) == 2


def test_max_build_prints_number(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": [{"attributes": {"version": "1200"}}], "links": {}}),
    )
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    code = asc_manager.main(["build-number", "me.app", "--strategy", "max-build", "--floor", "1254"])
    out = capsys.readouterr()
    assert code == 0
    assert out.out.strip() == "1255"


def test_json_envelope(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = asc_manager.main(["build-number", "--strategy", "commit", "--sha", "abcdef1", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["command"] == "build_number"
    assert out["strategy"] == "commit"
    assert out["monotonic"] is False
