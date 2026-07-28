# ANDP `build` / `run` / `test` — conception

**Date :** 2026-07-28
**Statut :** validé, prêt pour le plan d'implémentation

## 1. Problème

ANDP est aujourd'hui un client App Store Connect : il vérifie, téléverse, publie,
soumet. Produire le binaire est délégué à des scripts shell qui ne couvrent pas
ce que les projets déclarent réellement.

`examples/meeshy/project.yml` déclare neuf cibles sur cinq plateformes — iOS,
watchOS, tvOS, macOS, visionOS. `build-matrix.sh:8-10` en construit deux, sur une
seule plateforme :

```bash
SCHEMES=("Meeshy" "MeeshyWidgets")
CONFIGURATIONS=("Debug" "Release")
PLATFORMS=("iOS")
```

Quatre plateformes sur cinq ne sont jamais compilées. La matrice est codée en
dur dans un script, pas dérivée du projet.

Deux défauts aggravent la situation :

- `build.sh:41` et `test.sh:45` **annoncent un succès quand `xcodebuild` est
  absent**. C'est le faux vert silencieux que la spec précédente a éliminé côté
  configuration ; il subsiste ici.
- Aucune de ces commandes ne produit de sortie structurée. Un agent qui lance un
  build ne peut ni savoir quelle cible a échoué, ni décider s'il doit réessayer.

## 2. Objectif

Trois commandes natives, `andp build`, `andp run`, `andp test`, qui dérivent
leurs cibles d'une déclaration versionnée, couvrent toutes les plateformes du
projet, et rendent un résultat structuré par cible.

Les scripts shell existants deviennent des enveloppes minces autour de ces
commandes, en conservant leur signature d'appel actuelle.

## 3. Périmètre

Dans le périmètre :

- résolution des cibles depuis `andp.yml`, avec héritage et auto-détection
- traduction des cibles en arguments `-destination`
- invocation de `xcodebuild` (build, archive, exportArchive, test)
- cycle complet simulateur pour `run` : boot, install, launch, logs
- appareil physique en meilleur effort via `xcrun devicectl`
- enveloppe JSON agrégée multi-cibles
- conversion de `build.sh`, `build-matrix.sh`, `test.sh` en enveloppes

Hors périmètre :

- `test-report.sh` et la régression visuelle restent en shell — `andp test`
  exécute et rend un résultat structuré, il ne remplace pas la génération de
  rapport
- la gestion de pool de simulateurs (`simulator-manager.sh pool-init`,
  `mass-reset`) reste en shell : c'est de l'entretien de machine, pas du build
- la signature de code et le provisioning restent gérés par `sign.sh` et Xcode

## 4. Architecture

Un paquet `andp/xcode/`, symétrique de `andp/asc/` : une couche d'outillage
local, sœur de la couche App Store Connect, qui n'en dépend pas.

```
andp/xcode/
  targets.py       résolution des cibles (andp.yml + defaults + auto-détection)
  destination.py   dimensions → argument -destination
  runner.py        invocation xcodebuild, agrégation des résultats
  simulator.py     simctl : list / boot / install / launch / logs
  device.py        devicectl, meilleur effort
```

Direction des dépendances : `xcode/` → `errors.py`, `paths.py`. Jamais vers
`asc/` ni `core/`. Un build ne parle pas à Apple.

`targets.py` et `destination.py` sont des modules purs : ils ne lancent aucun
processus. `runner.py`, `simulator.py` et `device.py` reçoivent leur lanceur de
processus par injection, ce qui rend l'ensemble testable sans Xcode.

## 5. Modèle de cibles

### 5.1 Déclaration

Dans `andp.yml`, à la racine du projet — le fichier versionné de la spec
précédente, résolu par `paths.policy_path()` :

```yaml
targets:
  defaults:
    scheme: Meeshy
    configuration: Debug
  dev-ios:
    platform: iOS
    destination: "iPhone 15"
  dev-vision:
    platform: visionOS
    destination: "Apple Vision Pro"
  prod:
    platform: iOS
    destination: generic
    configuration: Release
```

Cinq champs, tous facultatifs dans une cible nommée :

| Champ | Valeurs | Défaut |
|---|---|---|
| `scheme` | nom d'un scheme Xcode | hérité de `defaults` |
| `platform` | `iOS`, `iPadOS`, `watchOS`, `tvOS`, `macOS`, `visionOS` | `iOS` |
| `destination` | `generic`, `id=<UDID>`, ou un nom de simulateur | `generic` |
| `configuration` | `Debug`, `Release`, ou toute configuration du projet | `Debug` |
| `os` | version de runtime, ex. `17.0` | absent (dernier disponible) |

