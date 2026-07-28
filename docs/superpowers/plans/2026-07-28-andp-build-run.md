# `andp build` / `run` / `test` — plan d'implémentation

> **Pour les agents :** SOUS-COMPÉTENCE REQUISE — `superpowers:subagent-driven-development`
> ou `superpowers:executing-plans` pour dérouler ce plan tâche par tâche. Les
> étapes utilisent la syntaxe case à cocher (`- [ ]`).

**But :** trois commandes natives — `andp build`, `andp run`, `andp test` — qui
construisent, lancent et testent toutes les cibles déclarées d'un projet Xcode,
avec un résultat structuré par cible.

**Architecture :** un paquet `andp/xcode/` symétrique de `andp/asc/`.
`targets.py` et `destination.py` sont purs ; `runner.py`, `simulator.py` et
`device.py` reçoivent leur lanceur de processus par injection. Aucun test ne
lance `xcodebuild`.

**Pile technique :** Python 2/3 compatible (style du dépôt), `subprocess`,
`yaml`, `pytest`. Outils externes appelés : `xcodebuild`, `xcrun simctl`,
`xcrun devicectl`.

**Spec :** `docs/superpowers/specs/2026-07-28-andp-build-run-design.md`

## Contraintes globales

- **Style du dépôt :** pas d'annotations de type, `namedtuple` plutôt que
  `dataclass` pour les valeurs de retour, docstrings expliquant *pourquoi*.
- **Direction des dépendances :** `andp/xcode/` importe `andp/errors.py` et
  `andp/paths.py`. Jamais `andp/asc/` ni `andp/core/`.
- **Invariant JSON :** en `--json`, stdout est toujours du JSON parsable. Les
  messages humains vont sur stderr.
- **Injection de processus :** toute fonction qui lance un processus accepte un
  paramètre `run_process=None` en dernier, défaut `subprocess.run`.
- **YAML :** `loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)` — le
  patron du dépôt (`andp/policy.py:12`).
- **Nommage des erreurs :** codes stables, en `snake_case`, listés en spec §11.
- **Commits :** un par tâche, message en français, avec le pied de session.

---

### Tâche 1 : `context` dans `AndpError`, et `XcodeError`

**Fichiers :**
- Modifier : `andp/errors.py`
- Test : `tests/test_errors_taxonomy.py`

**Interfaces :**
- Produit : `AndpError(code, message, retryable, remediation, context={})` avec
  `to_dict()` qui n'émet `context` que s'il est non vide ;
  `XcodeError(message, code, retryable=False, remediation="", context=None)`.

- [ ] **Étape 1 : test d'échec**

```python
def test_andp_error_carries_context():
    err = AndpError(code="build_failed", message="boom", retryable=False,
                    remediation="lis le log", context={"errors": ["a.swift:1"]})
    assert err.to_dict()["context"] == {"errors": ["a.swift:1"]}


def test_andp_error_omits_empty_context():
    err = AndpError(code="x", message="m", retryable=False, remediation="")
    assert "context" not in err.to_dict()


def test_xcode_error_is_an_andp_error():
    err = XcodeError("boom", code="build_failed", context={"log": "/tmp/a.log"})
    assert isinstance(err, AndpError)
    assert err.retryable is False
    assert err.to_dict()["context"] == {"log": "/tmp/a.log"}


def test_xcode_error_can_be_retryable():
    assert XcodeError("boot", code="simulator_boot_failed",
                      retryable=True).to_dict()["retryable"] is True
```

- [ ] **Étape 2 : vérifier l'échec**

`pytest tests/test_errors_taxonomy.py -v` → ImportError sur `XcodeError`.

- [ ] **Étape 3 : implémenter**

Dans `andp/errors.py`, ajouter `field` à l'import et le champ à la dataclass :

```python
from dataclasses import dataclass, field


@dataclass
class AndpError(Exception):
    code: str
    message: str
    retryable: bool
    remediation: str
    # Ce qui a été inspecté au moment de l'échec — chemins cherchés, valeurs
    # admises, lignes d'erreur du compilateur. Un agent remédie sans relancer
    # la commande pour explorer. Facultatif et en dernier: les constructions
    # existantes passent par mots-clés et ne bougent pas.
    context: dict = field(default_factory=dict)

    def __post_init__(self):
        super().__init__(f"[{self.code}] {self.message}")

    def to_dict(self):
        payload = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "remediation": self.remediation,
        }
        if self.context:
            payload["context"] = self.context
        return payload
```

Simplifier `ConfigError` — il n'a plus rien à surcharger :

```python
class ConfigError(AndpError):
    """Erreur de configuration — un AndpError jamais réessayable."""

    def __init__(self, message, code="config_error", remediation="", context=None):
        super().__init__(code=code, message=message, retryable=False,
                         remediation=remediation, context=context or {})


class XcodeError(AndpError):
    """Erreur de la couche outillage local (spec §11).

    Presque toutes sont définitives: un build cassé le reste tant que le code
    ne change pas. `simulator_boot_failed` est l'exception, d'où le paramètre.
    """

    def __init__(self, message, code="xcode_error", retryable=False,
                 remediation="", context=None):
        super().__init__(code=code, message=message, retryable=retryable,
                         remediation=remediation, context=context or {})
```

- [ ] **Étape 4 : vérifier le succès**

`pytest tests/test_errors_taxonomy.py -v` → tout passe.
`pytest -q` → les 423 tests existants passent toujours (la vraie vérification :
`ConfigError` a changé de forme interne).

- [ ] **Étape 5 : commit**

```bash
git add andp/errors.py tests/test_errors_taxonomy.py
git commit -m "refactor(errors): remonter context dans AndpError, ajouter XcodeError"
```

---

### Tâche 2 : résolution des cibles

**Fichiers :**
- Créer : `andp/xcode/__init__.py`, `andp/xcode/targets.py`
- Test : `tests/test_xcode_targets.py`

**Interfaces :**
- Consomme : `XcodeError` (tâche 1), `paths.policy_path` (existant).
- Produit :
  - `Target = namedtuple("Target", "name scheme platform destination configuration os")`
  - `PLATFORMS` — tuple des six plateformes admises
  - `FIELDS` — tuple des cinq champs admis dans une cible
  - `load_targets(project_root=".") -> dict`
  - `resolve(name=None, project_root=".", scheme_lister=None, overrides=None) -> Target`
  - `resolve_all(project_root=".", scheme_lister=None) -> list`
  - `list_names(project_root=".") -> list`
  - `project_dir(project_root=".") -> str`

- [ ] **Étape 1 : test d'échec**

