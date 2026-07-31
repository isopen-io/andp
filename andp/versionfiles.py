"""Propage la version commerciale (MARKETING_VERSION) dans les fichiers du dépôt.

`andp version set` réconcilie App Store Connect. Sans ce module, le dépôt reste
en arrière : vécu le 2026-07-31 sur me.meeshy.app — la version ASC passe à
1.0.1, `apps/ios/project.yml` reste à 1.0.0, et tout build local ou CI produit
un CFBundleShortVersionString en désaccord avec la version qui attend le
binaire. L'écart est silencieux jusqu'au rejet à l'upload.

Deux invariants de conception :

1. **On ne touche QUE la version commerciale.** `CURRENT_PROJECT_VERSION` /
   `CFBundleVersion` ont leur propre cycle (`andp build-number`) et sont laissés
   intacts.
2. **On ne remplace jamais une référence de build setting par un littéral.**
   `<string>$(MARKETING_VERSION)</string>` dans un Info.plist est le montage
   CORRECT : la valeur vient du build setting. L'écraser figerait la version et
   casserait le mécanisme. Seules les valeurs littérales sont réécrites.

Les fonctions `rewrite_*` sont pures (texte -> (texte, n)) donc testables sans
I/O ; seule `sync_marketing_version` touche le disque.
"""
import re
from pathlib import Path

# Apple : 1 à 3 entiers séparés par des points (CFBundleShortVersionString).
# Ni préfixe « v », ni suffixe de pré-version — l'App Store les refuse.
_VERSION_RE = re.compile(r"^\d+(\.\d+){0,2}$")

# Répertoires qui ne contiennent que des artefacts ou des dépendances : y
# réécrire une version serait au mieux inutile, au pire destructeur.
#
# TOUT répertoire caché (commençant par un point) est également écarté — voir
# `_is_skipped`. C'est ce qui protège les worktrees d'agents : sur meeshy,
# `.claude/worktrees/<branche>/apps/ios/project.yml` est une copie de travail
# APPARTENANT À UNE AUTRE SESSION. Y réécrire la version commerciale
# écraserait le travail en cours de quelqu'un d'autre. Constaté le 2026-07-31
# en lançant un dry-run sur le vrai dépôt : deux fichiers de worktree
# apparaissaient dans la liste des cibles.
_SKIP_DIRS = frozenset({
    "node_modules", "Pods", "Carthage", "vendor",
    "Build", "build", "DerivedData", "SourcePackages",
    "__pycache__", "venv", "dist", "fastlane",
})


def _is_skipped(relative_parts):
    """Vrai si l'un des répertoires parents est caché ou exclu."""
    return any(part in _SKIP_DIRS or part.startswith(".")
               for part in relative_parts)


class InvalidVersion(ValueError):
    """La chaîne proposée n'est pas une version App Store valide."""


def _validate(version):
    if not isinstance(version, str) or not _VERSION_RE.match(version.strip()):
        raise InvalidVersion(
            f"{version!r} n'est pas une version App Store valide "
            "(1 à 3 entiers séparés par des points, ex. 1.0.1)")
    return version.strip()


# --- réécritures pures -------------------------------------------------------

_YML_RE = re.compile(
    r"""(?P<head>^[ \t]*MARKETING_VERSION[ \t]*:[ \t]*)(?P<val>"[^"]*"|'[^']*'|[^\s#]+)""",
    re.MULTILINE)


def rewrite_project_yml(text, version):
    """XcodeGen — `MARKETING_VERSION: "1.0.1"`.

    La valeur est TOUJOURS re-écrite entre guillemets : sans eux, YAML lit
    `1.10` comme le flottant 1.1 et la version part fausse.
    """
    version = _validate(version)
    return _YML_RE.subn(lambda m: f'{m.group("head")}"{version}"', text)


_PBX_RE = re.compile(r"(?P<head>\bMARKETING_VERSION[ \t]*=[ \t]*)(?P<val>[^;]*)(?P<tail>;)")


def rewrite_pbxproj(text, version):
    """project.pbxproj — une occurrence par configuration, parfois par cible."""
    version = _validate(version)
    return _PBX_RE.subn(
        lambda m: f'{m.group("head")}{version}{m.group("tail")}', text)


_PLIST_RE = re.compile(
    r"(?P<head><key>CFBundleShortVersionString</key>\s*<string>)"
    r"(?P<val>[^<]*)"
    r"(?P<tail></string>)")


def rewrite_info_plist(text, version):
    """Info.plist — uniquement si la valeur est littérale.

    `$(MARKETING_VERSION)` (ou toute autre référence `$(…)`) est laissé tel
    quel : c'est le montage correct, la valeur venant du build setting.
    """
    version = _validate(version)

    def replace(match):
        if "$(" in match.group("val"):
            return match.group(0)
        return f'{match.group("head")}{version}{match.group("tail")}'

    out, _ = _PLIST_RE.subn(replace, text)
    # subn compte les correspondances, pas les modifications : on recompte.
    return out, (0 if out == text else len(_PLIST_RE.findall(text)))


# Chaque entrée : (nom de fichier ou suffixe, fonction de réécriture).
_HANDLERS = (
    ("project.yml", rewrite_project_yml),
    ("project.yaml", rewrite_project_yml),
    ("project.pbxproj", rewrite_pbxproj),
    ("Info.plist", rewrite_info_plist),
)


def _handler_for(path):
    for name, fn in _HANDLERS:
        if path.name == name:
            return fn
    return None


def discover_version_files(root):
    """Les fichiers du dépôt susceptibles de porter la version commerciale.

    L'élagage se fait PENDANT le parcours (`dirnames[:] = …`), pas après. Un
    `rglob("*")` suivi d'un filtre descendrait quand même dans les répertoires
    exclus : sur meeshy, `apps/ios/Build` pèse 8,7 Go et le scan ne rendait pas
    la main en 2 minutes. Ici les branches mortes ne sont jamais ouvertes.
    """
    import os

    root = Path(root)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Modification IN PLACE : c'est le contrat d'os.walk pour ne pas
        # descendre dans ces répertoires.
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if _handler_for(path) is not None:
                found.append(path)
    return found


def sync_marketing_version(root, version, dry_run=False):
    """Écrit `version` dans tous les fichiers du dépôt qui la portent.

    Retourne une enveloppe agent-friendly. `changed` dit si le disque diffère
    (ou différerait, en dry-run) — un dépôt déjà à jour renvoie changed=False et
    une liste vide, ce qui rend l'appel idempotent.
    """
    root = Path(root)
    try:
        version = _validate(version)
    except InvalidVersion as err:
        return {"command": "sync_marketing_version", "ok": False,
                "dry_run": bool(dry_run),
                "error": {"code": "invalid_version", "message": str(err),
                          "retryable": False,
                          "remediation": "Utiliser 1 à 3 entiers séparés par des points, ex. 1.0.1."}}

    changed_files = []
    for path in discover_version_files(root):
        handler = _handler_for(path)
        try:
            before = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue                      # binaire ou illisible : jamais fatal
        after, count = handler(before, version)
        if count == 0 or after == before:
            continue
        if not dry_run:
            path.write_text(after, encoding="utf-8")
        changed_files.append({
            "path": str(path.relative_to(root)),
            "occurrences": count,
        })

    return {"command": "sync_marketing_version", "ok": True,
            "dry_run": bool(dry_run), "version": version,
            "changed": bool(changed_files), "files": changed_files}
