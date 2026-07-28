"""Où ANDP lit sa configuration — cascade pure, sans I/O au-delà d'os.path.exists.

Ce module ne lève jamais : il décrit ce qu'il trouve. La politique d'erreur
(fichier introuvable, emplacement obsolète) vit dans andp/asc/config.py, ce qui
garde la résolution testable sans monter de contexte d'erreur.

`.andp/` est l'espace runtime non versionné (secrets, state, build, metrics) ;
`andp.yml` reste à la racine du projet, c'est de la config déclarative commitée.
"""
import os
from collections import namedtuple

ANDP_DIR_NAME = ".andp"
ENV_CONFIG_DIR = "ANDP_CONFIG_DIR"   # jamais ANDP_HOME: déjà pris par les workflows
TEMPLATE_NAME = "secrets.example.yml"

Resolution = namedtuple("Resolution", "path origin is_template")

_EMPTY = Resolution(None, None, False)


def andp_dir(project_root="."):
    """Le répertoire runtime: $ANDP_CONFIG_DIR s'il est défini, sinon <root>/.andp."""
    return os.environ.get(ENV_CONFIG_DIR) or os.path.join(project_root, ANDP_DIR_NAME)


def _candidates(filename, project_root):
    """(path, origin) dans l'ordre de priorité, template exclu."""
    env_dir = os.environ.get(ENV_CONFIG_DIR)
    if env_dir:
        yield os.path.join(env_dir, filename), "env"
    yield os.path.join(project_root, ANDP_DIR_NAME, filename), "project"
    yield os.path.join(os.path.expanduser("~"), ANDP_DIR_NAME, filename), "global"


def _template(project_root):
    return os.path.join(project_root, TEMPLATE_NAME)


def resolve_config(filename, project_root="."):
    """Premier trouvé gagne. Renvoie une Resolution; path=None si rien n'existe."""
    for path, origin in _candidates(filename, project_root):
        if os.path.exists(path):
            return Resolution(path, origin, False)
    if filename == "secrets.yml":
        template = _template(project_root)
        if os.path.exists(template):
            return Resolution(template, "template", True)
    return _EMPTY


def misplaced_secrets(project_root="."):
    """Chemin de ./secrets.yml s'il traîne encore à la racine, sinon None.

    Cet emplacement n'est plus un niveau de la cascade; le détecter évite qu'un
    fichier ignoré fasse silencieusement basculer un run en DRY-RUN.
    """
    path = os.path.join(project_root, "secrets.yml")
    return path if os.path.exists(path) else None


def searched_paths(filename, project_root="."):
    """Les emplacements inspectés, pour le bloc `context` d'une erreur typée."""
    out = [path for path, _ in _candidates(filename, project_root)]
    if filename == "secrets.yml":
        out.append(_template(project_root))
    return out


def policy_path(project_root="."):
    """andp.yml — config déclarative versionnée, à la racine, sans cascade."""
    return os.path.join(project_root, "andp.yml")