```python
import pytest
from andp.errors import XcodeError
from andp.xcode import targets


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
    assert t.destination == "generic"      # défaut du champ


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
    root = _write(tmp_path, "targets:\n  defaults:\n    scheme: A\n  x:\n    platform: iOS\n")
    assert targets.list_names(root) == ["x"]
    with pytest.raises(XcodeError) as e:
        targets.resolve("defaults", root)
    assert e.value.code == "target_not_found"


def test_unknown_target_lists_the_known_ones(tmp_path):
    root = _write(tmp_path, "targets:\n  a:\n    platform: iOS\n  b:\n    platform: tvOS\n")
    with pytest.raises(XcodeError) as e:
        targets.resolve("c", root)
    assert e.value.code == "target_not_found"
    assert e.value.context["available"] == ["a", "b"]


def test_unknown_field_is_refused(tmp_path):
    root = _write(tmp_path, "targets:\n  a:\n    platfrom: iOS\n")
    with pytest.raises(XcodeError) as e:
        targets.resolve("a", root)
    assert e.value.code == "bad_target_config"
    assert e.value.context["unknown"] == "platfrom"
    assert "platform" in e.value.context["allowed"]


def test_unknown_platform_is_refused(tmp_path):
    root = _write(tmp_path, "targets:\n  a:\n    platform: androidOS\n")
    with pytest.raises(XcodeError) as e:
        targets.resolve("a", root)
    assert e.value.code == "bad_target_config"
    assert "visionOS" in e.value.context["allowed"]


def test_autodetect_single_scheme(tmp_path):
    t = targets.resolve(None, str(tmp_path), scheme_lister=lambda d: ["Solo"])
    assert t.name == "default"
    assert t.scheme == "Solo"


def test_autodetect_multiple_schemes_is_ambiguous(tmp_path):
    with pytest.raises(XcodeError) as e:
        targets.resolve(None, str(tmp_path), scheme_lister=lambda d: ["A", "B"])
    assert e.value.code == "ambiguous_scheme"
    assert e.value.context["schemes"] == ["A", "B"]
    assert "targets:" in e.value.remediation


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


def test_project_dir_prefers_the_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDP_APP_DIR", "/from/env")
    assert targets.project_dir(str(tmp_path)) == "/from/env"


def test_project_dir_falls_back_to_andp_yml(tmp_path, monkeypatch):
    monkeypatch.delenv("ANDP_APP_DIR", raising=False)
    root = _write(tmp_path, "project:\n  dir: apps/demo\n")
    assert targets.project_dir(root).endswith("apps/demo")


def test_project_dir_defaults_to_the_root(tmp_path, monkeypatch):
    monkeypatch.delenv("ANDP_APP_DIR", raising=False)
    assert targets.project_dir(str(tmp_path)) == str(tmp_path)
```

- [ ] **Étape 2 : vérifier l'échec**

`pytest tests/test_xcode_targets.py -v` → `ModuleNotFoundError: andp.xcode`.

- [ ] **Étape 3 : implémenter**

`andp/xcode/__init__.py` : docstring seule, expliquant que le paquet est la
couche outillage local et qu'il ne dépend pas de `asc/`.

`andp/xcode/targets.py` :

```python
"""Résolution des cibles de build — module pur, ne lance aucun processus.

L'auto-détection a besoin de la liste des schemes: elle arrive par injection
(`scheme_lister`), ce qui garde ce module testable sans Xcode.
"""
import os
from collections import namedtuple

import yaml

from ..errors import XcodeError
from .. import paths

Target = namedtuple("Target", "name scheme platform destination configuration os")

PLATFORMS = ("iOS", "iPadOS", "watchOS", "tvOS", "macOS", "visionOS")
FIELDS = ("scheme", "platform", "destination", "configuration", "os")
DEFAULTS = {"scheme": None, "platform": "iOS", "destination": "generic",
            "configuration": "Debug", "os": None}
ENV_APP_DIR = "ANDP_APP_DIR"
_DEFAULTS_KEY = "defaults"


def _load_yaml(project_root):
    path = paths.policy_path(project_root)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as handle:
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        return yaml.load(handle, Loader=loader) or {}


def load_targets(project_root="."):
    """Le bloc targets: de andp.yml, sans defaults. {} si absent."""
    block = _load_yaml(project_root).get("targets")
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise XcodeError(
            "Le bloc `targets:` de andp.yml doit être un dictionnaire de cibles.",
            code="bad_target_config",
            remediation="targets:\n  ma-cible:\n    platform: iOS")
    return dict((k, v) for k, v in block.items() if k != _DEFAULTS_KEY)


def list_names(project_root="."):
    return sorted(load_targets(project_root).keys())


def project_dir(project_root="."):
    """Où vit le projet Xcode: $ANDP_APP_DIR, puis project.dir, puis la racine."""
    from_env = os.environ.get(ENV_APP_DIR)
    if from_env:
        return from_env
    declared = (_load_yaml(project_root).get("project") or {}).get("dir")
    if declared:
        return os.path.join(project_root, declared)
    return project_root


def _validate(name, spec):
    if not isinstance(spec, dict):
        raise XcodeError(
            "La cible `%s` doit être un dictionnaire de champs." % name,
            code="bad_target_config",
            context={"target": name, "allowed": list(FIELDS)})
    for key in spec:
        if key not in FIELDS:
            raise XcodeError(
                "Champ inconnu `%s` dans la cible `%s`." % (key, name),
                code="bad_target_config",
                remediation="Champs admis : %s." % ", ".join(FIELDS),
                context={"target": name, "unknown": key, "allowed": list(FIELDS)})
    platform = spec.get("platform")
    if platform is not None and platform not in PLATFORMS:
        raise XcodeError(
            "Plateforme inconnue `%s` dans la cible `%s`." % (platform, name),
            code="bad_target_config",
            remediation="Plateformes admises : %s." % ", ".join(PLATFORMS),
            context={"target": name, "unknown": platform,
                     "allowed": list(PLATFORMS)})


def _build(name, spec, defaults, overrides):
    merged = dict(DEFAULTS)
    merged.update(dict((k, v) for k, v in defaults.items() if v is not None))
    merged.update(dict((k, v) for k, v in spec.items() if v is not None))
    # argparse laisse les drapeaux non passés à None: les filtrer, sinon un
    # drapeau absent effacerait ce que andp.yml déclare.
    merged.update(dict((k, v) for k, v in (overrides or {}).items()
                       if v is not None and k in FIELDS))
    return Target(name=name, **merged)


def _autodetect(project_root, scheme_lister, overrides):
    if scheme_lister is None:
        from .runner import list_schemes as scheme_lister
    schemes = scheme_lister(project_dir(project_root))
    if len(schemes) == 1:
        return _build("default", {"scheme": schemes[0]}, {}, overrides)
    raise XcodeError(
        "Plusieurs schemes dans le projet et aucun bloc `targets:` dans andp.yml.",
        code="ambiguous_scheme",
        remediation=("Déclarez vos cibles :\n\ntargets:\n  defaults:\n"
                     "    scheme: %s\n  dev:\n    platform: iOS\n"
                     % (schemes[0] if schemes else "MonScheme")),
        context={"schemes": list(schemes)})


def resolve(name=None, project_root=".", scheme_lister=None, overrides=None):
    """La cible `name`, ou l'unique cible du projet. Lève sinon."""
    raw = _load_yaml(project_root).get("targets") or {}
    defaults = raw.get(_DEFAULTS_KEY) or {}
    declared = load_targets(project_root)

    if name is None:
        if len(declared) == 1:
            name = list(declared.keys())[0]
        elif not declared:
            return _autodetect(project_root, scheme_lister, overrides)
        else:
            raise XcodeError(
                "Plusieurs cibles déclarées : précisez laquelle, ou --all.",
                code="ambiguous_target",
                remediation="andp build %s" % " | ".join(sorted(declared)),
                context={"available": sorted(declared)})

    if name not in declared:
        raise XcodeError(
            "Cible inconnue : %s." % name,
            code="target_not_found",
            remediation="Cibles déclarées : %s." % (", ".join(sorted(declared))
                                                    or "aucune"),
            context={"requested": name, "available": sorted(declared)})

    _validate(_DEFAULTS_KEY, defaults)
    _validate(name, declared[name])
    return _build(name, declared[name], defaults, overrides)


def resolve_all(project_root=".", scheme_lister=None):
    declared = load_targets(project_root)
    if not declared:
        return [resolve(None, project_root, scheme_lister)]
    return [resolve(n, project_root) for n in sorted(declared)]
```

- [ ] **Étape 4 : vérifier le succès**

`pytest tests/test_xcode_targets.py -v` → tout passe.

- [ ] **Étape 5 : commit**