`defaults` fournit la base ; une cible nommée surcharge champ par champ. Une
cible qui ne déclare que `platform: visionOS` hérite du reste. `defaults` n'est
jamais une cible en soi : `andp build defaults` échoue en `target_not_found`.

### 5.2 Contrat

```python
Target = namedtuple("Target", "name scheme platform destination configuration os")

def load_targets(project_root=".") -> dict
def resolve(name=None, project_root=".", scheme_lister=None) -> Target
def resolve_all(project_root=".", scheme_lister=None) -> list
def list_names(project_root=".") -> list
```

`scheme_lister` est injectable — par défaut celui de `runner.py`, qui appelle
`xcodebuild -list -json`. C'est ce qui garde `targets.py` testable sans
processus : les tests passent une fonction qui renvoie une liste figée.

### 5.3 Auto-détection

Sans bloc `targets:` dans `andp.yml`, `resolve()` interroge `scheme_lister` :

- **un seul scheme applicatif** → cible implicite nommée `default`, tous les
  champs à leur défaut
- **plusieurs schemes** → `ambiguous_scheme`, dont le `context` porte la liste
  des schemes trouvés et le bloc `targets:` à écrire

Le second cas est le cas de `examples/meeshy`. L'erreur ne se contente pas de
refuser : elle donne le YAML à coller.

### 5.4 Validation

Stricte, comme le garde-fou de typo des champs de classification d'âge
(`Documentation/StoreConfig.md:45`) :

- un champ inconnu dans une cible → `bad_target_config`, `context.unknown`
  portant le nom du champ et `context.allowed` la liste des champs valides
- une `platform` inconnue → `bad_target_config`, `context.allowed` portant les
  six valeurs admises
- `targets:` présent mais vide, ou non-dictionnaire → `bad_target_config`

Un avertissement laisserait une cible mal orthographiée compiler silencieusement
la mauvaise chose. C'est une erreur.

### 5.5 Répertoire du projet Xcode

`build.sh:8` et `test.sh:8` lisent déjà `ANDP_APP_DIR`, avec `examples/meeshy`
pour défaut. On conserve cette variable et on la place en tête d'une cascade
alignée sur celle de la configuration :

1. `$ANDP_APP_DIR`
2. `project.dir` dans `andp.yml`
3. `.` — le répertoire courant

Le défaut `examples/meeshy` disparaît : il n'a de sens que dans ce dépôt, et
c'est une valeur que `andp.yml` peut porter explicitement. Un projet sans
`.xcodeproj` ni `.xcworkspace` au répertoire résolu lève `no_project`, dont le
`context` porte le répertoire inspecté et la cascade consultée.

## 6. Destinations

`destination.py` traduit `platform` + `destination` + `os` en argument
`-destination`. Fonction pure, entièrement testable.

```python
def to_argument(target, action="build") -> str
```

Trois formes de `destination` :

| Forme | Résultat | Usage |
|---|---|---|
| `generic` | `generic/platform=iOS` | archive, compilation sans appareil |
| `id=<UDID>` | `platform=iOS,id=<UDID>` | appareil physique |
| tout autre texte | `platform=iOS Simulator,name=iPhone 15` | simulateur nommé |

Avec `os` renseigné, la forme nommée gagne `,OS=17.0`.

Correspondance des plateformes :

| `platform` | Simulateur | Appareil |
|---|---|---|
| `iOS` | `iOS Simulator` | `iOS` |
| `iPadOS` | `iOS Simulator` | `iOS` |
| `watchOS` | `watchOS Simulator` | `watchOS` |
| `tvOS` | `tvOS Simulator` | `tvOS` |
| `visionOS` | `visionOS Simulator` | `visionOS` |
| `macOS` | — | `macOS` |

`iPadOS` est un alias normalisé vers `iOS` : xcodebuild ne connaît pas ce nom de
plateforme. Il est accepté parce que c'est ce qu'un utilisateur écrit
naturellement, et la distinction se fait par le nom du simulateur.

`macOS` n'a pas de simulateur : la forme nommée y est refusée en
`bad_target_config` plutôt que traduite en quelque chose qui échouerait plus
loin avec un message de xcodebuild.

## 7. Exécution

### 7.1 Contrat

```python
BuildResult = namedtuple(
    "BuildResult", "target action ok duration exit_code destination log_path error")

def build(target, project_dir, archive=False, run_process=None) -> BuildResult
def test(target, project_dir, run_process=None) -> BuildResult
def list_schemes(project_dir, run_process=None) -> list
```

