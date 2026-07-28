# Espace de nom `.andp/` + taxonomie d'erreurs unifiée — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ANDP résout ses credentials dans l'espace de nom `.andp/` (projet, global, ou `$ANDP_CONFIG_DIR`) et toute erreur de configuration remonte structurée jusqu'à la surface, y compris en mode `--json`.

**Architecture:** Un module feuille `andp/paths.py` porte la cascade de résolution et ne lève jamais ; `andp/asc/config.py` en fait la politique d'erreur. En parallèle, `andp/core/errors.py` remonte en `andp/errors.py` (vocabulaire transverse) et `ConfigError` devient une sous-classe d'`AndpError`, ce qui unifie la taxonomie et rend le bloc de traduction `service.py:26-32` inutile.

**Tech Stack:** Python ≥ 3.9, PyYAML, pytest (< 8.0). Aucune dépendance nouvelle.

**Spec :** `docs/superpowers/specs/2026-07-28-andp-config-namespace-design.md`

## Global Constraints

- **Branche :** `feat/andp-config-namespace` (déjà créée, contient les 2 commits de spec).
- **Baseline :** `python3 -m pytest -q` → `373 passed`. Chaque tâche se termine sur une suite verte.
- **Python ≥ 3.9** — pas de `match`, pas de `X | Y` en annotation, pas de `tomllib`.
- **`andp/paths.py` ne lève jamais.** Il décrit ce qu'il trouve ; la politique d'erreur vit dans `andp/asc/config.py`.
- **Cascade `secrets.yml`, premier trouvé gagne :** `$ANDP_CONFIG_DIR/secrets.yml` (`origin="env"`) → `./.andp/secrets.yml` (`"project"`) → `~/.andp/secrets.yml` (`"global"`) → `./secrets.example.yml` (`"template"`).
- **`./secrets.yml` n'est plus chargé** mais reste détecté → `config_misplaced`.
- **`andp.yml` ne bouge pas** : résolu à `<project_root>/andp.yml`, sans cascade. `andp/policy.py` n'est pas modifié.
- **Variable d'environnement : `ANDP_CONFIG_DIR`.** Jamais `ANDP_HOME`, déjà utilisée par `.github/workflows/andp-release.yml:58-60` pour désigner le checkout du repo.
- **Invariant `--json` :** en mode `--json`, stdout est toujours du JSON valide. Les messages humains vont sur stderr.
- **Codes d'erreur stables :** `config_misplaced`, `config_not_found` — tous deux `retryable: False`.
- **Convention stdout :** pour `andp config path|dir`, stdout ne porte que la valeur ; tout le reste sur stderr (même règle que `build-number`, `asc_manager.py:653`).

---

## Structure des fichiers

**Créés**
- `andp/errors.py` — taxonomie transverse (déplacement de `andp/core/errors.py` + `ConfigError`)
- `andp/paths.py` — cascade de résolution, non-levant
- `tests/test_paths.py` — cascade
- `tests/test_config_namespace.py` — codes d'erreur, non-régression, invariant JSON
- `tests/test_cli_config.py` — sous-commande `andp config`

**Supprimé**
- `andp/core/errors.py` (12 imports repointés)

**Modifiés**
- `andp/asc/config.py` — consomme `paths`, porte `origin`, lève les codes typés
- `andp/asc/asc_manager.py` — `COMMANDS["config"]`, `_cmd_config`, enveloppe JSON en `main()`
- `andp/asc/metadata_manager.py:68` — enveloppe JSON
- `andp/service.py` — suppression de la traduction, imports repointés
- `andp/publish.py:18`, `andp/core/state.py:13`, `andp/core/release.py:21` — imports
- `tests/conftest.py` — helper d'écriture des secrets
- 25 fichiers de tests — consomment le helper
- `sign.sh`, `archive.sh`, `infrastructure/{analytics-manager,security-auditor,governance-report}.sh`
- `action.yml`, `.github/actions/{testflight,appstore}-readiness/action.yml`, `.github/workflows/andp-release.yml`, `Jenkinsfile`, `azure-pipelines.yml`
- `.gitignore` + 12 fichiers de documentation

---

## Task 1: Taxonomie unifiée — `andp/errors.py`

**Files:**
- Create: `andp/errors.py` (via `git mv` depuis `andp/core/errors.py`)
- Delete: `andp/core/errors.py`
- Modify: `andp/service.py:12,24-35,140,214,304,349,442,512,605,654`
- Modify: `andp/publish.py:18`, `andp/core/state.py:13`, `andp/core/release.py:21`
- Modify: `andp/asc/config.py:20` (la classe locale devient un ré-export)
- Test: `tests/test_errors_taxonomy.py`

**Interfaces:**
- Consumes: rien (première tâche)
- Produces: `andp.errors.AndpError` (dataclass : `code`, `message`, `retryable`, `remediation`, méthode `to_dict()`), `andp.errors.ConfigError(message, code="config_error", remediation="", context=None)` avec `to_dict()` incluant `context` s'il est non vide. `andp.asc.config.ConfigError` reste importable (ré-export).

**Pourquoi en premier :** sans taxonomie unifiée, les tâches 4 et 5 devraient inventer un transport pour les codes d'erreur, qu'il faudrait ensuite défaire.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_errors_taxonomy.py` :

```python
"""ConfigError appartient à la taxonomie typée — un agent lit un seul type d'erreur."""
import pytest

from andp.errors import AndpError, ConfigError


def test_config_error_is_an_andp_error():
    err = ConfigError("boom", code="config_misplaced", remediation="fix it")
    assert isinstance(err, AndpError)
    assert err.code == "config_misplaced"
    assert err.remediation == "fix it"


def test_config_error_is_never_retryable():
    assert ConfigError("boom").to_dict()["retryable"] is False


def test_config_error_defaults_to_generic_code():
    assert ConfigError("boom").code == "config_error"


def test_context_is_absent_when_empty():
    assert "context" not in ConfigError("boom").to_dict()


def test_context_is_carried_into_the_envelope():
    err = ConfigError("boom", context={"searched": ["a", "b"]})
    assert err.to_dict()["context"] == {"searched": ["a", "b"]}


def test_caught_by_the_generic_handler():
    """C'est ce qui rend la traduction de service.py inutile."""
    with pytest.raises(AndpError):
        raise ConfigError("boom")