```bash
git add andp/xcode/ tests/test_xcode_targets.py
git commit -m "feat(xcode): résolution des cibles depuis andp.yml"
```

---

### Tâche 3 : destinations

**Fichiers :**
- Créer : `andp/xcode/destination.py`
- Test : `tests/test_xcode_destination.py`

**Interfaces :**
- Consomme : `Target`, `XcodeError`.
- Produit : `to_argument(target, action="build") -> str`,
  `is_simulator(target) -> bool`, `sdk_platform(target) -> str`.

- [ ] **Étape 1 : test d'échec**

```python
import pytest
from andp.errors import XcodeError
from andp.xcode import destination
from andp.xcode.targets import Target


def _t(**kw):
    base = dict(name="t", scheme="S", platform="iOS", destination="generic",
                configuration="Debug", os=None)
    base.update(kw)
    return Target(**base)


def test_generic_destination():
    assert destination.to_argument(_t()) == "generic/platform=iOS"


def test_named_simulator():
    assert destination.to_argument(_t(destination="iPhone 15")) == \
        "platform=iOS Simulator,name=iPhone 15"


def test_named_simulator_with_runtime():
    assert destination.to_argument(_t(destination="iPhone 15", os="17.0")) == \
        "platform=iOS Simulator,name=iPhone 15,OS=17.0"


def test_physical_device_by_id():
    assert destination.to_argument(_t(destination="id=00008030-ABC")) == \
        "platform=iOS,id=00008030-ABC"


def test_ipados_is_an_alias_for_ios():
    assert destination.to_argument(_t(platform="iPadOS", destination="iPad Air")) == \
        "platform=iOS Simulator,name=iPad Air"


def test_visionos_simulator():
    assert destination.to_argument(_t(platform="visionOS",
                                      destination="Apple Vision Pro")) == \
        "platform=visionOS Simulator,name=Apple Vision Pro"


def test_watchos_and_tvos():
    assert "watchOS Simulator" in destination.to_argument(
        _t(platform="watchOS", destination="Apple Watch Series 9 (45mm)"))
    assert "tvOS Simulator" in destination.to_argument(
        _t(platform="tvOS", destination="Apple TV"))


def test_macos_generic():
    assert destination.to_argument(_t(platform="macOS")) == "generic/platform=macOS"


def test_macos_refuses_a_named_simulator():
    with pytest.raises(XcodeError) as e:
        destination.to_argument(_t(platform="macOS", destination="Mon Mac"))
    assert e.value.code == "bad_target_config"


def test_is_simulator():
    assert destination.is_simulator(_t(destination="iPhone 15")) is True
    assert destination.is_simulator(_t(destination="id=ABC")) is False
    assert destination.is_simulator(_t(destination="generic")) is False
    assert destination.is_simulator(_t(platform="macOS")) is False
```

- [ ] **Étape 2 : vérifier l'échec**

`pytest tests/test_xcode_destination.py -v` → ImportError.

- [ ] **Étape 3 : implémenter**

```python
"""Traduction d'une cible en argument -destination. Module pur.

xcodebuild ne connaît pas `iPadOS`: c'est iOS, la distinction se faisant par le
nom du simulateur. L'alias est accepté parce que c'est ce qu'on écrit
naturellement.
"""
from ..errors import XcodeError

GENERIC = "generic"
_DEVICE_ID_PREFIX = "id="
_ALIASES = {"iPadOS": "iOS"}


def sdk_platform(target):
    """Le nom de plateforme que xcodebuild comprend."""
    return _ALIASES.get(target.platform, target.platform)


def is_simulator(target):
    """Vrai si la destination désigne un simulateur nommé."""
    if target.platform == "macOS":
        return False
    return (target.destination != GENERIC
            and not target.destination.startswith(_DEVICE_ID_PREFIX))


def to_argument(target, action="build"):
    platform = sdk_platform(target)

    if target.destination == GENERIC:
        return "generic/platform=%s" % platform

    if target.destination.startswith(_DEVICE_ID_PREFIX):
        return "platform=%s,%s" % (platform, target.destination)

    if target.platform == "macOS":
        # Pas de simulateur macOS: traduire donnerait un argument que xcodebuild
        # rejetterait plus loin, avec un message qui ne pointe pas andp.yml.
        raise XcodeError(
            "macOS n'a pas de simulateur : `destination: %s` est invalide."
            % target.destination,
            code="bad_target_config",
            remediation="Utilisez `destination: generic` pour une cible macOS.",
            context={"target": target.name, "destination": target.destination})

    argument = "platform=%s Simulator,name=%s" % (platform, target.destination)
    if target.os:
        argument += ",OS=%s" % target.os
    return argument
```

- [ ] **Étape 4 : vérifier le succès**

`pytest tests/test_xcode_destination.py -v` → tout passe.

- [ ] **Étape 5 : commit**

```bash
git add andp/xcode/destination.py tests/test_xcode_destination.py
git commit -m "feat(xcode): traduction cible → argument -destination"
```

---

### Tâche 4 : invocation de xcodebuild

**Fichiers :**
- Créer : `andp/xcode/runner.py`
- Test : `tests/test_xcode_runner.py`

**Interfaces :**
- Consomme : `Target`, `destination.to_argument`, `XcodeError`, `paths.andp_dir`.
- Produit :
  - `BuildResult = namedtuple("BuildResult", "target action ok duration exit_code destination log_path error")`
  - `xcodebuild_available() -> bool`
  - `list_schemes(project_dir, run_process=None) -> list`
  - `build(target, project_dir, project_root=".", archive=False, run_process=None) -> BuildResult`
  - `test(target, project_dir, project_root=".", run_process=None) -> BuildResult`
  - `app_path(target, project_dir, run_process=None) -> str`

- [ ] **Étape 1 : test d'échec**

