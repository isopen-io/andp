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

```console
$ andp config
ANDP config (account 'primary')
  dir       ./.andp
  secrets   ./.andp/secrets.yml   project   ✅ configured
  policy    ./andp.yml            absent
```

En script, `andp config path secrets` n'imprime que le chemin sur stdout :

```bash
SECRETS=$(andp config path secrets)   # sort 1 si rien n'est résolu
ANDP_DIR=$(andp config dir)
```

`andp config --json` renvoie le même diagnostic sous forme d'enveloppe, avec
l'origine (`env` / `project` / `global` / `template`) et la liste des
emplacements inspectés.

## `./secrets.yml` n'est plus lu

L'emplacement historique n'est plus un niveau de la cascade. S'il traîne encore,
ANDP refuse de démarrer avec `config_misplaced` plutôt que de basculer
silencieusement en DRY-RUN — un mode d'échec qui ne se révélait qu'à l'upload,
après un build complet :

```bash
andp config migrate     # .andp/ en 0700, le fichier en 0600, n'écrase jamais
```

## Erreurs typées

Les erreurs de configuration font partie de la taxonomie `AndpError` : elles
portent `code`, `retryable`, `remediation`, et sont sérialisées dans l'enveloppe
`--json` comme n'importe quelle autre erreur.

| code | quand | retryable |
|---|---|---|
| `config_misplaced` | `./secrets.yml` existe encore à la racine | non |
| `config_not_found` | aucun fichier trouvé, template compris | non |
| `account_not_found` | le compte demandé est absent du fichier | non |

Les deux premiers portent aussi un bloc `context` listant les emplacements
inspectés, pour qu'un agent remédie sans avoir à explorer :

```console
$ andp verify --json
{"command": "verify", "ok": false,
 "error": {"code": "config_not_found",
           "message": "Aucun fichier de credentials trouvé.",
           "retryable": false,
           "remediation": "Créez .andp/secrets.yml à partir de secrets.example.yml.",
           "context": {"resolved": null,
                       "searched": ["./.andp/secrets.yml",
                                    "/Users/you/.andp/secrets.yml",
                                    "./secrets.example.yml"]}}}
```

## `$ANDP_CONFIG_DIR`, pas `$ANDP_HOME`

`ANDP_HOME` désigne le checkout du repo ANDP dans les workflows fournis. La
configuration se pilote avec `ANDP_CONFIG_DIR`, qui prend la tête de la cascade
et redirige aussi les répertoires runtime (`build/`, `metrics/`, `artifacts/`).
