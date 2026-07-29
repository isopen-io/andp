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
    assert sorted(targets.load_targets(root)) == ["x"]
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


def test_autodetect_multiple_schemes_with_override_succeeds(tmp_path):
    t = targets.resolve(None, str(tmp_path), scheme_lister=lambda d: ["A", "B"], overrides={"scheme": "B"})
    assert t.scheme == "B"
    assert t.platform == "iOS"


def test_an_explicit_scheme_never_lists_the_schemes(tmp_path):
    """Lister les schemes lance xcodebuild — plusieurs secondes pour une réponse
    que l'override rend inutile."""
    def refuse(directory):
        raise AssertionError("scheme_lister appelé malgré --scheme")

    t = targets.resolve(None, str(tmp_path), scheme_lister=refuse,
                        overrides={"scheme": "B"})
    assert t.scheme == "B"


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


def test_ensure_project_accepts_an_xcodeproj(tmp_path):
    (tmp_path / "Demo.xcodeproj").mkdir()
    assert targets.ensure_project(str(tmp_path)) == str(tmp_path)


def test_ensure_project_accepts_a_workspace(tmp_path):
    (tmp_path / "Demo.xcworkspace").mkdir()
    assert targets.ensure_project(str(tmp_path)) == str(tmp_path)


def test_ensure_project_fails_once_up_front(tmp_path):
    """Sans cette garde, chaque cible relance xcodebuild pour la même absence."""
    with pytest.raises(XcodeError) as excinfo:
        targets.ensure_project(str(tmp_path), str(tmp_path))
    assert excinfo.value.code == "no_project"
    assert excinfo.value.context["project_dir"] == str(tmp_path)
    assert excinfo.value.context["policy"].endswith("andp.yml")


def test_ensure_project_on_a_missing_directory(tmp_path):
    with pytest.raises(XcodeError) as excinfo:
        targets.ensure_project(str(tmp_path / "absent"))
    assert excinfo.value.code == "no_project"


def test_project_dir_prefers_the_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv(targets.ENV_APP_DIR, "/from/env")
    assert targets.project_dir(str(tmp_path)) == "/from/env"


def test_project_dir_falls_back_to_andp_yml(tmp_path):
    root = _write(tmp_path, "project:\n  dir: apps/demo\n")
    assert targets.project_dir(root).endswith("apps/demo")


def test_project_dir_defaults_to_the_root(tmp_path):
    assert targets.project_dir(str(tmp_path)) == str(tmp_path)


# --- andp.yml illisible : une erreur typée, jamais une trace Python ----------
#
# Tout lecteur du module passe par _load_yaml. Une exception brute y remonterait
# jusqu'au CLI en trace, sans rien sur stdout — l'enveloppe {ok, error} que parse
# un agent disparaîtrait au moment précis où il en a besoin.


def test_malformed_yaml_is_a_typed_error(tmp_path):
    root = _write(tmp_path, "targets:\n  dev:\n   - [\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.load_targets(root)
    assert excinfo.value.code == "bad_config"
    assert excinfo.value.context["policy"].endswith("andp.yml")


def test_andp_yml_must_be_a_mapping(tmp_path):
    root = _write(tmp_path, "- a\n- b\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.load_targets(root)
    assert excinfo.value.code == "bad_config"
    assert excinfo.value.context["found"] == "list"


def test_malformed_yaml_also_guards_project_dir(tmp_path):
    """project_dir lit le même fichier : la garde doit valoir pour lui aussi."""
    root = _write(tmp_path, "project:\n  dir: [\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.project_dir(root)
    assert excinfo.value.code == "bad_config"


def test_project_block_must_be_a_mapping(tmp_path):
    root = _write(tmp_path, "project: oops\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.project_dir(root)
    assert excinfo.value.code == "bad_config"
    assert excinfo.value.context["found"] == "str"


# --- validation des surcharges de la ligne de commande -----------------------


def test_unknown_platform_from_a_flag_is_refused(tmp_path):
    """--platform ne passait par aucune validation : `Android` atteignait
    xcodebuild sous la forme `platform=Android Simulator`."""
    root = _write(tmp_path, "targets:\n  dev:\n    scheme: S\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve("dev", root, overrides={"platform": "Android"})
    assert excinfo.value.code == "bad_target_config"
    assert excinfo.value.context["flag"] == "--platform"
    assert excinfo.value.context["unknown"] == "Android"


def test_a_valid_platform_from_a_flag_passes(tmp_path):
    root = _write(tmp_path, "targets:\n  dev:\n    scheme: S\n")
    t = targets.resolve("dev", root, overrides={"platform": "tvOS"})
    assert t.platform == "tvOS"


def test_the_flag_guard_also_covers_autodetection(tmp_path):
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve(None, str(tmp_path), scheme_lister=lambda d: ["Solo"],
                        overrides={"platform": "Android"})
    assert excinfo.value.code == "bad_target_config"


# --- formes non conformes dans le bloc targets: ------------------------------


def test_a_target_must_be_a_mapping(tmp_path):
    root = _write(tmp_path, "targets:\n  dev: oops\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve("dev", root)
    assert excinfo.value.code == "bad_target_config"
    assert excinfo.value.context["target"] == "dev"


def test_defaults_must_be_a_mapping(tmp_path):
    root = _write(tmp_path, "targets:\n  defaults: oops\n  dev:\n    scheme: S\n")
    with pytest.raises(XcodeError) as excinfo:
        targets.resolve("dev", root)
    assert excinfo.value.code == "bad_target_config"
    assert excinfo.value.context["target"] == "defaults"


# --- derniers chemins non couverts -------------------------------------------


def test_autodetection_imports_the_real_lister_when_none_is_injected(
        tmp_path, monkeypatch):
    """Sans lanceur injecté, le module va chercher list_schemes dans runner.
    L'import est différé pour que ce module reste pur — il ne s'exécute que là."""
    from andp.xcode import runner
    monkeypatch.setattr(runner, "list_schemes", lambda directory: ["Solo"])
    assert targets.resolve(None, str(tmp_path)).scheme == "Solo"


def test_a_numeric_target_name_stays_usable(tmp_path):
    """YAML lit un `26:` non quoté comme un entier. Sans normalisation,
    `andp targets` affiche un nom que `andp build` refuse ensuite."""
    root = _write(tmp_path, "targets:\n  26:\n    scheme: S\n")
    assert list(targets.load_targets(root)) == ["26"]
    assert targets.resolve("26", root).scheme == "S"


def test_numeric_and_named_targets_sort_together(tmp_path):
    """Trier un mélange d'entiers et de chaînes levait un TypeError nu."""
    root = _write(tmp_path, "targets:\n  26:\n    scheme: A\n  dev:\n    scheme: B\n")
    assert [t.name for t in targets.resolve_all(root)] == ["26", "dev"]


def test_ensure_project_ignores_entries_that_are_not_projects(tmp_path):
    """Un dossier peuplé sans .xcodeproj échoue comme un dossier vide."""
    (tmp_path / "README.md").write_text("")
    (tmp_path / "Sources").mkdir()
    with pytest.raises(XcodeError) as excinfo:
        targets.ensure_project(str(tmp_path))
    assert excinfo.value.code == "no_project"