```python
import json
import os
import pytest
from andp.errors import XcodeError
from andp.xcode import runner
from andp.xcode.targets import Target


def _t(**kw):
    base = dict(name="dev", scheme="Meeshy", platform="iOS",
                destination="iPhone 15", configuration="Debug", os=None)
    base.update(kw)
    return Target(**base)


class FakeProcess(object):
    """Enregistre l'argv reçu et renvoie un code choisi. Aucun xcodebuild lancé."""

    def __init__(self, code=0, stdout=""):
        self.calls = []
        self.code = code
        self.stdout = stdout

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        handle = kwargs.get("stdout")
        if handle is not None and hasattr(handle, "write"):
            handle.write(self.stdout)
        return self.code


def test_build_argv_carries_scheme_configuration_and_destination(tmp_path):
    fake = FakeProcess()
    runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    argv = fake.calls[0]
    assert argv[0] == "xcodebuild"
    assert "-scheme" in argv and argv[argv.index("-scheme") + 1] == "Meeshy"
    assert argv[argv.index("-configuration") + 1] == "Debug"
    assert argv[argv.index("-destination") + 1] == \
        "platform=iOS Simulator,name=iPhone 15"
    assert argv[-1] == "build"


def test_successful_build_result(tmp_path):
    result = runner.build(_t(), str(tmp_path), str(tmp_path),
                          run_process=FakeProcess(0))
    assert result.ok is True
    assert result.exit_code == 0
    assert result.error is None
    assert result.target == "dev"
    assert result.duration >= 0


def test_failed_build_raises_nothing_but_carries_a_typed_error(tmp_path):
    fake = FakeProcess(65, stdout="Meeshy/App.swift:12: error: no such module\n")
    result = runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert result.ok is False
    assert result.error.code == "build_failed"
    assert result.error.retryable is False
    assert "no such module" in result.error.context["errors"][0]


def test_log_is_written_under_the_andp_namespace(tmp_path):
    fake = FakeProcess(0, stdout="compiling...\n")
    result = runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert os.path.exists(result.log_path)
    assert ".andp" in result.log_path and "dev-build" in result.log_path
    with open(result.log_path) as handle:
        assert "compiling" in handle.read()


def test_only_the_last_ten_error_lines_are_kept(tmp_path):
    noise = "".join("f.swift:%d: error: e%d\n" % (i, i) for i in range(30))
    fake = FakeProcess(65, stdout=noise)
    result = runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert len(result.error.context["errors"]) == 10
    assert "e29" in result.error.context["errors"][-1]


def test_ci_disables_code_signing(tmp_path, monkeypatch):
    monkeypatch.setenv("CI", "true")
    fake = FakeProcess()
    runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert "CODE_SIGNING_ALLOWED=NO" in fake.calls[0]


def test_no_signing_flags_outside_ci(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    fake = FakeProcess()
    runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert "CODE_SIGNING_ALLOWED=NO" not in fake.calls[0]


def test_archive_chains_archive_then_export(tmp_path):
    fake = FakeProcess()
    result = runner.build(_t(destination="generic"), str(tmp_path), str(tmp_path),
                          archive=True, run_process=fake)
    assert len(fake.calls) == 2
    assert "archive" in fake.calls[0]
    assert "-exportArchive" in fake.calls[1]
    assert result.ok is True


def test_archive_refuses_a_named_simulator(tmp_path):
    with pytest.raises(XcodeError) as e:
        runner.build(_t(destination="iPhone 15"), str(tmp_path), str(tmp_path),
                     archive=True, run_process=FakeProcess())
    assert e.value.code == "bad_target_config"


def test_export_failure_has_its_own_code(tmp_path):
    class FailSecond(FakeProcess):
        def __call__(self, argv, **kwargs):
            FakeProcess.__call__(self, argv, **kwargs)
            return 0 if len(self.calls) == 1 else 70

    result = runner.build(_t(destination="generic"), str(tmp_path), str(tmp_path),
                          archive=True, run_process=FailSecond())
    assert result.error.code == "export_failed"


def test_test_action_uses_the_test_verb(tmp_path):
    fake = FakeProcess()
    result = runner.test(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert "test" in fake.calls[0]
    assert result.action == "test"


def test_failed_test_has_its_own_code(tmp_path):
    result = runner.test(_t(), str(tmp_path), str(tmp_path),
                         run_process=FakeProcess(65))
    assert result.error.code == "test_failed"


def test_list_schemes_parses_the_json_output(tmp_path):
    payload = json.dumps({"project": {"schemes": ["Meeshy", "MeeshyWatch"]}})
    assert runner.list_schemes(str(tmp_path),
                               run_process=FakeProcess(0, payload)) == \
        ["Meeshy", "MeeshyWatch"]


def test_list_schemes_reads_a_workspace_payload(tmp_path):
    payload = json.dumps({"workspace": {"schemes": ["A"]}})
    assert runner.list_schemes(str(tmp_path),
                               run_process=FakeProcess(0, payload)) == ["A"]


def test_list_schemes_on_a_directory_without_project(tmp_path):
    with pytest.raises(XcodeError) as e:
        runner.list_schemes(str(tmp_path), run_process=FakeProcess(66, "nope"))
    assert e.value.code == "no_project"
```

- [ ] **Étape 2 : vérifier l'échec**

`pytest tests/test_xcode_runner.py -v` → ImportError.

- [ ] **Étape 3 : implémenter**

```python
"""Invocation de xcodebuild. Le lanceur de processus est injectable.

La sortie n'est pas parsée, à une exception près: les lignes `error:`, format
stable de longue date, remontent dans le contexte de l'erreur. C'est ce qui
distingue « le build a échoué » de « MeeshyWatch ne trouve pas WatchConnectivity ».
"""
import json
import os
import subprocess
import time
from collections import namedtuple

from ..errors import XcodeError
from .. import paths
from . import destination as dest

BuildResult = namedtuple(
    "BuildResult", "target action ok duration exit_code destination log_path error")

_MAX_ERROR_LINES = 10
_CI_SIGNING = ["CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO",
               "CODE_SIGN_IDENTITY=", "CODE_SIGN_ENTITLEMENTS=",
               "CODE_SIGNING_INJECT_BASE_ENTITLEMENTS=NO"]


def _run_process(argv, cwd=None, stdout=None):
    """Défaut: lance vraiment. Les tests injectent autre chose."""
    return subprocess.call(argv, cwd=cwd, stdout=stdout,
                           stderr=subprocess.STDOUT)


def xcodebuild_available():
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.isfile(os.path.join(directory, "xcodebuild")):
            return True
    return False


def _in_ci():
    return os.environ.get("CI") == "true" or \
        os.environ.get("GITHUB_ACTIONS") == "true"


def _log_path(project_root, target_name, action):
    directory = os.path.join(paths.andp_dir(project_root), "build", "logs")
    if not os.path.isdir(directory):
        os.makedirs(directory)
    return os.path.join(directory, "%s-%s.log" % (target_name, action))


def _error_lines(log_path):
    lines = []
    try:
        with open(log_path) as handle:
            for line in handle:
                if "error:" in line:
                    lines.append(line.rstrip())
    except IOError:
        return []
    return lines[-_MAX_ERROR_LINES:]


def _base_argv(target, extra=None):
    argv = ["xcodebuild",
            "-scheme", target.scheme,
            "-configuration", target.configuration,
            "-destination", dest.to_argument(target)]
    if _in_ci():
        argv.extend(_CI_SIGNING)
    argv.extend(extra or [])
    return argv


def _invoke(argv, project_dir, log_path, run_process, append=False):
    runner = run_process or _run_process
    with open(log_path, "a" if append else "w") as handle:
        return runner(argv, cwd=project_dir, stdout=handle)


def list_schemes(project_dir, run_process=None):
    """Les schemes du projet, via `xcodebuild -list -json`."""
    runner = run_process or _run_process
    import tempfile
    handle = tempfile.TemporaryFile(mode="w+")
    try:
        code = runner(["xcodebuild", "-list", "-json"], cwd=project_dir,
                      stdout=handle)
        handle.seek(0)
        payload = handle.read()
    finally:
        handle.close()
    if code != 0:
        raise XcodeError(
            "Aucun projet Xcode exploitable dans %s." % project_dir,
            code="no_project",
            remediation=("Vérifiez $ANDP_APP_DIR ou `project.dir` dans andp.yml, "
                         "et que le projet a été généré (xcodegen)."),
            context={"project_dir": project_dir})
    try:
        data = json.loads(payload)
    except ValueError:
        raise XcodeError(
            "Sortie illisible de `xcodebuild -list -json`.",
            code="no_project", context={"project_dir": project_dir})
    container = data.get("workspace") or data.get("project") or {}
    return list(container.get("schemes") or [])


def _result(target, action, ok, started, code, log_path, error):
    return BuildResult(target=target.name, action=action, ok=ok,
                       duration=round(time.time() - started, 2), exit_code=code,
                       destination=dest.to_argument(target), log_path=log_path,
                       error=error)


def _failure(target, action, code, error_code, log_path, message):
    return XcodeError(
        message, code=error_code,
        remediation="Lisez le journal complet : %s" % log_path,
        context={"target": target.name, "exit_code": code,
                 "log": log_path, "errors": _error_lines(log_path)})


def build(target, project_dir, project_root=".", archive=False, run_process=None):
    """Compile la cible. Avec archive=True, enchaîne archive puis exportArchive."""
    if archive and target.destination != dest.GENERIC:
        raise XcodeError(
            "L'archivage exige `destination: generic` (reçu : %s)."
            % target.destination,
            code="bad_target_config",
            remediation="Archiver pour un simulateur ne produit rien d'installable.",
            context={"target": target.name, "destination": target.destination})

    action = "archive" if archive else "build"
    log_path = _log_path(project_root, target.name, action)
    started = time.time()

    if not archive:
        code = _invoke(_base_argv(target, ["build"]), project_dir, log_path,
                       run_process)
        error = None if code == 0 else _failure(
            target, action, code, "build_failed", log_path,
            "xcodebuild a terminé avec le code %s." % code)
        return _result(target, action, code == 0, started, code, log_path, error)

    build_dir = os.path.join(paths.andp_dir(project_root), "build")
    archive_path = os.path.join(build_dir, "%s.xcarchive" % target.name)
    export_path = os.path.join(build_dir, "exported")

    code = _invoke(_base_argv(target, ["archive", "-archivePath", archive_path]),
                   project_dir, log_path, run_process)
    if code != 0:
        error = _failure(target, action, code, "build_failed", log_path,
                         "L'archivage a terminé avec le code %s." % code)
        return _result(target, action, False, started, code, log_path, error)

    code = _invoke(["xcodebuild", "-exportArchive",
                    "-archivePath", archive_path,
                    "-exportPath", export_path],
                   project_dir, log_path, run_process, append=True)
    error = None if code == 0 else _failure(
        target, action, code, "export_failed", log_path,
        "L'export de l'archive a terminé avec le code %s." % code)
    return _result(target, action, code == 0, started, code, log_path, error)


def test(target, project_dir, project_root=".", run_process=None):
    log_path = _log_path(project_root, target.name, "test")
    started = time.time()
    code = _invoke(_base_argv(target, ["test"]), project_dir, log_path,
                   run_process)
    error = None if code == 0 else _failure(
        target, "test", code, "test_failed", log_path,
        "La suite de tests a terminé avec le code %s." % code)
    return _result(target, "test", code == 0, started, code, log_path, error)


def app_path(target, project_dir, run_process=None):
    """Le .app produit, via -showBuildSettings. Nécessaire pour install/launch."""
    runner = run_process or _run_process
    import tempfile
    handle = tempfile.TemporaryFile(mode="w+")
    try:
        code = runner(_base_argv(target, ["-showBuildSettings", "-json"]),
                      cwd=project_dir, stdout=handle)
        handle.seek(0)
        payload = handle.read()
    finally:
        handle.close()
    settings = {}
    if code == 0:
        try:
            for entry in json.loads(payload):
                settings = entry.get("buildSettings") or {}
                break
        except ValueError:
            settings = {}
    directory = settings.get("TARGET_BUILD_DIR")
    name = settings.get("FULL_PRODUCT_NAME")
    if not directory or not name:
        raise XcodeError(
            "Impossible de localiser le produit compilé de `%s`." % target.name,
            code="app_not_found",
            remediation="Compilez d'abord la cible : andp build %s" % target.name,
            context={"target": target.name})
    return os.path.join(directory, name)
```