`run_process` est injectable. Par défaut `subprocess.run` ; les tests passent un
faux qui enregistre l'argv reçu et renvoie un code de sortie choisi. Aucun test
de cette spec ne lance `xcodebuild`.

### 7.2 Journalisation

La sortie complète de `xcodebuild` va dans
`.andp/build/logs/<cible>-<action>.log`, créé à la volée. Le chemin est dans le
résultat, donc dans l'enveloppe JSON : un agent qui voit un échec sait où lire.

Aucun parsing de la sortie, à une exception près : les lignes préfixées `error:`
— format stable de longue date — sont extraites, les dix dernières allant dans
`context.errors` de l'erreur. C'est ce qui distingue « le build a échoué » de
« le build a échoué parce que `MeeshyWatch` ne trouve pas `WatchConnectivity` ».

### 7.3 Signature en intégration continue

`build.sh:26-29` désactive la signature quand `$CI` ou `$GITHUB_ACTIONS` vaut
`true`. Le comportement est porté à l'identique — sans lui, toute compilation en
CI échoue faute de certificat.

### 7.4 Archive

`--archive` enchaîne deux invocations : `xcodebuild archive` vers
`.andp/build/<cible>.xcarchive`, puis `xcodebuild -exportArchive` vers
`.andp/build/exported/`. C'est le chemin que `sign.sh` consomme déjà —
`EXPORT_PATH="$ANDP_DIR/build/exported"`.

`--archive` requiert `destination: generic` ; toute autre destination lève
`bad_target_config`. Archiver pour un simulateur nommé ne produit rien
d'installable.

### 7.5 Mode DRY-RUN

Quand `xcodebuild` est introuvable, la commande n'invente pas un succès. Elle
rend une enveloppe portant `dry_run: true`, et un bandeau part sur stderr :

```json
{"command": "build", "ok": true, "dry_run": true, "results": [...]}
```

C'est la symétrie exacte du DRY-RUN de la couche ASC : la CI Linux reste verte,
et l'absence de compilation réelle est *déclarée*, pas tue. Le champ est dans
l'enveloppe, donc lisible par un agent sans heuristique.

Une seule condition déclenche le DRY-RUN : `xcodebuild` absent du `PATH`. Si
`xcodebuild` existe et échoue, c'est `build_failed`, franchement.

## 8. `run`

`andp run <cible>` enchaîne, pour une destination de simulateur :

1. résoudre la cible
2. démarrer le simulateur (`simctl boot`, puis `simctl bootstatus` pour attendre
   qu'il soit prêt) — sauf s'il l'est déjà
3. compiler, sauf si `--no-build`
4. localiser le `.app` produit, via `xcodebuild -showBuildSettings`
5. `simctl install` puis `simctl launch`
6. avec `--logs`, suivre `simctl spawn log stream` filtré sur l'identifiant du
   bundle, jusqu'à interruption

Pour `id=<UDID>`, le même enchaînement passe par `xcrun devicectl` en meilleur
effort : `devicectl device install app` puis `devicectl device process launch`.
Meilleur effort signifie que l'échec est rendu typé (`device_not_found`,
`device_install_failed`) sans tentative de contournement — appairage, confiance
et provisioning restent la responsabilité de l'utilisateur.

Pour `platform: macOS`, `run` lance directement le binaire produit.

`run` n'accepte **qu'une seule cible**. Lancer cinq applications simultanément
n'a pas de sens ; plusieurs cibles lèvent une erreur d'usage.

### 8.1 Cible sans simulateur nommé

`generic` est le défaut, et c'est le bon défaut pour `build` — mais on ne lance
rien sur une destination générique. Plutôt que de refuser, `run` choisit un
simulateur : le premier démarré pour la plateforme, sinon le premier disponible,
via `simctl list devices available -j`.

C'est le comportement de Xcode, et c'est ce qui fait que `andp run` fonctionne
sur un projet auto-détecté sans bloc `targets:`. Le choix n'est pas caché : la
destination retenue est dans le champ `destination` du résultat, donc dans
l'enveloppe JSON. Aucun simulateur disponible pour la plateforme lève
`simulator_not_found`, dont le `context` porte la plateforme cherchée.

Le boot de simulateur est la seule opération marquée `retryable: true` de cette
spec : `simctl boot` échoue de façon transitoire sous charge, ce que
`infrastructure/simulator-manager.sh:58-71` traite déjà par trois tentatives.

