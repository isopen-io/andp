"""Pure normalizer + renderers in andp/readiness.py.

verify and precheck have different result shapes; these functions collapse both
to one 'verdict' and render it for GitHub Actions. No I/O — pure functions.
"""
import json

from andp import readiness


# ---- testflight_verdict --------------------------------------------------

def test_testflight_ready():
    v = readiness.testflight_verdict(
        {"command": "verify", "ok": True,
         "checks": [{"name": "credentials", "ok": True, "detail": "ok"},
                    {"name": "jwt", "ok": True, "detail": "ok"},
                    {"name": "api_auth", "ok": True, "detail": "ok"}],
         "app": {"id": "1", "name": "N", "bundle_id": "b"}},
        bundle_id="b")
    assert v["target"] == "testflight"
    assert v["status"] == "ready" and v["ready"] is True
    assert v["credentials_ready"] is True
    assert v["blockers"] == []
    assert v["app"]["name"] == "N"


def test_testflight_missing_creds_is_unverified():
    v = readiness.testflight_verdict(
        {"command": "verify", "ok": False,
         "checks": [{"name": "credentials", "ok": False,
                     "detail": "missing or placeholder fields",
                     "missing": ["issuer_id", "key_content"]}]})
    assert v["status"] == "unverified"
    assert v["ready"] is False
    assert v["credentials_ready"] is False
    assert "issuer_id" in v["blockers"][0]["detail"]


def test_testflight_app_not_found_is_not_ready():
    v = readiness.testflight_verdict(
        {"command": "verify", "ok": False,
         "checks": [{"name": "credentials", "ok": True, "detail": "ok"},
                    {"name": "jwt", "ok": True, "detail": "ok"},
                    {"name": "api_auth", "ok": True, "detail": "ok"},
                    {"name": "app_record", "ok": False, "detail": "not found"}]})
    assert v["status"] == "not_ready"
    assert v["credentials_ready"] is True
    assert v["blockers"][0]["id"] == "app_record"


def test_testflight_retryable_api_error_is_unverified():
    v = readiness.testflight_verdict(
        {"command": "verify", "ok": False,
         "checks": [{"name": "credentials", "ok": True, "detail": "ok"},
                    {"name": "jwt", "ok": True, "detail": "ok"},
                    {"name": "api_auth", "ok": False, "detail": "429", "retryable": True}]})
    assert v["status"] == "unverified"
    assert v["credentials_ready"] is True


# ---- appstore_verdict ----------------------------------------------------

def test_appstore_clean_carries_warnings_and_note():
    v = readiness.appstore_verdict(
        {"command": "precheck", "ok": True, "errors": 0, "warnings": 1,
         "checks": [{"id": "keywords_empty", "level": "warning", "message": "no keywords"}],
         "note": "ok does not guarantee acceptance"},
        bundle_id="b", version="1.0")
    assert v["status"] == "ready" and v["ready"] is True
    assert v["blockers"] == []
    assert v["warnings"][0]["id"] == "keywords_empty"
    assert v["note"].startswith("ok does not")
    assert v["version"] == "1.0"


def test_appstore_error_checks_become_blockers():
    v = readiness.appstore_verdict(
        {"command": "precheck", "ok": False, "errors": 1, "warnings": 0,
         "checks": [{"id": "no_build", "level": "error", "message": "no build attached"},
                    {"id": "kw", "level": "warning", "message": "no keywords"}]})
    assert v["status"] == "not_ready"
    assert [b["id"] for b in v["blockers"]] == ["no_build"]
    assert [w["id"] for w in v["warnings"]] == ["kw"]


def test_appstore_no_credentials_is_unverified():
    v = readiness.appstore_verdict(
        {"command": "precheck", "ok": False,
         "error": {"code": "no_credentials", "message": "needs creds",
                   "retryable": False, "remediation": "fill secrets.yml"}})
    assert v["status"] == "unverified"
    assert v["credentials_ready"] is False
    assert v["blockers"][0]["remediation"] == "fill secrets.yml"