- [ ] **Étape 4 : vérifier le succès**

`pytest tests/test_xcode_runner.py -v` → tout passe.

**Note d'implémentation :** `FakeProcess.__call__` reçoit `stdout` en mot-clé et
y écrit ; `_invoke` ouvre le fichier avant d'appeler le lanceur. Si un test
échoue sur l'écriture du log, vérifier que le faux écrit bien dans le handle
reçu plutôt que de retourner une chaîne.

- [ ] **Étape 5 : commit**

```bash
git add andp/xcode/runner.py tests/test_xcode_runner.py
git commit -m "feat(xcode): invocation xcodebuild, journalisation et erreurs typées"
```

---

### Tâche 5 : simulateur et appareil

**Fichiers :**
- Créer : `andp/xcode/simulator.py`, `andp/xcode/device.py`
- Test : `tests/test_xcode_simulator.py`

**Interfaces :**
- Consomme : `Target`, `destination.sdk_platform`, `XcodeError`.
- Produit :
  - `simulator.find(target, run_process=None) -> dict` — `{udid, name, state}`
  - `simulator.boot(udid, run_process=None) -> None`
  - `simulator.install(udid, app_path, run_process=None) -> None`
  - `simulator.launch(udid, bundle_id, run_process=None) -> None`
  - `simulator.bundle_id(app_path) -> str`
  - `device.install(udid, app_path, run_process=None) -> None`
  - `device.launch(udid, bundle_id, run_process=None) -> None`

- [ ] **Étape 1 : test d'échec**

```python
import json
import pytest
from andp.errors import XcodeError
from andp.xcode import simulator
from andp.xcode.targets import Target

DEVICES = {"devices": {
    "com.apple.CoreSimulator.SimRuntime.iOS-17-0": [
        {"udid": "AAA", "name": "iPhone 15", "state": "Shutdown",
         "isAvailable": True},
        {"udid": "BBB", "name": "iPhone 15 Pro", "state": "Booted",
         "isAvailable": True},
        {"udid": "CCC", "name": "iPhone 14", "state": "Shutdown",
         "isAvailable": False}],
    "com.apple.CoreSimulator.SimRuntime.xrOS-1-0": [
        {"udid": "VVV", "name": "Apple Vision Pro", "state": "Shutdown",
         "isAvailable": True}]}}


class FakeProcess(object):
    def __init__(self, code=0, stdout=""):
        self.calls = []
        self.code = code
        self.stdout = stdout

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        handle = kwargs.get("stdout")
        if handle is not None and hasattr(handle, "write"):
            handle.write(self.stdout)
        return self.code


def _t(**kw):
    base = dict(name="dev", scheme="S", platform="iOS", destination="generic",
                configuration="Debug", os=None)
    base.update(kw)
    return Target(**base)


def test_find_by_name():
    fake = FakeProcess(0, json.dumps(DEVICES))
    found = simulator.find(_t(destination="iPhone 15"), run_process=fake)
    assert found["udid"] == "AAA"


def test_generic_prefers_a_booted_simulator():
    """Sans nom, on prend celui qui tourne déjà — pas de boot inutile."""
    fake = FakeProcess(0, json.dumps(DEVICES))
    assert simulator.find(_t(), run_process=fake)["udid"] == "BBB"


def test_generic_filters_by_platform():
    fake = FakeProcess(0, json.dumps(DEVICES))
    found = simulator.find(_t(platform="visionOS"), run_process=fake)
    assert found["udid"] == "VVV"


def test_unavailable_devices_are_skipped():
    fake = FakeProcess(0, json.dumps(DEVICES))
    with pytest.raises(XcodeError) as e:
        simulator.find(_t(destination="iPhone 14"), run_process=fake)
    assert e.value.code == "simulator_not_found"


def test_no_simulator_for_the_platform():
    fake = FakeProcess(0, json.dumps(DEVICES))
    with pytest.raises(XcodeError) as e:
        simulator.find(_t(platform="tvOS"), run_process=fake)
    assert e.value.code == "simulator_not_found"
    assert e.value.context["platform"] == "tvOS"


def test_boot_failure_is_retryable():
    with pytest.raises(XcodeError) as e:
        simulator.boot("AAA", run_process=FakeProcess(1))
    assert e.value.code == "simulator_boot_failed"
    assert e.value.retryable is True


def test_boot_waits_for_readiness():
    fake = FakeProcess(0)
    simulator.boot("AAA", run_process=fake)
    assert ["xcrun", "simctl", "boot", "AAA"] == fake.calls[0]
    assert "bootstatus" in fake.calls[1]


def test_install_and_launch():
    fake = FakeProcess(0)
    simulator.install("AAA", "/tmp/My.app", run_process=fake)
    simulator.launch("AAA", "com.me.app", run_process=fake)
    assert fake.calls[0] == ["xcrun", "simctl", "install", "AAA", "/tmp/My.app"]
    assert fake.calls[1] == ["xcrun", "simctl", "launch", "AAA", "com.me.app"]


def test_bundle_id_is_read_from_the_app_plist(tmp_path):
    app = tmp_path / "My.app"
    app.mkdir()
    (app / "Info.plist").write_text(
        '<?xml version="1.0"?><plist><dict>'
        '<key>CFBundleIdentifier</key><string>com.me.app</string>'
        '</dict></plist>')
    assert simulator.bundle_id(str(app)) == "com.me.app"


def test_bundle_id_missing_plist_raises(tmp_path):
    with pytest.raises(XcodeError) as e:
        simulator.bundle_id(str(tmp_path / "Nope.app"))
    assert e.value.code == "app_not_found"
```

