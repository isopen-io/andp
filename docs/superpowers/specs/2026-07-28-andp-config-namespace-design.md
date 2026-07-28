# Espace de nom `.andp/` — résolution de configuration

**Date :** 2026-07-28
**Statut :** design validé, prêt pour le plan d'implémentation
**Portée :** spec 1 sur 2. La spec 2 (`andp build` / `andp run` multi-cibles) dépend de celle-ci.

Deux sujets, liés par une même exigence — qu'ANDP reste exploitable par un agent
autonome : la résolution de configuration dans l'espace de nom `.andp/` (§1–§5), et
l'entrée des erreurs de configuration dans la taxonomie typée du projet (§6).

## 1. Problème

ANDP résout `secrets.yml` dans le répertoire courant uniquement (`andp/asc/config.py:52`) :

```python
path = "secrets.yml" if os.path.exists("secrets.yml") else "secrets.example.yml"
```

Trois conséquences :

1. **Aucun emplacement conventionnel.** Un projet consommateur qui écrit `.andp/secrets.yml`
   — ce que fait `meeshy.sh` — n'est jamais lu.
2. **Aucune configuration globale.** Rien n'est cherché sous `~`, donc les credentials
   doivent être redéposés dans chaque projet.
3. **Échec silencieux et tardif.** Quand `./secrets.yml` est absent, ANDP retombe sur le
   template `secrets.example.yml`, dont les placeholders donnent `is_configured() == False`,
   ce qui bascule le run en DRY-RUN sans erreur. Un pipeline `build → upload` passe donc
   ~15 minutes de build avant de casser à l'upload, alors que l'information manquait
   dès la seconde 0.

L'espace de nom `.andp/` existe déjà, mais à moitié : `andp/service.py:17` y écrit
l'état des releases (`.andp/state/`), tandis que les secrets et les artefacts sont
éparpillés à la racine du projet.

## 2. Décisions

### 2.1 Ligne de partage

Deux natures de fichiers, deux emplacements, un critère unique : **est-ce versionné ?**

| Nature | Emplacement | Versionné | Contenu |
|---|---|---|---|
| Config déclarative | `andp.yml` (racine projet) | oui, commité | policy, store, et plus tard `targets:` |
| Espace runtime | `.andp/` | non, gitignoré | `secrets.yml`, `state/`, `build/`, `metrics/`, `artifacts/` |

`andp.yml` ne change pas : il reste résolu à `<project_root>/andp.yml`, sans cascade.
`andp/policy.py` n'est pas modifié.

### 2.2 Pas de niveau legacy

`./secrets.yml` **n'est plus chargé**. La solution n'étant pas encore répandue, aucune
rétrocompatibilité de lecture n'est maintenue.

Mais l'ancien emplacement reste **détecté** : le retirer de la cascade sans le détecter
reproduirait exactement le bug décrit en §1 (chute silencieuse sur le template). Chargement
et détection sont deux choses distinctes ; seul le chargement disparaît.

### 2.3 Variable d'environnement : `ANDP_CONFIG_DIR`

`ANDP_HOME` est déjà utilisé pour désigner le checkout du repo ANDP
(`.github/workflows/andp-release.yml:58-60`, où il vaut parfois littéralement
`$GITHUB_WORKSPACE/.andp`). La réutiliser produirait une collision silencieuse.

### 2.4 Les erreurs de configuration entrent dans la taxonomie typée

ANDP se destine à des agents autonomes : une erreur n'est utile que si elle est
structurée. Les erreurs de configuration sont aujourd'hui la seule famille à échapper à
la taxonomie `AndpError` — elles remontent en texte brut, y compris en mode `--json`.

Cette spec les y fait entrer (§6). C'est une décision d'architecture qui dépasse le
strict correctif de résolution, assumée ici parce que les deux nouveaux codes d'erreur
n'auraient aucune valeur pour un agent s'ils ne parvenaient pas jusqu'à lui.

