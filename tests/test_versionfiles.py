"""Synchronisation de la version commerciale vers les fichiers du dépôt.

`andp version set` ne touchait qu'App Store Connect. Le dépôt, lui, gardait son
ancienne MARKETING_VERSION — vécu le 2026-07-31 sur me.meeshy.app : la version
ASC passe à 1.0.1, `project.yml` reste à 1.0.0, et tout build local produit un
CFBundleShortVersionString en désaccord avec la version qui attend le binaire.

Les fonctions de réécriture sont PURES (texte -> texte) pour être testables sans
I/O ; seule `sync_marketing_version` touche le disque.
"""
import pytest

from andp.versionfiles import (
    InvalidVersion,
    discover_version_files,
    rewrite_info_plist,
    rewrite_pbxproj,
    rewrite_project_yml,
    sync_marketing_version,
)


# --- project.yml (XcodeGen) --------------------------------------------------

def test_project_yml_quoted_value_is_rewritten():
    text = 'settings:\n  MARKETING_VERSION: "1.0.0"\n  OTHER: keep\n'
    out, n = rewrite_project_yml(text, "1.0.1")
    assert n == 1
    assert 'MARKETING_VERSION: "1.0.1"' in out
    assert "OTHER: keep" in out


def test_project_yml_unquoted_value_is_rewritten_and_stays_quoted():
    # Sans guillemets, YAML lit 1.10 comme un FLOTTANT — on requote toujours.
    text = "settings:\n  MARKETING_VERSION: 1.0.0\n"
    out, n = rewrite_project_yml(text, "1.10")
    assert n == 1
    assert 'MARKETING_VERSION: "1.10"' in out


def test_project_yml_preserves_indentation_and_comments():
    text = '  # la version commerciale\n  MARKETING_VERSION: "1.0.0"\n'
    out, _ = rewrite_project_yml(text, "2.0.0")
    assert out == '  # la version commerciale\n  MARKETING_VERSION: "2.0.0"\n'


def test_project_yml_without_the_key_is_untouched():
    text = "settings:\n  CURRENT_PROJECT_VERSION: 1265\n"
    out, n = rewrite_project_yml(text, "1.0.1")
    assert (out, n) == (text, 0)


# --- project.pbxproj ---------------------------------------------------------

def test_pbxproj_rewrites_every_occurrence():
    # Une par configuration (Debug/Release), parfois par cible.
    text = (
        "\t\t\t\tMARKETING_VERSION = 1.0.0;\n"
        "\t\t\t\tSDKROOT = iphoneos;\n"
        "\t\t\t\tMARKETING_VERSION = 1.0.0;\n"
    )
    out, n = rewrite_pbxproj(text, "1.0.1")
    assert n == 2
    assert "MARKETING_VERSION = 1.0.1;" in out
    assert "1.0.0" not in out
    assert "SDKROOT = iphoneos;" in out


def test_pbxproj_leaves_current_project_version_alone():
    """Le build number a son propre cycle (andp build-number) — ne pas y toucher."""
    text = "\t\t\t\tCURRENT_PROJECT_VERSION = 1265;\n\t\t\t\tMARKETING_VERSION = 1.0.0;\n"
    out, _ = rewrite_pbxproj(text, "1.0.1")
    assert "CURRENT_PROJECT_VERSION = 1265;" in out


# --- Info.plist --------------------------------------------------------------

def test_info_plist_literal_value_is_rewritten():
    text = (
        "<dict>\n\t<key>CFBundleShortVersionString</key>\n"
        "\t<string>1.0.0</string>\n</dict>\n"
    )
    out, n = rewrite_info_plist(text, "1.0.1")
    assert n == 1
    assert "<string>1.0.1</string>" in out


def test_info_plist_build_setting_reference_is_NOT_rewritten():
    """$(MARKETING_VERSION) délègue au build setting : l'écraser casserait tout.

    C'est le cas normal d'un projet XcodeGen — la valeur littérale n'existe que
    dans les projets qui n'utilisent pas le build setting.
    """
    text = (
        "<dict>\n\t<key>CFBundleShortVersionString</key>\n"
        "\t<string>$(MARKETING_VERSION)</string>\n</dict>\n"
    )
    out, n = rewrite_info_plist(text, "1.0.1")
    assert (out, n) == (text, 0)


def test_info_plist_other_keys_are_untouched():
    text = (
        "<key>CFBundleVersion</key>\n\t<string>1265</string>\n"
        "<key>CFBundleShortVersionString</key>\n\t<string>1.0.0</string>\n"
    )
    out, _ = rewrite_info_plist(text, "1.0.1")
    assert "<key>CFBundleVersion</key>\n\t<string>1265</string>" in out


# --- validation --------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "  ", "v1.0.0", "1.0.0-beta", "abc", "1..0"])
def test_invalid_versions_are_rejected(bad):
    with pytest.raises(InvalidVersion):
        rewrite_project_yml('MARKETING_VERSION: "1.0.0"\n', bad)