- [ ] **Étape 2 : vérifier l'échec**

`pytest tests/test_xcode_simulator.py -v` → ImportError.

- [ ] **Étape 3 : implémenter**

`andp/xcode/simulator.py` :

```python
"""simctl — recherche, démarrage, installation, lancement.

Le boot est la seule opération réessayable de la couche: simctl échoue de façon
transitoire sous charge, ce que infrastructure/simulator-manager.sh traite déjà
par trois tentatives.
"""
import json
import os
import plistlib
import tempfile

from ..errors import XcodeError
from . import destination as dest
from .runner import _run_process

# Le runtime visionOS s'appelle xrOS dans simctl, pas visionOS.
_RUNTIME_TOKENS = {"iOS": "iOS", "iPadOS": "iOS", "watchOS": "watchOS",
                   "tvOS": "tvOS", "visionOS": "xrOS"}


def _list_devices(run_process=None):
    runner = run_process or _run_process
    handle = tempfile.TemporaryFile(mode="w+")
    try:
        runner(["xcrun", "simctl", "list", "devices", "available", "-j"],
               stdout=handle)
        handle.seek(0)
        payload = handle.read()
    finally:
        handle.close()
    try:
        return json.loads(payload).get("devices") or {}
    except ValueError:
        return {}


def _candidates(target, run_process):
    token = _RUNTIME_TOKENS.get(target.platform, target.platform)
    found = []
    for runtime, devices in _list_devices(run_process).items():
        if token not in runtime:
            continue
        for device in devices:
            if device.get("isAvailable", True):
                found.append(device)
    return found


def find(target, run_process=None):
    """Le simulateur de la cible. Sans nom: le démarré, sinon le premier."""
    candidates = _candidates(target, run_process)

    if dest.is_simulator(target):
        for device in candidates:
            if device.get("name") == target.destination:
                return device
        raise XcodeError(
            "Aucun simulateur disponible nommé `%s`." % target.destination,
            code="simulator_not_found",
            remediation="xcrun simctl list devices available",
            context={"target": target.name, "requested": target.destination,
                     "available": [d.get("name") for d in candidates]})

    for device in candidates:
        if device.get("state") == "Booted":
            return device
    if candidates:
        return candidates[0]
    raise XcodeError(
        "Aucun simulateur %s disponible." % target.platform,
        code="simulator_not_found",
        remediation="Installez un runtime %s depuis Xcode." % target.platform,
        context={"target": target.name, "platform": target.platform})


def boot(udid, run_process=None):
    """Démarre et attend. Un simulateur déjà démarré fait échouer `boot`,
    d'où l'attente inconditionnelle: c'est bootstatus qui fait foi."""
    runner = run_process or _run_process
    runner(["xcrun", "simctl", "boot", udid])
    if runner(["xcrun", "simctl", "bootstatus", udid]) != 0:
        raise XcodeError(
            "Le simulateur %s n'a pas démarré." % udid,
            code="simulator_boot_failed", retryable=True,
            remediation="Réessayez ; simctl échoue de façon transitoire sous charge.",
            context={"udid": udid})


def install(udid, app_path, run_process=None):
    runner = run_process or _run_process
    if runner(["xcrun", "simctl", "install", udid, app_path]) != 0:
        raise XcodeError(
            "Installation refusée sur %s." % udid,
            code="install_failed",
            remediation="Vérifiez que le .app correspond à la plateforme du simulateur.",
            context={"udid": udid, "app": app_path})


def launch(udid, bundle_id, run_process=None):
    runner = run_process or _run_process
    if runner(["xcrun", "simctl", "launch", udid, bundle_id]) != 0:
        raise XcodeError(
            "Lancement de %s refusé sur %s." % (bundle_id, udid),
            code="launch_failed", remediation="Vérifiez l'identifiant de bundle.",
            context={"udid": udid, "bundle_id": bundle_id})


def bundle_id(app_path):
    plist = os.path.join(app_path, "Info.plist")
    if not os.path.exists(plist):
        raise XcodeError(
            "Aucun Info.plist dans %s." % app_path,
            code="app_not_found",
            remediation="Compilez la cible avant de la lancer.",
            context={"app": app_path})
    with open(plist, "rb") as handle:
        load = getattr(plistlib, "load", None) or plistlib.readPlist
        data = load(handle)
    identifier = data.get("CFBundleIdentifier")
    if not identifier:
        raise XcodeError(
            "CFBundleIdentifier absent de %s." % plist,
            code="app_not_found", context={"app": app_path})
    return identifier
```

`andp/xcode/device.py` — même forme, en meilleur effort :

```python
"""devicectl — appareil physique, en meilleur effort.

Appairage, confiance et provisioning restent la responsabilité de
l'utilisateur: on rend un échec typé plutôt que de tenter un contournement.
"""
from ..errors import XcodeError
from .runner import _run_process


def install(udid, app_path, run_process=None):
    runner = run_process or _run_process
    if runner(["xcrun", "devicectl", "device", "install", "app",
               "--device", udid, app_path]) != 0:
        raise XcodeError(
            "Installation refusée sur l'appareil %s." % udid,
            code="device_install_failed",
            remediation=("Vérifiez que l'appareil est appairé, déverrouillé, et "
                         "que le profil de provisioning couvre son identifiant."),
            context={"udid": udid, "app": app_path})


def launch(udid, bundle_id, run_process=None):
    runner = run_process or _run_process
    if runner(["xcrun", "devicectl", "device", "process", "launch",
               "--device", udid, bundle_id]) != 0:
        raise XcodeError(
            "Lancement de %s refusé sur l'appareil %s." % (bundle_id, udid),
            code="device_not_found",
            remediation="xcrun devicectl list devices",
            context={"udid": udid, "bundle_id": bundle_id})
```

- [ ] **Étape 4 : vérifier le succès**

`pytest tests/test_xcode_simulator.py -v` → tout passe.

- [ ] **Étape 5 : commit**

```bash
git add andp/xcode/simulator.py andp/xcode/device.py tests/test_xcode_simulator.py
git commit -m "feat(xcode): pilotage simctl et devicectl"
```

---

### Tâche 6 : commandes `build`, `test`, `targets`

**Fichiers :**
- Créer : `andp/xcode/commands.py`
- Modifier : `andp/asc/asc_manager.py` (dispatcher, `COMMANDS`, `USAGE`)
- Test : `tests/test_xcode_envelope.py`

**Interfaces :**
- Consomme : tout ce qui précède.
- Produit :
  - `commands.cmd_build(args, json_mode=False, project_root=".", run_process=None) -> int`
  - `commands.cmd_test(...) -> int`
  - `commands.cmd_targets(...) -> int`
  - `asc_manager._error_envelope(command, exc, json_mode) -> int`
  - `asc_manager.CREDENTIAL_FREE` — ensemble des commandes sans credentials