## 9. Surface CLI

```
andp build [cibles...] [--all] [--archive] [--scheme S] [--configuration C]
                       [--platform P] [--destination D] [--os V] [--json]
andp run <cible> [--no-build] [--logs] [--scheme S] [--configuration C]
                 [--platform P] [--destination D] [--os V] [--json]
andp test [cibles...] [--all] [--scheme S] [--configuration C]
                      [--platform P] [--destination D] [--os V] [--json]
andp targets [--json]
```

Les cinq drapeaux de surcharge — `--scheme`, `--configuration`, `--platform`,
`--destination`, `--os` — sont communs aux trois commandes et correspondent un
pour un aux champs d'une cible.

Sans cible nommée, la commande utilise la cible unique du projet, ou lève
`ambiguous_target` en listant les cibles disponibles. `--all` prend toutes les
cibles déclarées.

Les drapeaux de surcharge s'appliquent à la cible résolue, dans cet ordre de
priorité :

1. drapeau de ligne de commande
2. cible nommée dans `andp.yml`
3. `defaults` dans `andp.yml`
4. défaut du champ

`andp targets` existe pour l'agent : il rend la liste des cibles résolues, avec
leurs champs effectifs après héritage et l'argument `-destination` calculé. Un
agent découvre ce qu'il peut construire sans lire `andp.yml` ni connaître les
règles d'héritage.

### 9.1 Dispatcher

`asc_manager.main()` charge les credentials avant de router. Deux commandes en
sont déjà exemptées par une liste littérale (`asc_manager.py:868`) :

```python
if command in ("build-number", "config"):
```

Trois commandes de plus rendraient cette liste illisible. Elle devient un
ensemble nommé, déclaré à côté de `COMMANDS` :

```python
CREDENTIAL_FREE = {"build-number", "config", "build", "run", "test", "targets"}
```

Le dispatcher reste dans `asc/asc_manager.py`. Il y route déjà des commandes
non-ASC, ce qui est un défaut de placement — mais le déplacer casserait les
points d'import de la suite de tests pour un gain nul sur cette spec. C'est une
dette assumée et notée, pas un oubli.

## 10. Enveloppe multi-cibles

Une entrée par cible, dans l'ordre demandé :

```json
{
  "command": "build",
  "ok": false,
  "dry_run": false,
  "results": [
    {"target": "dev-ios", "ok": true, "duration": 42.1,
     "destination": "platform=iOS Simulator,name=iPhone 15",
     "log": ".andp/build/logs/dev-ios-build.log"},
    {"target": "dev-vision", "ok": false, "duration": 8.3,
     "destination": "platform=visionOS Simulator,name=Apple Vision Pro",
     "log": ".andp/build/logs/dev-vision-build.log",
     "error": {"code": "build_failed", "retryable": false,
               "message": "xcodebuild exited with 65",
               "remediation": "Read the log at .andp/build/logs/dev-vision-build.log",
               "context": {"errors": ["MeeshyVision/App.swift:12: error: ..."]}}}
  ]
}
```

Règles :

- l'exécution est **séquentielle** et **continue après un échec** — une cible
  visionOS cassée ne doit pas masquer l'état des quatre autres
- `ok` au niveau de l'enveloppe est la conjonction des `ok` de chaque cible
- le code de sortie est `0` si toutes réussissent, `1` sinon
- en mode humain, la même information part sur stdout sous forme de tableau, et
  les erreurs sur stderr

Une erreur qui survient **avant** toute exécution — `target_not_found`,
`no_project`, `ambiguous_scheme` — n'a pas de `results` : elle rend une
enveloppe d'erreur simple, `ok: false` et un `error` à la racine.

C'est la forme que le dispatcher produit déjà pour `ConfigError`
(`asc_manager.py:870-880`), mais en ligne, dans son propre bloc `except`. Les
handlers `build`, `run` et `test` en ont besoin à leur tour. Ces quatorze lignes
deviennent une fonction :

```python
def _error_envelope(command, exc, json_mode):
    """Enveloppe d'échec — JSON parsable, ou message humain sur stderr."""
```

Le bloc `ConfigError` du dispatcher l'appelle, les nouveaux handlers aussi, en
interceptant `AndpError`. Une seule forme d'échec pour tout l'outil, définie à
un seul endroit.

## 11. Erreurs

`XcodeError(AndpError)` suit le patron de `ConfigError` établi précédemment.