def test_config_module_still_exports_config_error():
    """Les 4 sites qui font `from .config import ConfigError` ne cassent pas."""
    from andp.asc.config import ConfigError as Reexported
    assert Reexported is ConfigError
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_errors_taxonomy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'andp.errors'`

- [ ] **Step 3: Move the module**

```bash
git mv andp/core/errors.py andp/errors.py
```

- [ ] **Step 4: Add ConfigError to `andp/errors.py`**

Ajouter juste après la classe `AndpError` (donc après sa méthode `to_dict()`, avant `_STATUS_MAP`) :

```python
class ConfigError(AndpError):
    """Configuration error — an AndpError that is never retryable.

    Subclassing keeps a single taxonomy: `except AndpError` catches it, and
    to_dict() makes it serialisable without any ad-hoc conversion. `context`
    carries what was inspected (searched paths, misplaced file) so an agent can
    remediate without re-running the command to explore.
    """

    def __init__(self, message, code="config_error", remediation="", context=None):
        super().__init__(code=code, message=message,
                         retryable=False, remediation=remediation)
        self.context = context or {}

    def to_dict(self):
        payload = super().to_dict()
        if self.context:
            payload["context"] = self.context
        return payload
```

- [ ] **Step 5: Repoint the 12 imports**

Dans `andp/service.py`, remplacer aux lignes 12, 140, 214, 304, 349, 442, 512, 605, 654 :
`from .core.errors import` → `from .errors import`

Dans `andp/publish.py:18` : `from .core.errors import AndpError` → `from .errors import AndpError`

Dans `andp/core/state.py:13` : `from .errors import AndpError` → `from ..errors import AndpError`

Dans `andp/core/release.py:21` : `from .errors import AndpError, from_asc_error, from_unexpected` → `from ..errors import AndpError, from_asc_error, from_unexpected`

Vérifier qu'aucun n'a été oublié :

```bash
grep -rn "core.errors\|core import errors" --include="*.py" andp/ tests/ | grep -v __pycache__
```
Expected: aucune sortie.

- [ ] **Step 6: Turn the local ConfigError into a re-export**

Dans `andp/asc/config.py`, remplacer la définition locale (ligne 20) :

```python
class ConfigError(Exception):
    """Raised when secrets are missing or malformed."""
```

par un import en tête de fichier, sous `import yaml` :

```python
from ..errors import ConfigError  # noqa: F401  (re-exported for existing importers)
```

`asc_manager.py:19` et `metadata_manager.py:16` font `from .config import ConfigError` — ce ré-export les préserve.

- [ ] **Step 7: Run the new test**

Run: `python3 -m pytest tests/test_errors_taxonomy.py -q`
Expected: PASS (7 tests)

- [ ] **Step 8: Remove the now-dead translation in `service.py`**

Remplacer `_managers_for` (lignes 24-35) :

```python
def _managers_for(account_id):
    """Return (managers, account, dry_run). managers is None in dry-run.
    Raises AndpError (not ConfigError) so callers have one error type to catch."""
    from .asc.config import ConfigError
    try:
        account = load_account(account_id)
    except ConfigError as exc:
        raise AndpError(code="config_error", message=str(exc), retryable=False,
                        remediation="Check secrets.yml and the --account name.")
    if not account.is_configured():
        return None, account, True
    return make_managers(account), account, False
```

par :

```python
def _managers_for(account_id):
    """Return (managers, account, dry_run). managers is None in dry-run.

    ConfigError is an AndpError (andp/errors.py), so callers already have one
    error type to catch — no translation needed, and the typed code survives.
    """
    account = load_account(account_id)
    if not account.is_configured():
        return None, account, True
    return make_managers(account), account, False
```

- [ ] **Step 9: Run the full suite**

Run: `python3 -m pytest -q`
Expected: `374 passed` (373 baseline + 7 nouveaux − 6 … vérifier le total réel ; aucun échec n'est acceptable)

Si un test échoue sur un message d'erreur : `AndpError.__post_init__` préfixe `str(exc)` par `[code] `, donc `str(ConfigError("boom"))` vaut désormais `"[config_error] boom"` au lieu de `"boom"`. Les assertions `match=` sur une sous-chaîne (ex. `test_config.py:56`, `match="unknown-account"`) restent vertes ; une assertion d'égalité stricte devrait être ajustée pour cibler `exc.message`.

- [ ] **Step 10: Commit**

```bash
git add andp/errors.py andp/asc/config.py andp/service.py andp/publish.py \
        andp/core/state.py andp/core/release.py tests/test_errors_taxonomy.py
git add -u andp/core/errors.py
git commit -m "refactor(errors): remonter la taxonomie en andp/errors.py et y faire entrer ConfigError

errors.py est du vocabulaire transverse, pas de la logique core, et la
dépendance va core -> asc (core/release.py:17,21) : le laisser dans core/
imposait une dépendance bidirectionnelle entre packages.

ConfigError hérite d'AndpError, ce qui rend le bloc de traduction de
_managers_for inutile — une seule taxonomie, to_dict() partout, et le
champ context prêt pour le diagnostic agent."
```

---

## Task 2: Module de résolution `andp/paths.py`

**Files:**
- Create: `andp/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Consumes: rien
- Produces:
  - `ANDP_DIR_NAME = ".andp"`, `ENV_CONFIG_DIR = "ANDP_CONFIG_DIR"`
  - `Resolution = namedtuple("Resolution", "path origin is_template")`
  - `andp_dir(project_root=".") -> str`
  - `resolve_config(filename, project_root=".") -> Resolution`
  - `misplaced_secrets(project_root=".") -> str | None`
  - `searched_paths(filename, project_root=".") -> list[str]`
  - `policy_path(project_root=".") -> str`

- [ ] **Step 1: Write the failing test**

Créer `tests/test_paths.py` :

```python
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


def test_priority_env_over_project_over_global_over_template(tmp_path, isolated_home, monkeypatch):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_paths.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'andp.paths'`

- [ ] **Step 3: Write the implementation**

Créer `andp/paths.py` :

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_paths.py -q`
Expected: PASS (15 tests)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: aucun échec — `paths.py` n'est encore consommé par personne.

- [ ] **Step 6: Commit**

```bash
git add andp/paths.py tests/test_paths.py
git commit -m "feat(paths): cascade de résolution .andp/ (env, projet, global, template)

Module feuille et non-levant: il décrit ce qu'il trouve, la politique d'erreur
reste dans asc/config.py. Pas encore consommé — la bascule est l'étape suivante."
```

---

## Task 3: Centraliser l'écriture des secrets dans les tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: les 25 fichiers de tests listés au Step 3

**Interfaces:**
- Consumes: rien
- Produces: `conftest.write_secrets(tmp_path, content) -> pathlib.Path` — écrit les credentials **là où ANDP les lit**. Un seul site à modifier en Task 4.

**Pourquoi cette tâche existe :** basculer `config.py` sur la cascade casserait d'un coup les 25 fixtures qui écrivent `tmp_path/"secrets.yml"`. En les faisant d'abord passer par un helper — dont le comportement reste **identique** à cette étape — la bascule de Task 4 devient un changement d'une ligne, et cette tâche-ci est vérifiable par une suite qui reste verte sans qu'aucun comportement n'ait bougé.

- [ ] **Step 1: Add the helper to `tests/conftest.py`**

Ajouter juste après la fonction `real_secrets_yaml` :

```python
def write_secrets(tmp_path, content):
    """Écrit les credentials à l'emplacement qu'ANDP lit.

    Un seul site à changer quand l'emplacement bouge — c'est tout l'intérêt.
    """
    path = tmp_path / "secrets.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path