def test_appstore_version_not_found_is_not_ready():
    v = readiness.appstore_verdict(
        {"command": "precheck", "ok": False,
         "error": {"code": "version_not_found", "message": "no version 9.9",
                   "retryable": False, "remediation": "create it"}})
    assert v["status"] == "not_ready"
    assert v["credentials_ready"] is True
    assert v["blockers"][0]["id"] == "version_not_found"


def test_appstore_config_error_is_unverified_and_creds_not_ready():
    """A malformed secrets file couldn't load creds -> credentials_ready is False,
    consistent with the TestFlight gate for the same condition."""
    v = readiness.appstore_verdict(
        {"command": "precheck", "ok": False,
         "error": {"code": "config_error", "message": "bad secrets.yml",
                   "retryable": False, "remediation": "fix it"}})
    assert v["status"] == "unverified"
    assert v["credentials_ready"] is False


def test_appstore_retryable_error_is_unverified():
    v = readiness.appstore_verdict(
        {"command": "precheck", "ok": False,
         "error": {"code": "rate_limited", "message": "429",
                   "retryable": True, "remediation": "retry"}})
    assert v["status"] == "unverified"
    assert v["credentials_ready"] is True


# ---- renderers -----------------------------------------------------------

def test_render_markdown_shows_headline_and_ids():
    v = readiness.appstore_verdict(
        {"command": "precheck", "ok": False, "errors": 1, "warnings": 1,
         "checks": [{"id": "no_build", "level": "error", "message": "no build"},
                    {"id": "kw", "level": "warning", "message": "no keywords"}],
         "note": "N"},
        bundle_id="me.app", version="1.0")
    md = readiness.render_markdown(v)
    assert "❌" in md and "Not ready" in md
    assert "no_build" in md and "kw" in md
    assert "me.app" in md and "1.0" in md


def test_render_markdown_unverified_headline():
    v = readiness.testflight_verdict(
        {"command": "verify", "ok": False,
         "checks": [{"name": "credentials", "ok": False, "detail": "x", "missing": ["issuer_id"]}]})
    md = readiness.render_markdown(v)
    assert "⚪" in md and "Unverified" in md


def test_render_annotations_one_per_finding_and_escaped():
    v = {"target": "appstore", "status": "not_ready",
         "blockers": [{"id": "no_build", "detail": "line1\nline2"}],
         "warnings": [{"id": "kw", "detail": "adv"}]}
    lines = readiness.render_annotations(v)
    assert any(l.startswith("::error") and "no_build" in l for l in lines)
    assert any(l.startswith("::warning") and "kw" in l for l in lines)
    assert all("\n" not in l.split("::", 2)[-1] for l in lines)  # newlines escaped
    assert "%0A" in lines[0]


def test_render_outputs_ready_is_string_tristate():
    ready = readiness.render_outputs({"target": "testflight", "status": "ready",
                                      "ready": True, "credentials_ready": True,
                                      "reason": "ok", "blockers": [], "warnings": []})
    assert ready["ready"] == "true"
    unknown = readiness.render_outputs({"target": "testflight", "status": "unverified",
                                        "ready": False, "credentials_ready": False,
                                        "reason": "x", "blockers": [], "warnings": []})
    assert unknown["ready"] == "unknown"
    assert unknown["credentials_ready"] == "false"
    notready = readiness.render_outputs({"target": "appstore", "status": "not_ready",
                                         "ready": False, "credentials_ready": True,
                                         "reason": "x", "blockers": [{"id": "b", "detail": "d"}],
                                         "warnings": []})
    assert notready["ready"] == "false"
    assert notready["blockers_count"] == "1"
    assert json.loads(notready["blockers"])[0]["id"] == "b"


def test_write_github_output_uses_heredoc_for_multiline(tmp_path):
    path = tmp_path / "out"
    path.write_text("")
    readiness.write_github_output(str(path), {"reason": "line1\nline2", "ready": "false"})
    content = path.read_text()
    # multiline value must be written via heredoc, never `reason=line1\nline2`
    assert "reason<<" in content
    assert "line1\nline2" in content
    assert "reason=line1" not in content