## 3. Contrat de résolution

### 3.1 Cascade de `secrets.yml` — premier trouvé gagne

| # | Chemin | `origin` |
|---|---|---|
| 1 | `$ANDP_CONFIG_DIR/secrets.yml` | `env` |
| 2 | `./.andp/secrets.yml` | `project` |
| 3 | `~/.andp/secrets.yml` | `global` |
| 4 | `./secrets.example.yml` | `template` |
| — | aucun | `None` → erreur `config_not_found` |

Le niveau 4 est conservé : le mode DRY-RUN des PR de fork en dépend, et c'est ce qui
garde la CI verte sans credentials (`tests/test_config.py:61`). Il reste à la racine
parce qu'il est **commité**, donc incompatible avec `.andp/` qui est gitignoré en bloc.
Sa sélection est annoncée sur stderr, jamais silencieuse.

Un `$ANDP_CONFIG_DIR` défini mais pointant vers un répertoire inexistant ne provoque pas
d'erreur : la cascade descend au niveau suivant.

### 3.2 Répertoires runtime — aucune cascade

Ce qui est *lu* cascade ; ce qui est *écrit* a une destination unique, sous `andp_dir()` :

```
.andp/state/       déjà en place (andp/service.py:17)
.andp/build/       ← build/ et infrastructure/build/
.andp/metrics/     ← metrics/
.andp/artifacts/   ← artifacts/
```

### 3.3 Détection de l'emplacement obsolète

`./secrets.yml` n'étant plus un niveau de la cascade, sa simple présence est une erreur :
soit il masque l'emplacement réellement lu (ambiguïté), soit il n'est pas lu du tout et
l'utilisateur croit le contraire. Dans les deux cas `load_account` échoue avec
`config_misplaced` **avant tout appel réseau**, quel que soit le niveau retenu :

```
❌ secrets.yml trouvé à la racine du projet, mais ANDP ne lit plus cet emplacement.
   Déplacez-le :  mkdir -p .andp && mv secrets.yml .andp/secrets.yml
   (ou lancez : andp config migrate)
```

Après `andp config migrate`, le fichier n'existe plus à la racine et la condition ne se
déclenche plus.

## 4. Module `andp/paths.py`

Nouveau module, pur : rien au-delà de `os.path.exists`, `os.environ` et
`os.path.expanduser`. Aucune lecture de fichier, aucun réseau — donc testable sans I/O
autre que la création de fichiers vides.

```python
ANDP_DIR_NAME = ".andp"

Resolution = namedtuple("Resolution", "path origin is_template")
# origin ∈ {"env", "project", "global", "template", None}

def andp_dir(project_root="."):
    """$ANDP_CONFIG_DIR si défini, sinon <project_root>/.andp"""

def resolve_config(filename, project_root="."):
    """Applique la cascade §3.1 et renvoie une Resolution.
    Ne lève jamais : un fichier introuvable donne path=None, origin=None.
    C'est l'appelant (load_account) qui transforme cela en erreur."""

def misplaced_secrets(project_root="."):
    """Chemin de ./secrets.yml s'il existe, sinon None. Support de §3.3.
    Ne lève jamais."""
```

`paths.py` est donc entièrement non-levant : il décrit ce qu'il trouve, il ne décide pas.
Toute la politique d'erreur vit dans `andp/asc/config.py`.

`andp/asc/config.py` consomme `resolve_config` et porte l'`origin` sur `AccountConfig`.
Ce champ n'est pas cosmétique : c'est lui qui permet à `andp verify` d'annoncer
« credentials chargés depuis `~/.andp/secrets.yml` » au lieu de laisser deviner.

## 5. Surface CLI — `andp config`

Convention héritée de `build-number` (`asc_manager.py:653`) : **stdout ne porte que la
valeur**, tout le reste va sur stderr, pour que la substitution de commande soit sûre
en bash.