```

- [ ] **Step 2: Route the shared fixture through it**

Dans `tests/conftest.py`, remplacer le corps de `configured_dir` (ligne ~110) :

```python
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
```

par :

```python
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
```

- [ ] **Step 3: Route every other write through it**

Lister les sites restants :

```bash
grep -rn '"secrets.yml"' tests/ | grep -v "secrets_file\|write_secrets"
```

Dans chaque fichier listé, remplacer le motif :

```python
(tmp_path / "secrets.yml").write_text(CONTENU)
```

par :

```python
write_secrets(tmp_path, CONTENU)
```

en ajoutant l'import nécessaire en tête du fichier (le `conftest.py` racine est sur le `sys.path` de pytest) :

```python
from conftest import write_secrets
```

Fichiers concernés : `test_service_ship.py:28`, `test_service.py:32`, `test_mcp_store.py:22`, `test_cli_release_sub.py:24,57`, `test_readiness_service.py:8,37,76`, `test_service_buildnum.py:41,56,70,79,108`, `test_publish_hardening.py:70`, `test_submit_attaches_build.py:13`, `test_asc_manager_cli.py:140`, `test_mcp_v2.py:73,97,128`, `test_hardening.py:182`, `test_buildnum_cli.py:42`, `test_precheck_cli.py:11`, `test_ship_hardening.py:190,204`, `test_store_cli.py:17`, `test_service_store.py:17`, `test_readiness_cli.py:11,20`, `test_mcp_ship.py:39`, `test_asc_verify.py:28,116`, `test_json_output.py:50`, `test_verify_service.py:141,151`, `test_publish_cli.py:19,48`.

**Ne pas toucher** aux sites qui écrivent `secrets.example.yml` (le template garde sa place à la racine), ni à `tests/test_config.py` qui passe par `secrets_file=` et court-circuite la cascade.

- [ ] **Step 4: Run the full suite — nothing must change**

Run: `python3 -m pytest -q`
Expected: même total qu'à la fin de Task 2, aucun échec. Le helper écrit encore au même endroit : c'est un refactor à comportement constant.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: centraliser l'écriture des secrets derrière conftest.write_secrets

Comportement inchangé. Prépare la bascule vers .andp/secrets.yml, qui devient
un changement d'une ligne au lieu de 25 fichiers."
```

---

## Task 4: `config.py` consomme la cascade

**Files:**
- Modify: `andp/asc/config.py:47-60`
- Modify: `tests/conftest.py` (une ligne — le helper bascule)
- Test: `tests/test_config_namespace.py`

**Interfaces:**
- Consumes: `andp.paths.{resolve_config, misplaced_secrets, searched_paths}` (Task 2), `andp.errors.ConfigError` (Task 1), `conftest.write_secrets` (Task 3)
- Produces: `load_account(account_id, secrets_file=None, project_root=".")` lève `ConfigError` avec `code="config_misplaced"` ou `code="config_not_found"` ; `AccountConfig` porte l'attribut `origin` (str ou `None`).

- [ ] **Step 1: Write the failing test**

Créer `tests/test_config_namespace.py` :

```python
"""Résolution .andp/ — et surtout: plus jamais de bascule DRY-RUN silencieuse."""
import pytest

from andp.asc.config import load_account
from andp.errors import ConfigError
from conftest import real_secrets_yaml, write_secrets

PLACEHOLDERS = """
accounts:
  primary:
    asc_api:
      key_id: "ABCDE12345"
      issuer_id: "REPLACE_WITH_ISSUER_ID"
      key_content: "PRIMARY_KEY_CONTENT"
"""


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    return home


def test_reads_from_the_project_namespace(tmp_path, monkeypatch, ec_private_key_pem):
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    account = load_account("primary")
    assert account.is_configured() is True
    assert account.origin == "project"


def test_reads_from_the_global_namespace(tmp_path, monkeypatch, isolated_home,
                                         ec_private_key_pem):
    write_secrets(isolated_home, real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    account = load_account("primary")
    assert account.is_configured() is True
    assert account.origin == "global"


def test_root_secrets_never_silently_falls_back_to_template(tmp_path, monkeypatch,
                                                            ec_private_key_pem):
    """Le bug d'origine: 15 min de build, puis un upload en DRY-RUN silencieux."""
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    (tmp_path / "secrets.example.yml").write_text(PLACEHOLDERS)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError) as excinfo:
        load_account("primary")
    assert excinfo.value.code == "config_misplaced"
    assert excinfo.value.remediation


def test_misplaced_is_raised_even_when_another_level_resolves(tmp_path, monkeypatch,
                                                              ec_private_key_pem):
    """Deux fichiers concurrents: on signale plutôt que de trancher en silence."""
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError) as excinfo:
        load_account("primary")
    assert excinfo.value.code == "config_misplaced"


def test_nothing_anywhere_raises_config_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as excinfo:
        load_account("primary")
    assert excinfo.value.code == "config_not_found"


def test_error_context_lists_the_searched_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as excinfo:
        load_account("primary")
    context = excinfo.value.to_dict()["context"]
    assert context["resolved"] is None
    assert any(p.endswith(".andp/secrets.yml") for p in context["searched"])


def test_template_still_yields_a_dry_run_account(tmp_path, monkeypatch):
    """Les PR de fork restent vertes: le template garde son rôle."""
    (tmp_path / "secrets.example.yml").write_text(PLACEHOLDERS)
    monkeypatch.chdir(tmp_path)
    account = load_account("primary")
    assert account.is_configured() is False
    assert account.origin == "template"


def test_explicit_secrets_file_bypasses_the_cascade(tmp_path, ec_private_key_pem):
    path = tmp_path / "anywhere.yml"
    path.write_text(real_secrets_yaml(ec_private_key_pem))
    account = load_account("primary", secrets_file=str(path))
    assert account.is_configured() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config_namespace.py -q`
Expected: FAIL — `AttributeError: 'AccountConfig' object has no attribute 'origin'` et les codes d'erreur absents.

- [ ] **Step 3: Add `origin` to `AccountConfig`**

Dans `andp/asc/config.py`, modifier la signature du constructeur :

```python
    def __init__(self, account_id, key_id, issuer_id, key_content, team_id=None,
                 raw=None, origin=None):
        self.account_id = account_id
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.key_content = key_content
        self.team_id = team_id
        self.raw = raw or {}
        self.origin = origin
```

`origin` est en dernier et par défaut `None` : `asc_manager.py:748` construit un `AccountConfig(account_id, None, None, None)` positionnel, il n'est pas affecté.

