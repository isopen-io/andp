"""CLI `andp readiness <testflight|appstore> ...` — exit-code contract and the
GitHub Actions side-effects (step summary, outputs, annotations)."""
import json

from andp import service
from andp.asc import asc_manager
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


def _real(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    return session


def _placeholder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secrets.yml").write_text(
        "accounts:\n  primary:\n    asc_api:\n"
        "      key_id: \"ABCDE12345\"\n      issuer_id: \"\"\n      key_content: \"\"\n")


def test_cli_testflight_ready_exit_0(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(FakeResponse(200, {"data": [
        {"id": "app-1", "attributes": {"name": "Demo", "bundleId": "me.app"}}]}))
    code = asc_manager.main(["readiness", "testflight", "me.app", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["target"] == "testflight" and out["ready"] is True


def test_cli_appstore_not_ready_exit_1(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": []}),  # version not found -> not_ready
    )
    code = asc_manager.main(["readiness", "appstore", "me.app", "9.9", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["status"] == "not_ready"


def test_cli_soft_downgrades_not_ready_to_0(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": []}),
    )
    code = asc_manager.main(["readiness", "appstore", "me.app", "9.9", "--json", "--soft"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0            # soft: gate does not fail the job
    assert out["ready"] is False  # ...but the verdict is still honest


def test_cli_unverified_exit_3_by_default(tmp_path, monkeypatch, capsys):
    _placeholder(tmp_path, monkeypatch)
    code = asc_manager.main(["readiness", "testflight", "me.app", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["status"] == "unverified"


def test_cli_allow_unverified_downgrades_to_0(tmp_path, monkeypatch, capsys):
    _placeholder(tmp_path, monkeypatch)
    code = asc_manager.main(["readiness", "testflight", "me.app", "--json", "--allow-unverified"])
    capsys.readouterr()
    assert code == 0


def test_cli_bad_target_is_usage_error(tmp_path, monkeypatch, capsys):
    _placeholder(tmp_path, monkeypatch)
    code = asc_manager.main(["readiness", "sideload", "me.app"])
    assert code == 2


def test_cli_appstore_requires_version(tmp_path, monkeypatch, capsys):
    _placeholder(tmp_path, monkeypatch)
    code = asc_manager.main(["readiness", "appstore", "me.app"])
    assert code == 2


def test_cli_writes_github_summary_and_outputs(tmp_path, monkeypatch, ec_private_key_pem):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(FakeResponse(200, {"data": [
        {"id": "app-1", "attributes": {"name": "Demo", "bundleId": "me.app"}}]}))
    summary = tmp_path / "summary.md"
    output = tmp_path / "gh_output"
    summary.write_text("")
    output.write_text("")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    code = asc_manager.main(["readiness", "testflight", "me.app", "--json"])
    assert code == 0
    assert "TestFlight readiness" in summary.read_text()
    out_content = output.read_text()
    assert "ready<<" in out_content            # heredoc form
    assert "true" in out_content


def test_cli_json_stdout_is_pure_even_in_github(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": []}),
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    asc_manager.main(["readiness", "appstore", "me.app", "9.9", "--json", "--soft"])
    out = capsys.readouterr().out
    # stdout must parse as a single JSON object: no ::error:: annotations mixed in
    parsed = json.loads(out)
    assert parsed["command"] == "readiness"