```bash
andp config                   # diagnostic humain (défaut)
andp config path secrets      # → .andp/secrets.yml     (stdout pur)
andp config path policy       # → andp.yml              (stdout pur)
andp config dir               # → .andp                 (stdout pur)
andp config migrate           # déplace ./secrets.yml → .andp/secrets.yml
```

`path` accepte exactement deux valeurs, `secrets` et `policy` ; toute autre valeur est une
erreur d'usage (sortie 2). `path secrets` sort 1 si aucun fichier n'est résolu, pour que
`set -e` en bash s'arrête au bon endroit.

Sortie de `andp config` sans argument :

```
ANDP config (account 'primary')
  dir       .andp                     project
  secrets   .andp/secrets.yml         project      ✅ configured
  policy    andp.yml                  absent       (defaults)
```

`--json` est accepté sur chaque forme, comme sur toutes les autres commandes.

`config` ne requiert aucun credential : elle rejoint `build-number` dans l'exception de
`main()` (`asc_manager.py:747`) qui tolère `ConfigError` pour les commandes n'en ayant
pas besoin.

**`andp config migrate`** crée `.andp/` en `0700`, déplace le fichier en préservant `0600`,
**refuse d'écraser** une cible existante (sortie non nulle, message explicite), et est
idempotent : sans rien à migrer il l'annonce et sort 0. Il ne touche à aucun autre fichier.

## 6. Erreurs

Deux codes ajoutés à la taxonomie typée (`code` / `message` / `retryable` /
`remediation`), dont §6.1 fixe l'emplacement définitif en `andp/errors.py` :

| code | retryable | déclencheur | remediation |
|---|---|---|---|
| `config_misplaced` | `False` | `./secrets.yml` existe (§3.3) | `mkdir -p .andp && mv secrets.yml .andp/secrets.yml` ou `andp config migrate` |
| `config_not_found` | `False` | aucun fichier trouvé, template compris | créer `.andp/secrets.yml` à partir de `secrets.example.yml` |

### 6.1 Taxonomie unifiée — `andp/errors.py`

**Objectif : ANDP reste utilisable par un agent autonome, donc toute erreur remonte
structurée jusqu'à la surface, sans exception.**

État actuel. La dépendance entre packages va `core` → `asc` :
`andp/core/release.py:17,21` importe `asc/appstore.py` et `asc/client.py`, tandis
qu'`andp/asc/` n'importe jamais `core/`. Faire dépendre `asc/config.py` de
`core/errors.py` installerait donc une dépendance bidirectionnelle entre les deux
packages.

`errors.py` n'est pas de la logique métier : c'est du vocabulaire transverse. Il remonte
à la racine du package, en module feuille dépendu par tous et ne dépendant de rien :

```
andp/errors.py          ← feuille, n'importe que dataclasses
   ↑        ↑        ↑
 asc/     core/   service.py
```

`ConfigError` en devient une sous-classe :

```python
# andp/errors.py
class ConfigError(AndpError):
    """Erreur de configuration — un AndpError qui n'est jamais retryable."""
    def __init__(self, message, code="config_error", remediation=""):
        super().__init__(code=code, message=message,
                         retryable=False, remediation=remediation)
```

Conséquences :

- **Une seule taxonomie.** `to_dict()` est disponible sur toute erreur, donc toute erreur
  est sérialisable en JSON sans conversion ad hoc. `retryable=False` est vrai par nature
  pour la configuration : une config cassée ne se répare pas en réessayant.
- **Le bloc de traduction disparaît.** `service.py:26-32` existait précisément parce que
  les deux types étaient étrangers (*« so callers have one error type to catch »*).
  `except AndpError` attrape désormais `ConfigError` : `_managers_for` n'a plus besoin
  de traduire, et le code net diminue.
- **Rien ne casse.** Les quatre `except ConfigError` (`service.py:30`,
  `asc_manager.py:744`, `metadata_manager.py:67`) et `tests/test_config.py:56,70`
  restent valides — c'est une sous-classe.