- [ ] **Step 4: Replace the resolution in `load_account`**

Remplacer les lignes 47-55 :

```python
def load_account(account_id, secrets_file=None):
    path = secrets_file
    if path is None:
        path = "secrets.yml" if os.path.exists("secrets.yml") else "secrets.example.yml"
    if not os.path.exists(path):
        raise ConfigError(f"No secrets file found (looked for {path})")
```

par :

```python
def load_account(account_id, secrets_file=None, project_root="."):
    if secrets_file is not None:
        path, origin = secrets_file, "explicit"
        if not os.path.exists(path):
            raise ConfigError(
                f"No secrets file found (looked for {path})",
                code="config_not_found",
                remediation="Pass an existing path, or drop the secrets_file argument.")
    else:
        misplaced = paths.misplaced_secrets(project_root)
        if misplaced:
            raise ConfigError(
                f"secrets.yml trouvé à la racine du projet ({misplaced}), mais ANDP "
                "ne lit plus cet emplacement.",
                code="config_misplaced",
                remediation="mkdir -p .andp && mv secrets.yml .andp/secrets.yml "
                            "(ou : andp config migrate)",
                context={"misplaced": misplaced,
                         "searched": paths.searched_paths("secrets.yml", project_root)})
        resolution = paths.resolve_config("secrets.yml", project_root)
        if resolution.path is None:
            raise ConfigError(
                "Aucun fichier de credentials trouvé.",
                code="config_not_found",
                remediation="Créez .andp/secrets.yml à partir de secrets.example.yml.",
                context={"resolved": None,
                         "searched": paths.searched_paths("secrets.yml", project_root)})
        path, origin = resolution.path, resolution.origin
```

Ajouter l'import en tête de fichier, sous `import yaml` :

```python
from .. import paths
```

- [ ] **Step 5: Carry `origin` into the returned account**

Dans le `return AccountConfig(...)` en fin de `load_account`, ajouter le paramètre :

```python
        raw=account,
        origin=origin,
    )
```

Et dans le `raise ConfigError` du compte introuvable (ligne ~63), ajouter le code typé :

```python
        raise ConfigError(f"Account '{account_id}' not found in {path}",
                          code="account_not_found",
                          remediation="Check the --account name against the accounts "
                                      "block of the secrets file.")
```

- [ ] **Step 6: Flip the test helper to the new location**

Dans `tests/conftest.py`, dans `write_secrets`, remplacer :

```python
    path = tmp_path / "secrets.yml"
```

par :

```python
    path = tmp_path / ".andp" / "secrets.yml"
```

C'est le seul changement nécessaire côté tests — d'où la Task 3.

- [ ] **Step 7: Run the new test**

Run: `python3 -m pytest tests/test_config_namespace.py -q`
Expected: PASS (8 tests)

- [ ] **Step 8: Run the full suite**

Run: `python3 -m pytest -q`
Expected: aucun échec.

Deux échecs sont attendus et doivent être corrigés dans cette tâche :
- `tests/test_config.py:60` (`test_missing_file_falls_back_to_example`) reste vert — le template est toujours le dernier niveau.
- Tout test qui posait un `secrets.yml` à la racine **et** attendait un chargement doit désormais utiliser `write_secrets`. S'il en reste, le message `config_misplaced` le désigne explicitement.

- [ ] **Step 9: Commit**

```bash
git add andp/asc/config.py tests/
git commit -m "feat(config): lire les credentials depuis .andp/ et refuser l'ancien emplacement

Cascade: \$ANDP_CONFIG_DIR, ./.andp, ~/.andp, puis le template. ./secrets.yml
n'est plus chargé mais reste détecté (config_misplaced): le retirer sans le
détecter aurait reproduit la bascule DRY-RUN silencieuse qu'on corrige."
```

---

## Task 5: Invariant `--json`

**Files:**
- Modify: `andp/asc/asc_manager.py:742-751`
- Modify: `andp/asc/metadata_manager.py:65-69`
- Test: `tests/test_config_json_envelope.py`

**Interfaces:**
- Consumes: `ConfigError.to_dict()` (Task 1), les codes typés (Task 4)
- Produces: en mode `--json`, `main()` imprime `{"command": str, "ok": false, "error": {...}}` sur stdout et retourne 1.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_config_json_envelope.py` :

```python
"""En --json, stdout est toujours du JSON — y compris sans configuration.

Un agent qui ne peut pas parser stdout perd le code, retryable et la remediation:
il ne sait ni ce qui a échoué, ni s'il doit réessayer.
"""
import json

import pytest

from andp.asc.asc_manager import main


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("argv", [
    ["verify"],
    ["upload", "app.ipa"],
    ["status", "me.app", "42"],
    ["submit", "me.app", "1.0"],
    ["precheck", "me.app", "1.0"],
    ["readiness", "testflight", "me.app"],
    ["store", "apply", "me.app"],
])
def test_json_stays_parsable_without_any_config(argv, capsys):
    rc = main(argv + ["--json"])
    payload = json.loads(capsys.readouterr().out)      # ne doit pas lever
    assert rc == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "config_not_found"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["remediation"]


