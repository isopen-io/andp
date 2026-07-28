"""Résolution des cibles — héritage, validation stricte, auto-détection."""
import pytest

from andp.errors import XcodeError
from andp.xcode import targets


@pytest.fixture(autouse=True)
def no_app_dir(monkeypatch):
    """$ANDP_APP_DIR fuiterait de l'environnement dans les tests de project_dir."""
    monkeypatch.delenv(targets.ENV_APP_DIR, raising=False)


def _write(tmp_path, body):
    (tmp_path / "andp.yml").write_text(body)
    return str(tmp_path)


def test_named_target_inherits_defaults(tmp_path):
    root = _write(tmp_path, """
targets:
  defaults:
    scheme: Meeshy
    configuration: Release
  vision:
    platform: visionOS
""")
    t = targets.resolve("vision", root)
    assert t.scheme == "Meeshy"
    assert t.configuration == "Release"
    assert t.platform == "visionOS"
    assert t.destination == "generic"


def test_target_overrides_defaults(tmp_path):
    root = _write(tmp_path, """
targets:
  defaults:
    configuration: Debug
  prod:
    configuration: Release
""")
    assert targets.resolve("prod", root).configuration == "Release"


def test_defaults_is_not_a_target(tmp_path):
    root = _write(tmp_path,
                  "targets:\n  defaults:\n    scheme: A\n  x:\n    platform: iOS\n")
    assert targets.list_names(root) == ["x"]
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve("defaults", root)
    assert excinfo.value.code == "target_not_found"


def test_unknown_target_lists_the_known_ones(tmp_path):
    root = _write(tmp_path, "targets:\n  a:\n    platform: iOS\n  b:\n    platform: tvOS\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve("c", root)
    assert excinfo.value.code == "target_not_found"
    assert excinfo.value.context["available"] == ["a", "b"]


def test_unknown_field_is_refused(tmp_path):
    root = _write(tmp_path, "targets:\n  a:\n    platfrom: iOS\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve("a", root)
    assert excinfo.value.code == "bad_target_config"
    assert excinfo.value.context["unknown"] == "platfrom"
    assert "platform" in excinfo.value.context["allowed"]


def test_unknown_platform_is_refused(tmp_path):
    root = _write(tmp_path, "targets:\n  a:\n    platform: androidOS\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve("a", root)
    assert excinfo.value.code == "bad_target_config"
    assert "visionOS" in excinfo.value.context["allowed"]


def test_targets_block_must_be_a_mapping(tmp_path):
    root = _write(tmp_path, "targets:\n  - a\n  - b\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.load_targets(root)
    assert excinfo.value.code == "bad_target_config"


def test_autodetect_single_scheme(tmp_path):
    t = targets.resolve(None, str(tmp_path), scheme_lister=lambda d: ["Solo"])
    assert t.name == "default"
    assert t.scheme == "Solo"
    assert t.platform == "iOS"


def test_autodetect_multiple_schemes_is_ambiguous(tmp_path):
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve(None, str(tmp_path), scheme_lister=lambda d: ["A", "B"])
    assert excinfo.value.code == "ambiguous_scheme"
    assert excinfo.value.context["schemes"] == ["A", "B"]
    assert "targets:" in excinfo.value.remediation


def test_single_declared_target_needs_no_name(tmp_path):
    root = _write(tmp_path, "targets:\n  only:\n    scheme: S\n")
    assert targets.resolve(None, root).name == "only"


def test_several_declared_targets_without_a_name_is_ambiguous(tmp_path):
    root = _write(tmp_path, "targets:\n  a:\n    scheme: A\n  b:\n    scheme: B\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve(None, root)
    assert excinfo.value.code == "ambiguous_target"
    assert excinfo.value.context["available"] == ["a", "b"]


def test_overrides_beat_the_declaration(tmp_path):
    root = _write(tmp_path, "targets:\n  a:\n    configuration: Debug\n")
    t = targets.resolve("a", root, overrides={"configuration": "Release"})
    assert t.configuration == "Release"


def test_none_overrides_are_ignored(tmp_path):
    """argparse laisse les drapeaux absents à None — ils ne doivent rien écraser."""
    root = _write(tmp_path, "targets:\n  a:\n    configuration: Release\n")
    t = targets.resolve("a", root, overrides={"configuration": None, "os": None})
    assert t.configuration == "Release"


def test_resolve_all_returns_every_declared_target(tmp_path):
    root = _write(tmp_path, "targets:\n  a:\n    platform: iOS\n  b:\n    platform: macOS\n")
    assert [t.name for t in targets.resolve_all(root)] == ["a", "b"]


def test_resolve_all_falls_back_to_autodetection(tmp_path):
    found = targets.resolve_all(str(tmp_path), scheme_lister=lambda d: ["Solo"])
    assert [t.name for t in found] == ["default"]


def test_no_andp_yml_at_all(tmp_path):
    assert targets.load_targets(str(tmp_path)) == {}
    assert targets.list_names(str(tmp_path)) == []


def test_project_dir_prefers_the_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv(targets.ENV_APP_DIR, "/from/env")
    assert targets.project_dir(str(tmp_path)) == "/from/env"


def test_project_dir_falls_back_to_andp_yml(tmp_path):
    root = _write(tmp_path, "project:\n  dir: apps/demo\n")
    assert targets.project_dir(root).endswith("apps/demo")


def test_project_dir_defaults_to_the_root(tmp_path):
    assert targets.project_dir(str(tmp_path)) == str(tmp_path)