- **Évolutif pour la spec 2.** `BuildError`, `SimulatorError`, `DeviceError` suivent le
  même patron : xcodebuild qui échoue (non retryable), un simulateur qui ne boote pas
  (retryable), un device non appairé (non retryable, remediation explicite).

`andp/core/errors.py` est supprimé ; ses 12 sites d'import passent à `andp.errors`.
Aucune API publique n'est touchée : `pyproject.toml` n'expose que `andp.cli:main`.

### 6.2 Invariant : `--json` produit toujours du JSON

Aujourd'hui, une erreur de configuration court-circuite l'enveloppe. `asc_manager.py:749`
et `metadata_manager.py:68` font :

```python
except ConfigError as exc:
    print(f"Error: {exc}")     # texte brut, MÊME avec --json
    return 1
```

Un agent qui lance `andp verify --json` sans fichier de credentials reçoit donc du texte
non parsable sur stdout et perd tout : code, `retryable`, remediation. Aucun test ne
couvre ce chemin (`tests/test_json_output.py` teste des credentials *placeholder*,
jamais *absents*).

**Invariant établi par cette spec : en mode `--json`, stdout est toujours du JSON valide,
y compris pour les erreurs de configuration et d'usage.** Les deux sites ci-dessus
sérialisent l'enveloppe standard du projet (`service.py:719`) :

```json
{"command": "verify", "ok": false,
 "error": {"code": "config_misplaced",
           "message": "secrets.yml trouvé à la racine du projet, mais ANDP ne lit plus cet emplacement.",
           "retryable": false,
           "remediation": "mkdir -p .andp && mv secrets.yml .andp/secrets.yml (ou : andp config migrate)"}}
```

En mode humain, le rendu texte actuel est conservé.

### 6.3 Diagnostic exploitable par un agent

`config_misplaced` et `config_not_found` portent, en plus des quatre champs standard, un
bloc `context` qui dit ce qui a été inspecté — un agent peut alors remédier sans deviner
ni relancer la commande pour explorer :

```json
"context": {"resolved": null,
            "misplaced": "./secrets.yml",
            "searched": ["$ANDP_CONFIG_DIR/secrets.yml", "./.andp/secrets.yml",
                         "~/.andp/secrets.yml", "./secrets.example.yml"]}
```

Le champ `origin` (§4) apparaît dans ce bloc dès qu'un fichier est résolu, ce qui rend
`andp config --json` directement consommable comme diagnostic.

## 7. Sites à migrer

### Python (8 fichiers)

| Fichier | Changement |
|---|---|
| `andp/errors.py` | nouveau — `core/errors.py` remonté, `ConfigError(AndpError)` ajouté (§6.1) |
| `andp/core/errors.py` | supprimé ; 12 imports repointés vers `andp.errors` |
| `andp/paths.py` | nouveau (§4) |
| `andp/asc/config.py:52` | consomme `resolve_config` ; `AccountConfig` porte `origin` ; lève les deux nouveaux codes |
| `andp/asc/asc_manager.py` | `COMMANDS["config"]` + `_cmd_config` ; `:99` affiche l'origine résolue ; `:749` sérialise l'enveloppe en mode `--json` (§6.2) |
| `andp/asc/metadata_manager.py:68` | idem `:749` — plus de `print(f"Error: {exc}")` nu |
| `andp/service.py:26-32` | le bloc de traduction `ConfigError` → `AndpError` disparaît (§6.1) |
| `andp/service.py:314,358,737` | les remediations « Fill in secrets.yml » citent le chemin résolu |

Les 12 imports à repointer : `service.py:12,140,214,304,349,442,512,605,654`,
`publish.py:18`, `core/state.py:13`, `core/release.py:21`.

### Shell (6 fichiers)