- [ ] **Étape 1 : test d'échec**

```python
import json
import pytest
from andp.asc.asc_manager import main


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    monkeypatch.delenv("ANDP_APP_DIR", raising=False)
    monkeypatch.setenv("PATH", "")          # pas de xcodebuild → DRY-RUN
    monkeypatch.chdir(tmp_path)
    (tmp_path / "andp.yml").write_text("""
targets:
  defaults:
    scheme: Meeshy
  dev:
    platform: iOS
    destination: "iPhone 15"
  vision:
    platform: visionOS
    destination: "Apple Vision Pro"
""")


def test_build_runs_without_credentials(capsys):
    """Un build ne parle pas à Apple: il ne doit rien exiger."""
    rc = main(["build", "dev", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["dry_run"] is True


def test_dry_run_is_declared_never_silent(capsys):
    main(["build", "dev"])
    assert "DRY-RUN" in capsys.readouterr().err


def test_all_builds_every_declared_target(capsys):
    rc = main(["build", "--all", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert [r["target"] for r in payload["results"]] == ["dev", "vision"]


def test_unknown_target_is_a_typed_envelope(capsys):
    rc = main(["build", "nope", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "target_not_found"
    assert payload["error"]["context"]["available"] == ["dev", "vision"]


def test_no_target_and_no_all_is_ambiguous(capsys):
    rc = main(["build", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "ambiguous_target"


def test_targets_lists_effective_fields(capsys):
    rc = main(["targets", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    dev = [t for t in payload["targets"] if t["name"] == "dev"][0]
    assert dev["scheme"] == "Meeshy"                 # hérité de defaults
    assert dev["destination_argument"] == "platform=iOS Simulator,name=iPhone 15"


def test_json_stays_parsable_on_a_broken_config(tmp_path, capsys):
    (tmp_path / "andp.yml").write_text("targets:\n  a:\n    platfrom: iOS\n")
    rc = main(["build", "a", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "bad_target_config"


def test_human_mode_keeps_stdout_free_of_errors(capsys):
    rc = main(["build", "nope"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "target_not_found" not in captured.out
    assert "nope" in captured.err
```