def test_json_envelope_for_a_misplaced_file(tmp_path, capsys):
    (tmp_path / "secrets.yml").write_text("accounts: {}\n")
    rc = main(["verify", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "config_misplaced"
    assert payload["error"]["context"]["misplaced"].endswith("secrets.yml")


def test_human_mode_keeps_stdout_clean(capsys):
    """Le message humain va sur stderr — stdout reste réservé aux données."""
    rc = main(["verify"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "config" in captured.err.lower() or "secrets" in captured.err.lower()


def test_build_number_still_runs_without_credentials(capsys):
    """L'exception existante ne doit pas être régressée par l'enveloppe."""
    rc = main(["build-number", "--strategy", "timestamp"])
    assert rc == 0
    assert capsys.readouterr().out.strip().isdigit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config_json_envelope.py -q`
Expected: FAIL — `json.decoder.JSONDecodeError`, stdout contenant `Error: ...` en texte brut.

- [ ] **Step 3: Serialise the envelope in `main()`**

Dans `andp/asc/asc_manager.py`, remplacer le bloc lignes 742-751 :

```python
    try:
        account = load_account(account_id)
    except ConfigError as exc:
        # `build-number` (timestamp/commit) needs no credentials at all — let it
        # run in a repo with no secrets file. Every other command still fails.
        if command == "build-number":
            account = AccountConfig(account_id, None, None, None)
        else:
            print(f"Error: {exc}")
            return 1
```

par :

```python
    try:
        account = load_account(account_id)
    except ConfigError as exc:
        # `build-number` (timestamp/commit) needs no credentials at all — let it
        # run in a repo with no secrets file. Every other command still fails.
        if command == "build-number":
            account = AccountConfig(account_id, None, None, None)
        elif json_mode:
            # stdout must stay parsable: an agent reads code/retryable/remediation
            # from here, and gets nothing usable from a bare error line.
            print(json.dumps({"command": command, "ok": False,
                              "error": exc.to_dict()}))
            return 1
        else:
            print(f"❌ {exc.message}", file=sys.stderr)
            if exc.remediation:
                print(f"   → {exc.remediation}", file=sys.stderr)
            return 1
```

`json` et `sys` sont déjà importés en tête du module.

- [ ] **Step 4: Apply the same fix to `metadata_manager.py`**

Remplacer les lignes 65-69 :

```python
    try:
        account = load_account(account_id)
    except ConfigError as exc:
        print(f"Error: {exc}")
        return 1
```

par :

```python
    try:
        account = load_account(account_id)
    except ConfigError as exc:
        print(f"❌ {exc.message}", file=sys.stderr)
        if exc.remediation:
            print(f"   → {exc.remediation}", file=sys.stderr)
        return 1
```

Vérifier que `import sys` figure en tête de `metadata_manager.py` ; l'ajouter sinon.

- [ ] **Step 5: Run the new test**

Run: `python3 -m pytest tests/test_config_json_envelope.py -q`
Expected: PASS (10 tests)

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: aucun échec. Un test qui asserte l'ancien texte `Error: ...` sur **stdout** doit être migré vers `capsys.readouterr().err`.

- [ ] **Step 7: Commit**

```bash
git add andp/asc/asc_manager.py andp/asc/metadata_manager.py tests/test_config_json_envelope.py
git commit -m "fix(cli): sérialiser les erreurs de config dans l'enveloppe JSON

\`andp verify --json\` sans credentials imprimait 'Error: ...' en texte brut sur
stdout: json.loads() levait et l'agent perdait code, retryable et remediation.
Le message humain passe sur stderr, stdout reste réservé aux données."
```

---

## Task 6: Sous-commande `andp config`

**Files:**
- Modify: `andp/asc/asc_manager.py` (USAGE, `_cmd_config`, `COMMANDS`, exception credentials)
- Test: `tests/test_cli_config.py`

**Interfaces:**
- Consumes: `andp.paths.*` (Task 2), `AccountConfig.origin` (Task 4)
- Produces: `andp config`, `andp config path secrets|policy`, `andp config dir`, `andp config migrate`.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_cli_config.py` :

```python
"""`andp config` — expose la résolution au shell et diagnostique sans credentials."""
import json
import os
import stat

import pytest

from andp.asc.asc_manager import main
from conftest import real_secrets_yaml, write_secrets


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_path_secrets_prints_only_the_path(isolated, capsys, ec_private_key_pem):
    expected = write_secrets(isolated, real_secrets_yaml(ec_private_key_pem))
    rc = main(["config", "path", "secrets"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == str(expected)   # substitution shell sûre


def test_path_secrets_exits_1_when_unresolved(isolated, capsys):
    rc = main(["config", "path", "secrets"])
    assert rc == 1
    assert capsys.readouterr().out.strip() == ""


def test_path_policy_has_no_cascade(isolated, capsys):
    rc = main(["config", "path", "policy"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == os.path.join(str(isolated), "andp.yml")


def test_path_rejects_an_unknown_target(isolated, capsys):
    assert main(["config", "path", "nope"]) == 2


def test_dir_prints_the_runtime_directory(isolated, capsys):
    rc = main(["config", "dir"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == os.path.join(str(isolated), ".andp")


def test_dir_honours_the_env_var(isolated, monkeypatch, capsys):
    monkeypatch.setenv("ANDP_CONFIG_DIR", "/custom/place")
    main(["config", "dir"])
    assert capsys.readouterr().out.strip() == "/custom/place"


def test_config_runs_without_any_credentials(isolated, capsys):
    """Comme build-number: diagnostiquer une config absente ne peut pas exiger
    une config présente."""
    rc = main(["config"])
    assert rc == 0
    assert "secrets" in capsys.readouterr().out


def test_json_diagnostic_reports_origin(isolated, capsys, ec_private_key_pem):
    write_secrets(isolated, real_secrets_yaml(ec_private_key_pem))
    main(["config", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["secrets"]["origin"] == "project"
    assert payload["secrets"]["configured"] is True


def test_migrate_moves_the_file_with_safe_modes(isolated, capsys, ec_private_key_pem):
    legacy = isolated / "secrets.yml"
    legacy.write_text(real_secrets_yaml(ec_private_key_pem))
    rc = main(["config", "migrate"])
    target = isolated / ".andp" / "secrets.yml"

    assert rc == 0
    assert not legacy.exists()
    assert target.exists()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE((isolated / ".andp").stat().st_mode) == 0o700


def test_migrate_refuses_to_overwrite(isolated, capsys, ec_private_key_pem):
    (isolated / "secrets.yml").write_text("legacy\n")
    write_secrets(isolated, real_secrets_yaml(ec_private_key_pem))
    rc = main(["config", "migrate"])
    assert rc == 1
    assert (isolated / "secrets.yml").exists()      # rien n'a été détruit


def test_migrate_is_idempotent(isolated, capsys):
    assert main(["config", "migrate"]) == 0
    assert main(["config", "migrate"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli_config.py -q`
Expected: FAIL — la commande `config` est inconnue, `main` retourne 2 et imprime l'usage.

- [ ] **Step 3: Implement `_cmd_config`**

Ajouter dans `andp/asc/asc_manager.py`, juste avant le dict `COMMANDS` :

```python
_CONFIG_USAGE = ("Usage: config [path <secrets|policy> | dir | migrate] "
                 "[--account <id>] [--json]")


def _config_diagnostic(account_id, project_root="."):
    """L'état résolu de la configuration — la donnée derrière `andp config`."""
    from .. import paths

    resolution = paths.resolve_config("secrets.yml", project_root)
    misplaced = paths.misplaced_secrets(project_root)
    configured = False
    if resolution.path and not misplaced:
        try:
            configured = load_account(account_id, project_root=project_root).is_configured()
        except ConfigError:
            configured = False

    policy = paths.policy_path(project_root)
    return {
        "command": "config",
        "ok": misplaced is None,
        "account": account_id,
        "dir": paths.andp_dir(project_root),
        "secrets": {"path": resolution.path, "origin": resolution.origin,
                    "configured": configured,
                    "searched": paths.searched_paths("secrets.yml", project_root)},
        "policy": {"path": policy, "present": os.path.exists(policy)},
        "misplaced": misplaced,
    }


def _print_config_human(diag):
    print(f"ANDP config (account '{diag['account']}')")
    print(f"  dir       {diag['dir']}")
    secrets = diag["secrets"]
    if secrets["path"]:
        state = "✅ configured" if secrets["configured"] else "⚪ dry-run"
        print(f"  secrets   {secrets['path']}   {secrets['origin']}   {state}")
    else:
        print("  secrets   (aucun)   — cherché dans :")
        for candidate in secrets["searched"]:
            print(f"              {candidate}")
    policy = diag["policy"]
    print(f"  policy    {policy['path']}   {'present' if policy['present'] else 'absent'}")
    if diag["misplaced"]:
        print(f"\n❌ {diag['misplaced']} n'est plus lu par ANDP.", file=sys.stderr)
        print("   → andp config migrate", file=sys.stderr)


def _cmd_config_migrate(project_root="."):
    """Déplace ./secrets.yml vers .andp/secrets.yml. N'écrase jamais."""
    from .. import paths

    legacy = paths.misplaced_secrets(project_root)
    if legacy is None:
        print("Rien à migrer : aucun secrets.yml à la racine.", file=sys.stderr)
        return 0

    target_dir = paths.andp_dir(project_root)
    target = os.path.join(target_dir, "secrets.yml")
    if os.path.exists(target):
        print(f"❌ {target} existe déjà — migration refusée pour ne rien écraser.",
              file=sys.stderr)
        print(f"   → comparez les deux fichiers, puis supprimez {legacy}.",
              file=sys.stderr)
        return 1

    os.makedirs(target_dir, mode=0o700, exist_ok=True)
    os.chmod(target_dir, 0o700)
    os.rename(legacy, target)
    os.chmod(target, 0o600)
    print(f"✅ {legacy} → {target}", file=sys.stderr)
    return 0


def _cmd_config(account, managers, dry_run, args, json_mode=False):
    """Résolution de configuration — sans credentials, par construction."""
    from .. import paths

    args = list(args)
    sub = args[0] if args else None

    if sub == "migrate":
        return _cmd_config_migrate()

    if sub == "path":
        target = args[1] if len(args) > 1 else None
        if target == "secrets":
            resolution = paths.resolve_config("secrets.yml")
            if resolution.path is None:
                print("Aucun fichier de credentials résolu.", file=sys.stderr)
                return 1
            print(resolution.path)          # stdout ne porte que la valeur
            return 0
        if target == "policy":
            print(paths.policy_path())
            return 0
        print(_CONFIG_USAGE, file=sys.stderr)
        return 2

    if sub == "dir":
        print(paths.andp_dir())
        return 0

    if sub is not None:
        print(_CONFIG_USAGE, file=sys.stderr)
        return 2

    diag = _config_diagnostic(account.account_id)
    if json_mode:
        print(json.dumps(diag))
        return 0
    _print_config_human(diag)
    return 0
```

- [ ] **Step 4: Register the command**

Ajouter l'entrée au dict `COMMANDS` :

```python
    "config": _cmd_config,
```

Ajouter la ligne d'usage dans `USAGE`, après celle de `build-number` :

```
  config [path <secrets|policy>|dir|migrate]     Where ANDP reads its configuration
```

- [ ] **Step 5: Exempt `config` from the credential requirement**

Dans `main()`, la clause qui tolère `ConfigError` ne vise que `build-number`. L'étendre :

```python
        if command in ("build-number", "config"):
            account = AccountConfig(account_id, None, None, None)
```

Vérifier que le commentaire au-dessus est mis à jour pour mentionner les deux commandes.

- [ ] **Step 6: Run the new test**

Run: `python3 -m pytest tests/test_cli_config.py -q`
Expected: PASS (11 tests)

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest -q`
Expected: aucun échec.

- [ ] **Step 8: Commit**

```bash
git add andp/asc/asc_manager.py tests/test_cli_config.py
git commit -m "feat(cli): andp config — path, dir, migrate et diagnostic

Expose la cascade au shell (sign.sh, meeshy.sh) pour qu'aucun consommateur ne
réimplémente la résolution — c'est la duplication Python/bash qui avait produit
le bug d'origine. migrate n'écrase jamais et pose 0700/0600."
```

---

## Task 7: Scripts shell

**Files:**
- Modify: `sign.sh:11,25,...`, `archive.sh:12`
- Modify: `artifact-manager.sh:8`
- Modify: `infrastructure/analytics-manager.sh:8`
- Modify: `infrastructure/security-auditor.sh:36-39`
- Modify: `infrastructure/governance-report.sh:59-60`
- Modify: `infrastructure/tests/run_tests.sh:53`

**Interfaces:**
- Consumes: `andp config path secrets`, `andp config dir` (Task 6)
- Produces: artefacts sous `.andp/build/`, métriques sous `.andp/metrics/`

- [ ] **Step 1: Add the CLI helper to `sign.sh`**

En tête de `sign.sh`, après `set -e` :

```bash
# Le binaire `andp` n'est pas garanti dans le PATH des runners — les workflows
# utilisent déjà `python3 -m andp` (action.yml:53).
andp_cli() { command -v andp >/dev/null 2>&1 && andp "$@" || python3 -m andp "$@"; }
```

- [ ] **Step 2: Fix the broken secrets read in `sign.sh`**

Remplacer la ligne 25 :

```bash
TEAM_ID=$(python3 -c "import yaml, sys; loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader); data = yaml.load(open('secrets.yml' if sys.path[0]+'/secrets.yml' else 'secrets.example.yml'), Loader=loader); print(data.get('accounts', {}).get('$ACCOUNT', {}).get('signing', {}).get('development_team', 'REPLACE_WITH_TEAM_ID'))" 2>/dev/null || echo "REPLACE_WITH_TEAM_ID")
```

par :

```bash
# La condition d'origine (`'secrets.yml' if sys.path[0]+'/secrets.yml' else ...`)
# était une concaténation de chaînes, toujours vraie: le fallback était mort.
SECRETS_PATH=$(andp_cli config path secrets 2>/dev/null || true)
if [ -n "$SECRETS_PATH" ]; then
    TEAM_ID=$(SECRETS_PATH="$SECRETS_PATH" python3 -c "
import os, yaml
loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
with open(os.environ['SECRETS_PATH']) as f:
    data = yaml.load(f, Loader=loader) or {}
account = (data.get('accounts', {}) or {}).get('$ACCOUNT', {}) or {}
print((account.get('signing', {}) or {}).get('development_team', 'REPLACE_WITH_TEAM_ID'))
" 2>/dev/null || echo "REPLACE_WITH_TEAM_ID")
else
    TEAM_ID="REPLACE_WITH_TEAM_ID"
fi
```

- [ ] **Step 3: Move the build artefacts**

Dans `sign.sh`, remplacer :

```bash
EXPORT_PATH="build/exported"
EXPORT_OPTIONS_PLIST="infrastructure/build/ExportOptions_$ACCOUNT.plist"
```

par :

```bash
ANDP_DIR=$(andp_cli config dir 2>/dev/null || echo ".andp")
EXPORT_PATH="$ANDP_DIR/build/exported"
EXPORT_OPTIONS_PLIST="$ANDP_DIR/build/ExportOptions_$ACCOUNT.plist"
```

et remplacer le `mkdir -p infrastructure/build` par `mkdir -p "$ANDP_DIR/build"`.

Dans `archive.sh`, remplacer :

```bash
ARCHIVE_PATH="$ROOT_DIR/build/$SCHEME.xcarchive"
```

par :

```bash
ARCHIVE_PATH="${ANDP_CONFIG_DIR:-$ROOT_DIR/.andp}/build/$SCHEME.xcarchive"
```

et le `mkdir -p build` par `mkdir -p "$(dirname "$ARCHIVE_PATH")"`.

- [ ] **Step 4: Move metrics and artifacts**

Dans `infrastructure/analytics-manager.sh`, remplacer la ligne 8 :

```bash
METRICS_DIR="metrics"
```

par :

```bash
METRICS_DIR="${ANDP_CONFIG_DIR:-.andp}/metrics"
```

Dans `artifact-manager.sh`, remplacer la ligne 8 :

```bash
ARTIFACTS_DIR="artifacts"
```

par :

```bash
ARTIFACTS_DIR="${ANDP_CONFIG_DIR:-.andp}/artifacts"
```

`infrastructure/tests/run_tests.sh:53` vérifie la présence des artefacts par chemin
codé en dur et casserait sans cela. Remplacer :

```bash
if [ -f "artifacts/app.ipa" ] && [ -f "artifacts/Meeshy.dmg" ] && [ -f "artifacts/Meeshy.pkg" ]; then
```

par :

```bash
ARTIFACTS_DIR="${ANDP_CONFIG_DIR:-.andp}/artifacts"
if [ -f "$ARTIFACTS_DIR/app.ipa" ] && [ -f "$ARTIFACTS_DIR/Meeshy.dmg" ] && [ -f "$ARTIFACTS_DIR/Meeshy.pkg" ]; then
```

Vérifier le reste du fichier : si d'autres lignes fabriquent ces fichiers sous
`artifacts/`, les repointer sur `$ARTIFACTS_DIR` pour que le test reste cohérent.

```bash
grep -n "artifacts/" infrastructure/tests/run_tests.sh
```

- [ ] **Step 5: Fix the two presence checks**

Dans `infrastructure/security-auditor.sh`, remplacer les lignes 36-39 :

```bash
if [ -f "secrets.yml" ]; then
    echo "✅ secrets.yml found (local only)."
else
    echo "⚠️ secrets.yml missing. Ensure you copied it from secrets.example.yml."
```

par :

```bash
if python3 -m andp config path secrets >/dev/null 2>&1; then
    echo "✅ credentials found at $(python3 -m andp config path secrets) (local only)."
else
    echo "⚠️ No credentials. Create .andp/secrets.yml from secrets.example.yml."
```

Dans `infrastructure/governance-report.sh`, remplacer la ligne 60 :

```bash
if [ -f "secrets.yml" ] || [ -f "secrets.example.yml" ]; then
```

par :

```bash
if python3 -m andp config path secrets >/dev/null 2>&1; then
```

- [ ] **Step 6: Verify the scripts parse**

Run: `bash -n sign.sh archive.sh artifact-manager.sh infrastructure/analytics-manager.sh infrastructure/security-auditor.sh infrastructure/governance-report.sh infrastructure/tests/run_tests.sh`
Expected: aucune sortie (syntaxe valide).

Run: `python3 -m pytest -q`
Expected: aucun échec (la suite Python n'exécute pas ces scripts).

- [ ] **Step 7: Commit**

```bash
git add sign.sh archive.sh artifact-manager.sh infrastructure/
git commit -m "refactor(scripts): résoudre la config via la CLI, artefacts sous .andp/

sign.sh lisait les secrets via un python inline dont la condition était toujours
vraie (concaténation de chaînes): le fallback n'était jamais atteint. Les scripts
consomment désormais \`andp config\`, seule implémentation de la cascade."
```

---

## Task 8: CI et actions GitHub

**Files:**
- Modify: `action.yml:44-52`
- Modify: `.github/actions/testflight-readiness/action.yml:~81-88`
- Modify: `.github/actions/appstore-readiness/action.yml:~99-106`
- Modify: `.github/workflows/andp-release.yml:103,109,115`
- Modify: `Jenkinsfile:30-31`, `azure-pipelines.yml:28-30`

**Interfaces:**
- Consumes: la cascade (Task 4) — les actions écrivent au niveau `project`
- Produces: rien pour les tâches suivantes

**Note :** les trois actions écrivent dans un `mktemp -d` jetable puis lancent ANDP depuis ce répertoire. Les consommateurs externes appellent l'action, jamais le chemin — aucun utilisateur en aval n'est impacté.

- [ ] **Step 1: Update the three actions**

Dans `action.yml`, remplacer la ligne de redirection :

```yaml
        } > "$WORKDIR/secrets.yml"
```

par :

```yaml
        } > "$WORKDIR/.andp/secrets.yml"
```

et insérer la création du répertoire juste après `umask 077` :

```yaml
        mkdir -p "$WORKDIR/.andp"
```

Appliquer exactement les mêmes deux modifications à
`.github/actions/testflight-readiness/action.yml` et
`.github/actions/appstore-readiness/action.yml`.

- [ ] **Step 2: Update the artefact paths in the workflows**

Dans `.github/workflows/andp-release.yml` :
- ligne 109 : `./sign.sh "build/$SCHEME.xcarchive"` → `./sign.sh ".andp/build/$SCHEME.xcarchive"`
- ligne 115 : `./asc-manager.sh upload "build/exported/$SCHEME.ipa"` → `./asc-manager.sh upload ".andp/build/exported/$SCHEME.ipa"`

Dans `Jenkinsfile` ligne 31 : `sh './sign.sh build/*.xcarchive'` → `sh './sign.sh .andp/build/*.xcarchive'`

Dans `azure-pipelines.yml` ligne 30 : `./sign.sh build/*.xcarchive` → `./sign.sh .andp/build/*.xcarchive`

- [ ] **Step 3: Validate the YAML**

```bash
python3 -c "
import yaml, sys
for path in ['action.yml',
             '.github/actions/testflight-readiness/action.yml',
             '.github/actions/appstore-readiness/action.yml',
             '.github/workflows/andp-release.yml',
             'azure-pipelines.yml']:
    yaml.safe_load(open(path))
    print('ok', path)
"
```
Expected: `ok` pour chacun.

- [ ] **Step 4: Verify no stale path remains**

```bash
grep -rn 'WORKDIR/secrets.yml\|sign.sh build/\|upload "build/' \
     action.yml .github/ Jenkinsfile azure-pipelines.yml
```
Expected: aucune sortie.

- [ ] **Step 5: Commit**

```bash
git add action.yml .github/ Jenkinsfile azure-pipelines.yml
git commit -m "ci: écrire les credentials dans .andp/ et lire les artefacts depuis .andp/build

Les trois actions écrivent dans un mktemp jetable puis lancent ANDP depuis ce
répertoire: les consommateurs appellent l'action, pas le chemin, donc aucun
utilisateur en aval n'est impacté."
```

---

## Task 9: Documentation et `.gitignore`

**Files:**
- Modify: `.gitignore`
- Modify: `README.md:31`, `SECURITY.md:21-24`, `Documentation/Security.md:7-8`, `Documentation/Operations.md:15,37`, `Documentation/Migration.md:11,21`, `Documentation/AgentGuide.md:44,393,400`, `Documentation/ASC-API.md:63,73`, `Documentation/Troubleshooting.md:14,31`, `Documentation/BuildNumber.md:50,59`, `Documentation/PublishReadiness.md:143`, `Documentation/Architecture/Diagrams.md:111,141`, `Documentation/articles/capacitor-without-appflow.md:22`
- Create: `Documentation/Configuration.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Simplify `.gitignore`**

Retirer les lignes devenues redondantes (`build/`, `metrics/`, `secrets.yml`) — la ligne `.andp/` déjà présente les couvre. Remplacer le bloc :

```
# ANDP Secrets
secrets.yml
*.ipa
```

par :

```
# ANDP Secrets
*.ipa
```

et retirer `build/` du bloc Xcode ainsi que `metrics/` du bloc ANDP Artifacts. Vérifier que `.andp/` reste présent.

- [ ] **Step 2: Update every quickstart**

Remplacer partout le motif :

```bash
cp secrets.example.yml secrets.yml
```

par :

```bash
mkdir -p .andp && cp secrets.example.yml .andp/secrets.yml
```

Sites : `README.md:31`, `Documentation/Migration.md:21`, `Documentation/ASC-API.md:63`,
`Documentation/articles/capacitor-without-appflow.md:22`.

Dans les autres fichiers, remplacer les mentions de `secrets.yml` désignant l'emplacement
par `.andp/secrets.yml` — sans toucher aux mentions de `secrets.example.yml`, qui reste
à la racine.

- [ ] **Step 3: Write `Documentation/Configuration.md`**

```markdown
# Configuration

ANDP sépare ce qui est versionné de ce qui ne l'est pas.

| | Emplacement | Versionné | Contenu |
|---|---|---|---|
| Config déclarative | `andp.yml` (racine) | oui | policy, pricing, availability, age rating |
| Espace runtime | `.andp/` | non, gitignoré | `secrets.yml`, `state/`, `build/`, `metrics/`, `artifacts/` |

## Où ANDP cherche les credentials

Premier trouvé gagne :

1. `$ANDP_CONFIG_DIR/secrets.yml`
2. `./.andp/secrets.yml` — le projet
3. `~/.andp/secrets.yml` — global à l'utilisateur
4. `./secrets.example.yml` — le template, qui force le mode DRY-RUN

`andp config` dit lequel a gagné :

```bash
$ andp config
ANDP config (account 'primary')
  dir       .andp
  secrets   .andp/secrets.yml   project   ✅ configured
  policy    andp.yml            absent
```

En script, `andp config path secrets` n'imprime que le chemin sur stdout.

## `./secrets.yml` n'est plus lu

L'emplacement historique n'est plus un niveau de la cascade. S'il traîne encore,
ANDP refuse de démarrer avec `config_misplaced` plutôt que de basculer
silencieusement en DRY-RUN :

```bash
andp config migrate     # .andp/ en 0700, le fichier en 0600, n'écrase jamais
```

## `$ANDP_CONFIG_DIR`, pas `$ANDP_HOME`

`ANDP_HOME` désigne le checkout du repo ANDP dans les workflows fournis. La
configuration se pilote avec `ANDP_CONFIG_DIR`.
```

Ajouter la ligne correspondante à l'index de documentation du `README.md` :

```markdown
- [`Documentation/Configuration.md`](Documentation/Configuration.md) — où ANDP lit sa configuration : l'espace de nom `.andp/`, la cascade de résolution, `andp config`
```

- [ ] **Step 4: Add a CHANGELOG entry**

En tête de `CHANGELOG.md`, dans la section non publiée :

```markdown
### Changed
- **BREAKING** — les credentials se lisent désormais dans `.andp/secrets.yml`
  (projet), `~/.andp/secrets.yml` (global) ou `$ANDP_CONFIG_DIR/secrets.yml`.
  `./secrets.yml` n'est plus chargé : `andp config migrate` déplace le fichier.
- Les artefacts de build, métriques et rapports passent sous `.andp/`.

### Added
- `andp config` — `path secrets|policy`, `dir`, `migrate`, et un diagnostic
  qui indique d'où viennent les credentials.
- Codes d'erreur typés `config_misplaced` et `config_not_found`, avec un bloc
  `context` listant les emplacements inspectés.

### Fixed
- En mode `--json`, une erreur de configuration produisait du texte brut sur
  stdout : l'enveloppe JSON est désormais toujours valide.
- `sign.sh` lisait les secrets via une condition Python toujours vraie, rendant
  son fallback inatteignable.
```

- [ ] **Step 5: Verify no stale reference remains**

```bash
grep -rn "cp secrets.example.yml secrets.yml" . | grep -v "^./.git/"
```
Expected: aucune sortie.

- [ ] **Step 6: Run the full suite one last time**

Run: `python3 -m pytest -q`
Expected: aucun échec.

- [ ] **Step 7: Commit**

```bash
git add .gitignore README.md SECURITY.md CHANGELOG.md Documentation/
git commit -m "docs: documenter l'espace de nom .andp/ et simplifier .gitignore

Ajoute Documentation/Configuration.md (cascade, andp config, migration) et
retire de .gitignore les entrées que la ligne .andp/ couvre désormais — ce qui
corrige au passage artifacts/, qu'aucune règle n'ignorait."
```

---

## Vérification finale

- [ ] `python3 -m pytest -q` — aucun échec
- [ ] `grep -rn "core.errors" --include="*.py" andp/ tests/` — aucune sortie
- [ ] `grep -rn '"secrets.yml"' tests/ | grep -v "secrets_file\|write_secrets"` — aucune sortie
- [ ] `bash -n build.sh archive.sh sign.sh test.sh` — syntaxe valide
- [ ] Bout en bout, dans un répertoire temporaire :

```bash
cd "$(mktemp -d)"
python3 -m andp verify --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['error']['code'])"
# attendu: config_not_found

printf 'accounts: {}\n' > secrets.yml
python3 -m andp verify --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['error']['code'])"
# attendu: config_misplaced

python3 -m andp config migrate && python3 -m andp config path secrets
# attendu: <cwd>/.andp/secrets.yml
```