| Fichier | Changement |
|---|---|
| `sign.sh:25` | `SECRETS=$(andp config path secrets)` puis lecture du team_id depuis ce chemin. Corrige au passage la condition `if sys.path[0]+'/secrets.yml'`, une concaténation de chaînes toujours vraie, qui rend le fallback inatteignable |
| `sign.sh` | `EXPORT_PATH` et `EXPORT_OPTIONS_PLIST` → `.andp/build/` |
| `archive.sh` | `ARCHIVE_PATH` → `.andp/build/` |
| `infrastructure/analytics-manager.sh:8` | `METRICS_DIR=".andp/metrics"` |
| `infrastructure/security-auditor.sh:36` | test de présence via `andp config path secrets` |
| `infrastructure/governance-report.sh:60` | idem |

Les scripts n'appellent pas `andp` directement : le binaire n'est pas garanti dans le
`PATH` des runners, où les workflows utilisent déjà `python3 -m andp`
(`action.yml:53`). Ils passent donc par un helper unique, défini une fois :

```bash
andp_cli() { command -v andp >/dev/null 2>&1 && andp "$@" || python3 -m andp "$@"; }
```

### CI (6 fichiers)

| Fichier | Changement |
|---|---|
| `action.yml:50` | `mkdir -p "$WORKDIR/.andp"` puis `> "$WORKDIR/.andp/secrets.yml"` |
| `.github/actions/testflight-readiness/action.yml:87` | idem |
| `.github/actions/appstore-readiness/action.yml:105` | idem |
| `.github/workflows/andp-release.yml:103,109,115` | chemins `build/` → `.andp/build/` |
| `Jenkinsfile:30-31` | idem |
| `azure-pipelines.yml:28-30` | idem |

Les trois actions écrivent le fichier dans un `mktemp -d` jetable puis lancent ANDP
immédiatement depuis ce répertoire. Les consommateurs externes appellent l'action, jamais
le chemin : **aucun utilisateur en aval n'est impacté** par ce changement.

### Documentation (12 fichiers)

`README.md:31`, `SECURITY.md:21-24`, `Documentation/Security.md:7-8`,
`Documentation/Operations.md:15,37`, `Documentation/Migration.md:11,21`,
`Documentation/AgentGuide.md:44,393,400`, `Documentation/ASC-API.md:63,73`,
`Documentation/Troubleshooting.md:14,31`, `Documentation/BuildNumber.md:50,59`,
`Documentation/PublishReadiness.md:143`, `Documentation/Architecture/Diagrams.md:111,141`,
`Documentation/articles/capacitor-without-appflow.md:22`.

Le quickstart `cp secrets.example.yml secrets.yml` devient
`mkdir -p .andp && cp secrets.example.yml .andp/secrets.yml`.

### `.gitignore`

Retirer `build/`, `metrics/` et `secrets.yml` ; la ligne `.andp/` déjà présente couvre
l'ensemble. Corrige au passage que `artifacts/` n'était ignoré par aucune règle alors que
le répertoire est produit par les scripts.

## 8. Tests

### Nouveau `tests/test_paths.py`

Table-driven sur la cascade :

- chaque niveau gagne lorsqu'il est seul présent
- la priorité est respectée quand plusieurs coexistent (`env` > `project` > `global` > `template`)
- `origin` est correct à chaque niveau
- `$ANDP_CONFIG_DIR` pointant vers un répertoire inexistant fait descendre la cascade sans erreur
- `~` est expansé (via `monkeypatch.setenv("HOME", tmp_path)`)
- aucun fichier → `path is None`, `origin is None`

### Test de non-régression

Il encode le bug d'origine et doit échouer sur le code actuel :

```python
def test_root_secrets_never_silently_falls_back_to_template(tmp_path, monkeypatch):
    (tmp_path / "secrets.yml").write_text(REAL_SECRETS)          # l'ancien emplacement
    (tmp_path / "secrets.example.yml").write_text(PLACEHOLDERS)  # le piège
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as e:                        # cf. §6.1
        load_account("primary")
    assert e.value.code == "config_misplaced"   # et surtout PAS un DRY-RUN silencieux
```