Un second fichier, `tests/test_xcode_aggregate.py`, pour l'agrégation avec un
lanceur injecté (les tests ci-dessus passent par `main`, qui n'expose pas
l'injection) :

```python
from andp.xcode import commands
from andp.xcode.targets import Target


def _t(name, **kw):
    base = dict(name=name, scheme="S", platform="iOS", destination="generic",
                configuration="Debug", os=None)
    base.update(kw)
    return Target(**base)


class FailSecond(object):
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        return 0 if len(self.calls) == 1 else 65


def test_execution_continues_past_a_failure(tmp_path):
    envelope = commands.build_targets(
        [_t("a"), _t("b"), _t("c")], str(tmp_path), str(tmp_path),
        run_process=FailSecond())
    assert [r["target"] for r in envelope["results"]] == ["a", "b", "c"]
    assert [r["ok"] for r in envelope["results"]] == [True, False, False]


def test_envelope_ok_is_the_conjunction(tmp_path):
    envelope = commands.build_targets([_t("a"), _t("b")], str(tmp_path),
                                      str(tmp_path), run_process=FailSecond())
    assert envelope["ok"] is False
```

- [ ] **Étape 2 : vérifier l'échec**

`pytest tests/test_xcode_envelope.py tests/test_xcode_aggregate.py -v` → échec.

- [ ] **Étape 3 : implémenter**

`andp/xcode/commands.py` porte le découpage d'arguments, l'agrégation et
l'affichage. Points à respecter :

- `_parse(args)` sépare les cibles positionnelles des drapeaux
  `--all --archive --no-build --logs --scheme --configuration --platform
  --destination --os`. Un drapeau à valeur consomme l'argument suivant ; un
  drapeau à valeur manquante lève `XcodeError(code="bad_usage")`.
- `build_targets(targets, project_dir, project_root, archive=False,
  run_process=None)` boucle **séquentiellement**, appelle `runner.build`,
  n'interrompt jamais la boucle sur un échec, et rend le dictionnaire
  d'enveloppe. Chaque entrée : `target`, `ok`, `duration`, `destination`,
  `log`, plus `error` si échec.
- `dry_run` vaut `runner.xcodebuild_available() is False`. En DRY-RUN, aucune
  invocation : chaque cible rend `ok: True` sans lancer de processus, et un
  bandeau part sur stderr en mode humain.
- `cmd_targets` rend `{"targets": [...]}`, chaque entrée portant les six champs
  du `Target` plus `destination_argument`.
- L'affichage humain : une ligne par cible sur stdout, `✅`/`❌`, durée, chemin
  du log ; les erreurs détaillées sur stderr.

Dans `andp/asc/asc_manager.py` :

```python
def _error_envelope(command, exc, json_mode):
    """Enveloppe d'échec — JSON parsable, ou message humain sur stderr.

    Une seule forme d'échec pour tout l'outil. En --json, stdout doit rester
    parsable: un agent y lit code/retryable/remediation, et ne tire rien d'une
    ligne d'erreur nue.
    """
    if json_mode:
        print(json.dumps({"command": command, "ok": False,
                          "error": exc.to_dict()}))
    else:
        print("❌ %s" % exc.message, file=sys.stderr)
        if exc.remediation:
            print("   → %s" % exc.remediation, file=sys.stderr)
    return 1
```

Le bloc `except ConfigError` du dispatcher l'appelle désormais. Ajouter :

```python
CREDENTIAL_FREE = {"build-number", "config", "build", "run", "test", "targets"}
```

et remplacer les deux occurrences de la liste littérale
(`asc_manager.py:868` et `:891`) par un test d'appartenance à cet ensemble.

Les handlers `xcode` ont une signature différente (pas de `account`,
`managers`, `dry_run`). Les adapter par une petite fonction d'enrobage :

```python
def _xcode_handler(func):
    """Adapte un handler xcode à la signature du dispatcher.

    Un build n'a ni compte ni managers: les ignorer explicitement vaut mieux
    que de faire semblant qu'il en existe un.
    """
    def wrapper(account, managers, dry_run, args, json_mode=False):
        try:
            return func(args, json_mode=json_mode)
        except AndpError as exc:
            return _error_envelope(func.__name__, exc, json_mode)
    return wrapper
```

Enregistrer dans `COMMANDS` : `"build"`, `"test"`, `"targets"`. Compléter
`USAGE`.

- [ ] **Étape 4 : vérifier le succès**

`pytest tests/test_xcode_envelope.py tests/test_xcode_aggregate.py -v`, puis
`pytest -q` en entier.

- [ ] **Étape 5 : commit**

```bash
git add andp/xcode/commands.py andp/asc/asc_manager.py tests/test_xcode_envelope.py tests/test_xcode_aggregate.py
git commit -m "feat(cli): commandes andp build, test et targets"
```

---

### Tâche 7 : commande `run`

**Fichiers :**
- Modifier : `andp/xcode/commands.py`, `andp/asc/asc_manager.py`
- Test : `tests/test_xcode_run.py`

**Interfaces :**
- Consomme : `simulator`, `device`, `runner.app_path`, `runner.build`.
- Produit : `commands.cmd_run(args, json_mode=False, project_root=".", run_process=None) -> int`

- [ ] **Étape 1 : test d'échec**

```python
import json
import pytest
from andp.asc.asc_manager import main


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ANDP_APP_DIR", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "andp.yml").write_text(
        "targets:\n  a:\n    scheme: A\n  b:\n    scheme: B\n")


def test_run_refuses_several_targets(capsys):
    rc = main(["run", "a", "b", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "bad_usage"


def test_run_in_dry_run_declares_it(capsys):
    rc = main(["run", "a", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["dry_run"] is True
```

Et, avec injection, dans le même fichier :

```python
from andp.xcode import commands
from andp.xcode.targets import Target


class Recorder(object):
    def __init__(self, payload=""):
        self.calls = []
        self.payload = payload

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        handle = kwargs.get("stdout")
        if handle is not None and hasattr(handle, "write"):
            handle.write(self.payload)
        return 0


def test_run_boots_installs_then_launches(tmp_path, monkeypatch):
    """L'ordre est le contrat: un launch avant install échoue silencieusement."""
    target = Target(name="a", scheme="A", platform="iOS",
                    destination="iPhone 15", configuration="Debug", os=None)
    app = tmp_path / "A.app"
    app.mkdir()
    (app / "Info.plist").write_text(
        '<?xml version="1.0"?><plist><dict>'
        '<key>CFBundleIdentifier</key><string>com.a</string></dict></plist>')

    monkeypatch.setattr(commands.runner, "app_path",
                        lambda *a, **k: str(app))
    monkeypatch.setattr(commands.simulator, "find",
                        lambda *a, **k: {"udid": "AAA", "name": "iPhone 15",
                                         "state": "Shutdown"})
    recorder = Recorder()
    commands.run_target(target, str(tmp_path), str(tmp_path), build_first=False,
                        run_process=recorder)
    verbs = [c[2] for c in recorder.calls if c[:2] == ["xcrun", "simctl"]]
    assert verbs.index("install") < verbs.index("launch")
    assert "boot" in verbs


def test_run_skips_boot_when_already_booted(tmp_path, monkeypatch):
    target = Target(name="a", scheme="A", platform="iOS",
                    destination="iPhone 15", configuration="Debug", os=None)
    app = tmp_path / "A.app"
    app.mkdir()
    (app / "Info.plist").write_text(
        '<?xml version="1.0"?><plist><dict>'
        '<key>CFBundleIdentifier</key><string>com.a</string></dict></plist>')
    monkeypatch.setattr(commands.runner, "app_path", lambda *a, **k: str(app))
    monkeypatch.setattr(commands.simulator, "find",
                        lambda *a, **k: {"udid": "AAA", "name": "iPhone 15",
                                         "state": "Booted"})
    recorder = Recorder()
    commands.run_target(target, str(tmp_path), str(tmp_path), build_first=False,
                        run_process=recorder)
    assert "boot" not in [c[2] for c in recorder.calls if c[:2] == ["xcrun", "simctl"]]
```

- [ ] **Étape 2 : vérifier l'échec**

`pytest tests/test_xcode_run.py -v` → échec.

- [ ] **Étape 3 : implémenter**

`commands.run_target(target, project_dir, project_root, build_first=True,
follow_logs=False, run_process=None)` :

1. si `build_first`, appeler `runner.build` ; en cas d'échec, rendre le résultat
   sans tenter d'installer
2. brancher selon la destination :
   - `id=<UDID>` → `device.install` puis `device.launch`
   - `platform: macOS` → lancer le binaire produit directement
   - sinon → `simulator.find`, `simulator.boot` **si l'état n'est pas `Booted`**,
     `simulator.install`, `simulator.launch`
3. avec `follow_logs`, enchaîner
   `xcrun simctl spawn <udid> log stream --predicate 'subsystem == "<bundle>"'`
4. rendre une enveloppe à une seule entrée, portant `udid` et `bundle_id`

`cmd_run` refuse plus d'une cible positionnelle : `XcodeError(code="bad_usage")`.

Enregistrer `"run"` dans `COMMANDS` et compléter `USAGE`.

- [ ] **Étape 4 : vérifier le succès**

`pytest tests/test_xcode_run.py -v`, puis `pytest -q`.

- [ ] **Étape 5 : commit**

```bash
git add andp/xcode/commands.py andp/asc/asc_manager.py tests/test_xcode_run.py
git commit -m "feat(cli): commande andp run (simulateur, appareil, macOS)"
```

---

### Tâche 8 : scripts shell et documentation

**Fichiers :**
- Modifier : `build.sh`, `build-matrix.sh`, `test.sh`
- Créer : `Documentation/Build.md`
- Modifier : `README.md` (section commandes)

**Interfaces :** aucune nouvelle — les scripts conservent leur signature
positionnelle. `.github/workflows/andp-release.yml:95` appelle
`./build.sh "$SCHEME" Release iphoneos` et ne doit pas être modifié.

- [ ] **Étape 1 : vérifier la signature actuelle**

```bash
grep -rn "build\.sh\|test\.sh\|build-matrix" .github/workflows/ infrastructure/ *.sh
```

Noter chaque appelant avant de toucher aux scripts.

- [ ] **Étape 2 : convertir `build.sh`**

Conserver `$1` scheme, `$2` configuration, `$3` sdk. Traduire `$3` :
`iphoneos` → `generic`, `iphonesimulator` → le simulateur par défaut (omettre
`--destination`). Router par le même helper que `sign.sh` :

```bash
andp_cli() { command -v andp >/dev/null 2>&1 && andp "$@" || python3 -m andp "$@"; }
```

- [ ] **Étape 3 : convertir `build-matrix.sh` et `test.sh`**

`build-matrix.sh` devient `andp_cli build --all`. `test.sh` devient
`andp_cli test --scheme "$1" --destination "$2" --os "$3"`, en conservant
l'appel final à `test-report.sh` : la génération de rapport reste en shell.

- [ ] **Étape 4 : vérifier**

```bash
CI=true ./build-matrix.sh          # sans xcodebuild → DRY-RUN annoncé, code 0
./build.sh Meeshy Release iphoneos
pytest -q
```

Vérifier qu'aucun script n'annonce plus un succès muet quand `xcodebuild` est
absent : la mention DRY-RUN doit apparaître sur stderr.

- [ ] **Étape 5 : documenter**

`Documentation/Build.md` : le bloc `targets:`, les six plateformes, les trois
formes de destination, les quatre commandes, l'enveloppe JSON, la table des
codes d'erreur. Ajouter le renvoi depuis `README.md`.

- [ ] **Étape 6 : commit**

```bash
git add build.sh build-matrix.sh test.sh Documentation/Build.md README.md
git commit -m "refactor(scripts): build.sh, build-matrix.sh et test.sh deviennent des enveloppes"
```

---

## Auto-relecture

**Couverture de la spec :**

| Section | Tâche |
|---|---|
| §4 architecture | 2–5 |
| §5 modèle de cibles | 2 |
| §5.5 répertoire projet | 2 (`project_dir`) |
| §6 destinations | 3 |
| §7 exécution, logs, CI, archive | 4 |
| §7.5 DRY-RUN | 6 |
| §8 `run` | 7 |
| §8.1 cible sans simulateur nommé | 5 (`find`) + 7 |
| §9 surface CLI | 6, 7 |
| §9.1 `CREDENTIAL_FREE` | 6 |
| §10 enveloppe, `_error_envelope` | 6 |
| §11 erreurs, `context` | 1 |
| §12 scripts | 8 |
| §13 tests | chaque tâche |

**Cohérence des types :** `Target` a six champs, identiques en tâches 2, 3, 5, 6
et 7. `BuildResult` a huit champs, défini en tâche 4 et consommé en 6 et 7.
`run_process` est le dernier paramètre partout.

**Point de vigilance :** la tâche 4 importe `_run_process` depuis `runner` dans
`simulator.py` et `device.py` — c'est un nom privé partagé entre modules du même
paquet, ce qui est acceptable ici mais doit rester le seul cas.
