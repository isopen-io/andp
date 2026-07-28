"""Cascade de résolution — andp/paths.py ne lève jamais, il décrit ce qu'il trouve."""
import os

import pytest

from andp import paths


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Un HOME neuf et pas de $ANDP_CONFIG_DIR : chaque test part d'une ardoise vide."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv(paths.ENV_CONFIG_DIR, raising=False)
    return home


def _touch(path):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    open(str(path), "w").close()
    return str(path)


def test_nothing_found_returns_empty_resolution(tmp_path):
    res = paths.resolve_config("secrets.yml", str(tmp_path))
    assert res.path is None
    assert res.origin is None
    assert res.is_template is False


def test_project_level_wins_alone(tmp_path):
    expected = _touch(tmp_path / ".andp" / "secrets.yml")
    res = paths.resolve_config("secrets.yml", str(tmp_path))
    assert res.path == expected
    assert res.origin == "project"


def test_global_level_wins_alone(tmp_path, isolated_home):
    expected = _touch(isolated_home / ".andp" / "secrets.yml")
    res = paths.resolve_config("secrets.yml", str(tmp_path))
    assert res.path == expected
    assert res.origin == "global"


def test_env_level_wins_alone(tmp_path, monkeypatch):
    cfg = tmp_path / "custom"
    expected = _touch(cfg / "secrets.yml")
    monkeypatch.setenv(paths.ENV_CONFIG_DIR, str(cfg))
    res = paths.resolve_config("secrets.yml", str(tmp_path))
    assert res.path == expected
    assert res.origin == "env"


def test_template_is_the_last_resort(tmp_path):
    expected = _touch(tmp_path / "secrets.example.yml")
    res = paths.resolve_config("secrets.yml", str(tmp_path))
    assert res.path == expected
    assert res.origin == "template"
    assert res.is_template is True


def test_priority_env_over_project_over_global_over_template(tmp_path, isolated_home,
                                                             monkeypatch):
    cfg = tmp_path / "custom"
    env_path = _touch(cfg / "secrets.yml")
    _touch(tmp_path / ".andp" / "secrets.yml")
    _touch(isolated_home / ".andp" / "secrets.yml")
    _touch(tmp_path / "secrets.example.yml")
    monkeypatch.setenv(paths.ENV_CONFIG_DIR, str(cfg))

    assert paths.resolve_config("secrets.yml", str(tmp_path)).path == env_path

    monkeypatch.delenv(paths.ENV_CONFIG_DIR)
    assert paths.resolve_config("secrets.yml", str(tmp_path)).origin == "project"

    os.remove(str(tmp_path / ".andp" / "secrets.yml"))
    assert paths.resolve_config("secrets.yml", str(tmp_path)).origin == "global"

    os.remove(str(isolated_home / ".andp" / "secrets.yml"))
    assert paths.resolve_config("secrets.yml", str(tmp_path)).origin == "template"


def test_missing_env_dir_falls_through_without_raising(tmp_path, monkeypatch):
    expected = _touch(tmp_path / ".andp" / "secrets.yml")
    monkeypatch.setenv(paths.ENV_CONFIG_DIR, str(tmp_path / "does-not-exist"))
    res = paths.resolve_config("secrets.yml", str(tmp_path))
    assert res.path == expected
    assert res.origin == "project"


def test_root_secrets_is_never_a_resolution_level(tmp_path):
    """L'ancien emplacement n'est plus chargé — il est seulement détecté."""
    _touch(tmp_path / "secrets.yml")
    assert paths.resolve_config("secrets.yml", str(tmp_path)).path is None


def test_misplaced_secrets_detects_the_old_location(tmp_path):
    expected = _touch(tmp_path / "secrets.yml")
    assert paths.misplaced_secrets(str(tmp_path)) == expected


def test_misplaced_secrets_is_none_when_clean(tmp_path):
    assert paths.misplaced_secrets(str(tmp_path)) is None


def test_andp_dir_defaults_to_project(tmp_path):
    assert paths.andp_dir(str(tmp_path)) == os.path.join(str(tmp_path), ".andp")


def test_andp_dir_honours_the_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_CONFIG_DIR, "/somewhere/else")
    assert paths.andp_dir(str(tmp_path)) == "/somewhere/else"


def test_searched_paths_lists_every_inspected_location(tmp_path):
    searched = paths.searched_paths("secrets.yml", str(tmp_path))
    assert len(searched) == 3          # project, global, template (pas d'env défini)
    assert searched[-1].endswith("secrets.example.yml")


def test_policy_path_has_no_cascade(tmp_path):
    assert paths.policy_path(str(tmp_path)) == os.path.join(str(tmp_path), "andp.yml")