Un second test vérifie §6.1 : le même scénario via `service.verify()` produit une
enveloppe portant `error.code == "config_misplaced"` — le code typé traverse les couches
sans conversion, `ConfigError` étant désormais un `AndpError`.

### Tests de l'invariant JSON (§6.2)

Le trou le plus important, aujourd'hui non couvert : **toute** commande en `--json` doit
produire du JSON parsable même sans configuration.

```python
@pytest.mark.parametrize("cmd", [
    ["verify"], ["upload", "app.ipa"], ["status", "me.app", "42"],
    ["submit", "me.app", "1.0"], ["precheck", "me.app", "1.0"],
    ["readiness", "testflight", "me.app"], ["store", "apply", "me.app"],
])
def test_json_stays_parsable_without_any_config(cmd, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)          # ni .andp/, ni ~/.andp/, ni template
    main(cmd + ["--json"])
    payload = json.loads(capsys.readouterr().out)   # ne doit pas lever
    assert payload["ok"] is False
    assert payload["error"]["code"] == "config_not_found"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["remediation"]           # non vide
```

Un test symétrique couvre `config_misplaced`, et un troisième vérifie que le bloc
`context` de §6.3 liste bien les emplacements inspectés.

### Test de la structure de la taxonomie (§6.1)

```python
def test_config_error_is_an_andp_error():
    err = ConfigError("boom", code="config_misplaced", remediation="fix it")
    assert isinstance(err, AndpError)          # une seule taxonomie
    assert err.to_dict()["retryable"] is False # jamais retryable par construction
```

### `tests/conftest.py`

`configured_dir` (`:108`) écrit désormais dans `.andp/secrets.yml`. Les tests qui
l'utilisent déjà passent sans modification. Nouvelle fixture `misplaced_secrets_dir`
pour le cas ci-dessus.

### Les 25 fichiers écrivant `secrets.yml` en dur

Réécrits pour consommer `configured_dir` au lieu de dupliquer l'écriture. C'est mécanique,
et cela supprime la duplication qui rend ce type de changement coûteux.

### `tests/test_config.py`

Réécrit autour de la nouvelle cascade. Son cas « sans `secrets.yml`, on retombe sur
`secrets.example.yml` » reste valide, le template étant conservé au niveau 4.

## 9. Ordre d'implémentation

Chaque étape laisse la suite verte :

0. **Taxonomie** — `core/errors.py` → `andp/errors.py`, `ConfigError(AndpError)`,
   12 imports repointés, suppression du bloc de traduction `service.py:26-32`.
   Étape autonome : elle ne dépend de rien de ce qui suit et se valide seule sur la
   suite existante.
1. `andp/paths.py` + `tests/test_paths.py`
2. `andp/asc/config.py` + les deux codes d'erreur + le test de non-régression
3. Invariant JSON (§6.2) : `asc_manager.py:749`, `metadata_manager.py:68`,
   et les tests paramétrés
4. `andp config` (CLI)
5. `conftest.py` + migration des 25 fichiers de test
6. Scripts shell
7. CI et actions
8. Documentation et `.gitignore`

L'étape 0 en tête n'est pas un détail d'ordonnancement : sans taxonomie unifiée, les
étapes 2 et 3 devraient inventer un mécanisme de transport pour les codes d'erreur,
qu'il faudrait ensuite défaire.

## 10. Hors périmètre

Traité dans la spec 2, qui s'appuiera sur l'emplacement de config tranché ici :

- `andp build` / `andp run` en Python natif, les scripts shell devenant des wrappers
- cibles nommées déclarées dans `andp.yml` (`targets:`), avec les 4 dimensions
  scheme × plateforme × destination × configuration
- `andp build` compile ; `--archive` va jusqu'à l'IPA
- `andp run` : simulateur complet (boot → build → install → launch → logs),
  device physique en best-effort via `xcrun devicectl`
- invocation multi-cibles, remplaçant `build-matrix.sh`