| Code | Retryable | Levé par |
|---|---|---|
| `target_not_found` | non | `targets.resolve` |
| `ambiguous_target` | non | CLI, sans cible ni `--all` |
| `ambiguous_scheme` | non | auto-détection, plusieurs schemes |
| `bad_target_config` | non | validation de `andp.yml` |
| `no_project` | non | résolution du répertoire projet |
| `build_failed` | non | `runner`, code de sortie non nul |
| `test_failed` | non | `runner`, en mode test |
| `export_failed` | non | `exportArchive` |
| `app_not_found` | non | `.app` introuvable après compilation |
| `simulator_not_found` | non | `simctl`, appareil inconnu |
| `simulator_boot_failed` | **oui** | `simctl boot`, échec transitoire |
| `device_not_found` | non | `devicectl` |
| `device_install_failed` | non | `devicectl install` |

### 11.1 `context` remonte dans `AndpError`

`ConfigError` porte déjà un `context` et surcharge `to_dict()` pour le
sérialiser. `XcodeError` en a le même besoin — pour les schemes disponibles, les
champs admis, les lignes `error:`, le répertoire inspecté.

Plutôt que de dupliquer ce mécanisme, `context` devient un champ facultatif
d'`AndpError`, et `ConfigError` cesse de surcharger `to_dict()` :

```python
@dataclass
class AndpError(Exception):
    code: str
    message: str
    retryable: bool
    remediation: str
    context: dict = field(default_factory=dict)
```

`to_dict()` n'émet `context` que s'il est non vide — c'est ce que fait déjà
`ConfigError`, et c'est ce que le test `test_context_is_absent_when_empty`
vérifie. Les constructions existantes passent toutes par mots-clés
(`from_asc_error`, `from_unexpected`, `ConfigError.__init__`) : aucune n'est
affectée par l'ajout d'un champ en fin de dataclass.

## 12. Scripts shell

Les trois scripts deviennent des enveloppes, **en conservant leur signature
positionnelle** — `.github/workflows/andp-release.yml:95` appelle
`./build.sh "$SCHEME" Release iphoneos` et ne doit pas être touché.

| Script | Devient |
|---|---|
| `build.sh SCHEME CONFIG SDK` | `andp build --scheme "$1" --configuration "$2" --destination <traduit de $3>` |
| `build-matrix.sh` | `andp build --all` |
| `test.sh SCHEME DEVICE OS` | `andp test --scheme "$1" --destination "$2" --os "$3"` |

Le troisième argument de `build.sh` (`iphoneos` / `iphonesimulator`) est traduit
dans le script : `iphoneos` → `generic`, `iphonesimulator` → le simulateur par
défaut. `-sdk` n'est pas exposé dans la CLI — il se recouvre avec
`-destination`, que Xcode recommande depuis longtemps.

Le troisième argument de `test.sh` est une version de runtime (`17.0`), d'où le
drapeau `--os` correspondant au champ `os` de la cible.

L'appel à `analytics-manager.sh record` (`build.sh:48-50`) reste dans le script :
c'est de l'instrumentation de dépôt, pas une responsabilité de l'outil.

## 13. Tests

Aucun test ne lance `xcodebuild`, `simctl` ou `devicectl`. Ce qui est vérifié :

| Fichier | Objet |
|---|---|
| `tests/test_xcode_targets.py` | héritage `defaults`, surcharges, validation stricte, auto-détection à un et plusieurs schemes |
| `tests/test_xcode_destination.py` | les trois formes, les six plateformes, l'alias `iPadOS`, le refus de `macOS` nommé |
| `tests/test_xcode_runner.py` | argv construit (via lanceur injecté), extraction des lignes `error:`, chemin de log, contournement CI |
| `tests/test_xcode_envelope.py` | agrégation multi-cibles, code de sortie, continuation après échec, `dry_run` |
| `tests/test_cli_build_run.py` | surface CLI, priorité des surcharges, `--all`, `andp targets` |

Le test qui compte le plus, en écho au faux vert de la spec précédente :
`xcodebuild` absent produit `dry_run: true` dans l'enveloppe, jamais un succès
muet.

## 14. Ce que cette spec ne fait pas

- elle ne remplace pas XcodeGen : `project.yml` reste la source du projet Xcode,
  `andp.yml` ne décrit que *ce qu'on en construit*
- elle ne parallélise pas les cibles : l'exécution séquentielle rend les logs
  lisibles et l'échec attribuable ; la parallélisation viendra si le temps de
  build le justifie
- elle ne gère pas la signature ni le provisioning
- elle ne déplace pas le dispatcher hors de `asc/asc_manager.py`