@pytest.mark.parametrize("good", ["1", "1.0", "1.0.1", "10.20.30"])
def test_apple_accepts_one_to_three_numeric_components(good):
    out, n = rewrite_project_yml('MARKETING_VERSION: "0.0.0"\n', good)
    assert n == 1 and f'"{good}"' in out


# --- découverte + application ------------------------------------------------

def _make_tree(root):
    (root / "apps" / "ios" / "Meeshy.xcodeproj").mkdir(parents=True)
    (root / "apps" / "ios" / "project.yml").write_text(
        'settings:\n  MARKETING_VERSION: "1.0.0"\n')
    (root / "apps" / "ios" / "Meeshy.xcodeproj" / "project.pbxproj").write_text(
        "\t\t\t\tMARKETING_VERSION = 1.0.0;\n")
    (root / "apps" / "ios" / "Info.plist").write_text(
        "<key>CFBundleShortVersionString</key>\n\t<string>$(MARKETING_VERSION)</string>\n")
    return root


def test_discover_finds_project_yml_and_pbxproj(tmp_path):
    _make_tree(tmp_path)
    found = {p.name for p in discover_version_files(tmp_path)}
    assert "project.yml" in found
    assert "project.pbxproj" in found


def test_discover_skips_build_and_vendor_directories(tmp_path):
    _make_tree(tmp_path)
    for noise in ("node_modules", "Build", ".git", "DerivedData", "Pods"):
        d = tmp_path / noise
        d.mkdir()
        (d / "project.yml").write_text('MARKETING_VERSION: "9.9.9"\n')
    found = [p for p in discover_version_files(tmp_path)]
    assert not any(
        part in {"node_modules", "Build", ".git", "DerivedData", "Pods"}
        for p in found for part in p.parts)


def test_sync_updates_every_file_and_reports_them(tmp_path):
    _make_tree(tmp_path)
    result = sync_marketing_version(tmp_path, "1.0.1")
    assert result["ok"] is True
    assert result["version"] == "1.0.1"
    assert result["changed"] is True
    assert 'MARKETING_VERSION: "1.0.1"' in (tmp_path / "apps/ios/project.yml").read_text()
    assert "MARKETING_VERSION = 1.0.1;" in (
        tmp_path / "apps/ios/Meeshy.xcodeproj/project.pbxproj").read_text()
    names = {f["path"].split("/")[-1] for f in result["files"]}
    assert names == {"project.yml", "project.pbxproj"}


def test_sync_leaves_info_plist_delegating_to_the_build_setting(tmp_path):
    _make_tree(tmp_path)
    sync_marketing_version(tmp_path, "1.0.1")
    assert "$(MARKETING_VERSION)" in (tmp_path / "apps/ios/Info.plist").read_text()


def test_sync_is_idempotent(tmp_path):
    _make_tree(tmp_path)
    sync_marketing_version(tmp_path, "1.0.1")
    again = sync_marketing_version(tmp_path, "1.0.1")
    assert again["ok"] is True
    assert again["changed"] is False
    assert again["files"] == []


def test_sync_dry_run_reports_without_writing(tmp_path):
    _make_tree(tmp_path)
    result = sync_marketing_version(tmp_path, "1.0.1", dry_run=True)
    assert result["dry_run"] is True
    assert result["changed"] is True
    assert len(result["files"]) == 2
    assert '"1.0.0"' in (tmp_path / "apps/ios/project.yml").read_text()


def test_sync_rejects_an_invalid_version_without_touching_anything(tmp_path):
    _make_tree(tmp_path)
    result = sync_marketing_version(tmp_path, "v1.0.0")
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_version"
    assert '"1.0.0"' in (tmp_path / "apps/ios/project.yml").read_text()


def test_sync_on_a_tree_without_version_files_is_ok_and_empty(tmp_path):
    (tmp_path / "README.md").write_text("rien a versionner\n")
    result = sync_marketing_version(tmp_path, "1.0.1")
    assert result["ok"] is True
    assert result["changed"] is False
    assert result["files"] == []


def test_discover_skips_hidden_directories_including_agent_worktrees(tmp_path):
    """Un dépôt contient souvent des worktrees isolés sous des dossiers cachés.

    Vécu 2026-07-31 sur meeshy : `.claude/worktrees/<branche>/apps/ios/project.yml`
    appartient à une AUTRE session de travail. Y réécrire la version commerciale
    écraserait le travail en cours de quelqu'un d'autre — exactement le dégât
    qu'un outil de release ne doit jamais causer.
    """
    _make_tree(tmp_path)
    wt = tmp_path / ".claude" / "worktrees" / "feat-x" / "apps" / "ios"
    wt.mkdir(parents=True)
    (wt / "project.yml").write_text('settings:\n  MARKETING_VERSION: "0.9.0"\n')

    found = discover_version_files(tmp_path)
    assert not any(".claude" in p.parts for p in found)

    sync_marketing_version(tmp_path, "1.0.1")
    assert '"0.9.0"' in (wt / "project.yml").read_text()   # worktree intact
