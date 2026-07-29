# Configuration TestFlight & App Store par API — Guide ANDP

État de l'art : **juillet 2026** (App Store Connect API 4.4). Base URL : `https://api.appstoreconnect.apple.com` (format JSON:API).

Ce document résume ce qui est nécessaire pour configurer une application pour TestFlight et l'App Store **entièrement par API**, et comment ANDP l'implémente (package `andp/asc/`).

## 1. Prérequis compte

- **Apple Developer Program** actif (99 USD/an ; D-U-N-S pour les organisations).
- **Clé API App Store Connect** de type **Team Key** (les Individual Keys n'ont pas accès au Provisioning). Création : App Store Connect → *Users and Access → Integrations → App Store Connect API* — réservée à l'Account Holder/Admin. Le fichier **.p8** (ECDSA P-256) n'est téléchargeable **qu'une seule fois**.
- Rôles : `ADMIN` ou `APP_MANAGER` pour la soumission ; `DEVELOPER` suffit pour l'upload de builds.
- **Paid Applications Agreement** signé dans l'UI (Account Holder) avant toute app payante/IAP — non automatisable.

## 2. Authentification (module `auth.py`)

JWT **ES256** signé avec la clé .p8 :

| Élément | Valeur |
|---|---|
| Header | `alg: ES256`, `kid: <Key ID>`, `typ: JWT` |
| `iss` | Issuer ID (UUID, affiché dans Integrations) |
| `iat` / `exp` | epoch ; **durée max 20 minutes** |
| `aud` | `appstoreconnect-v1` (même pour les endpoints /v2 et /v3) |

Envoi : `Authorization: Bearer <token>`. ANDP régénère le token à 19 min avec marge de 60 s (`ASCAuth`).

## 3. Pipeline 100 % API

**Seule étape manuelle restante : créer la fiche app dans l'UI App Store Connect** (`POST /v1/apps` n'existe pas), et signer les agreements. Tout le reste :

| Étape | Endpoints | Module ANDP |
|---|---|---|
| App ID | `POST /v1/bundleIds` | `provisioning.py` |
| Capabilities | `POST /v1/bundleIdCapabilities` | `provisioning.py` |
| Certificat (CSR PEM) | `POST /v1/certificates` | `provisioning.py` |
| Profil de signature | `POST /v1/profiles` (pas de PATCH : delete + recreate) | `provisioning.py` |
| Fiche app (catégories, localisation, âge) | `PATCH /v1/apps`, `/v1/appInfos`, `/v1/appInfoLocalizations`, `/v1/ageRatingDeclarations` | `apps.py` |
| **Upload du build** | **Build Upload API** (ASC 4.1, GA fin 2025) : `POST /v1/buildUploads` → `POST /v1/buildUploadFiles` → PUT des chunks → `PATCH uploaded=true` | `builds.py` |
| Suivi du traitement | `GET /v1/builds` (`processingState`: PROCESSING/VALID/FAILED/INVALID) | `builds.py` |
| Export compliance | `PATCH /v1/builds/{id}` `usesNonExemptEncryption` (ou clé Info.plist `ITSAppUsesNonExemptEncryption`) | `builds.py` |
| Groupes TestFlight | `POST /v1/betaGroups` (publicLink, limites 1–10 000) | `testflight.py` |
| Testeurs | `POST /v1/betaTesters`, liaison `POST /v1/betaGroups/{id}/relationships/betaTesters` | `testflight.py` |
| « What to Test » | `POST/PATCH /v1/betaBuildLocalizations` | `testflight.py` |
| Beta App Review (testeurs externes) | `POST /v1/betaAppReviewSubmissions` | `testflight.py` |
| Version App Store | `POST /v1/appStoreVersions` (`releaseType`: MANUAL/AFTER_APPROVAL/SCHEDULED) | `appstore.py` |
| Métadonnées localisées | `POST/PATCH /v1/appStoreVersionLocalizations` (description, keywords, whatsNew…) | `appstore.py`, `metadata_manager.py` |
| Screenshots | `appScreenshotSets` → `appScreenshots` (réservation → PUT chunks → commit **MD5**) | `assets.py` |
| Rattacher le build | `PATCH /v1/appStoreVersions/{id}/relationships/build` | `appstore.py` |
| **Soumission au review** | **Review Submissions** : `POST /v1/reviewSubmissions` → `reviewSubmissionItems` → `submitted=true` (l'ancien `appStoreVersionSubmissions` a été **supprimé** en ASC 4.0) | `appstore.py` |
| **Retrait d'une soumission** | `PATCH /v1/reviewSubmissions/{id}` `canceled=true` — asynchrone : ASC répond `CANCELING`, la version ne redevient éditable qu'ensuite | `appstore.py` |
| Release | `POST /v1/appStoreVersionReleaseRequests` ; phased release : `appStoreVersionPhasedReleases` | `appstore.py` |
| Pricing | `GET /v3/appPricePoints` (filtre territoire) → `POST /v1/appPriceSchedules` (remplace le calendrier ; le système de tiers a disparu) | `pricing.py` |
| Territoires | `POST /v2/appAvailabilities` — remplacement complet du jeu, `availableInNewTerritories` préservé si non spécifié | `availability.py` |
| Classification d'âge | `PATCH /v1/ageRatingDeclarations/{id}` — modèle 2025 (descripteurs ternaires + booléens) | `agerating.py` |
| Webhooks (ASC 4.0) | `POST /v1/webhooks` — 12 événements (`BUILD_UPLOAD_STATE_UPDATED`, `APP_STORE_VERSION_APP_VERSION_STATE_UPDATED`…), signature HMAC-SHA256 `X-Apple-Signature` | *(à venir)* |

## 4. Limites de l'API

- **Rate limit** ~3500 req/h par clé (header `X-Rate-Limit`), 429 → retry (géré par `client.py` avec `Retry-After`).
- Pagination par curseur (`links.next`, `limit` ≤ 200) — gérée par `ASCClient.get_all`.
- Impossible par API : création de la fiche app, agreements/banking/tax, suppression de devices (seulement `DISABLED`), App Groups/conteneurs iCloud, certificats Developer ID, transfert d'app, réponses au Resolution Center.

## 5. Utilisation ANDP

```bash
# Renseigner .andp/secrets.yml (copie de secrets.example.yml) avec key_id, issuer_id, key_content

andp verify me.your.app                          # préflight de publication
andp upload build/exported/App.ipa               # Build Upload API
andp status me.your.app 42                       # polling processingState
andp testflight me.your.app "Beta" add jc@x.co   # groupes + testeurs
andp submit me.your.app 1.2.0                    # Review Submission
andp publish me.your.app 1.2.0 ./metadata        # métadonnées + médias localisés
andp store apply me.your.app                     # prix, territoires, âge
```

Les wrappers shell historiques (`./asc-manager.sh`, `./metadata-manager.sh`)
restent des enveloppes minces autour de ces mêmes commandes, pour les appelants
CI existants.

Pour une livraison complète et reprenable plutôt qu'une suite de commandes
unitaires, c'est la machine de release : `andp release start … --ship` puis
`andp release poll` — voir [Release.md](Release.md).

Sans credentials réels (placeholders de `secrets.example.yml`), toutes les commandes passent en **DRY-RUN** (aucun appel réseau, exit 0) — c'est ce qui permet à la CI de rester verte.

**Exception : `verify`.** C'est le préflight de publication ; son rôle est de dire la vérité sur la capacité à publier, donc il **échoue** (exit 1) tant que les credentials sont incomplets, en nommant précisément chaque champ manquant. Avec des credentials réels il enchaîne : signature JWT ES256 → authentification effective contre l'API (`GET /v1/apps`) → si un bundle id est fourni, vérification que la fiche app existe sur le compte. `PREFLIGHT PASSED` garantit que la chaîne upload/testflight/submit fonctionnera avec ces credentials.

## 6. Ce que l'API ne dit pas

Trois comportements de la Build Upload API ne figurent pas dans la documentation
et font échouer un client conforme à la spec : la relation `app` obligatoire,
`assetType: ASSET`, et le `uti` obligatoire. Les erreurs verbatim et le contrat
réellement observé sont dans
[articles/build-upload-api-observed-contract.md](articles/build-upload-api-observed-contract.md).

Un paquet malformé, lui, n'est pas rejeté par l'API du tout : l'upload est
acquitté, puis le build est écarté pendant le traitement, sans qu'aucun build
n'apparaisse. ANDP lit les `.appex` embarquées dans l'`.ipa` avant l'envoi pour
transformer ce rejet silencieux en erreur immédiate — voir
[Validation.md §2](Validation.md#2-the-package-gate).

## 7. Tests

Suite TDD complète : `tests/` (pytest, **616 tests**) — JWT, client JSON:API
(pagination, 429, erreurs), provisioning, fiche app, Build Upload, TestFlight,
Review Submissions, annulation de soumission, screenshots et previews, pricing,
territoires, classification d'âge, precheck, readiness, machine de release,
validation de paquet, surface MCP, couche xcode, et le dry-run de la CLI.
Lancée par `infrastructure/tests/run_tests.sh` et par le pipeline GitHub Actions.

## Sources

- https://developer.apple.com/documentation/appstoreconnectapi (spec 4.4, release notes 2.0 → 4.4)
- https://developer.apple.com/documentation/appstoreconnectapi/creating-api-keys-for-app-store-connect-api
- https://developer.apple.com/documentation/appstoreconnectapi/generating-tokens-for-api-requests
- https://developer.apple.com/documentation/appstoreconnectapi/build-uploads (WWDC25 sessions 324 & 328)
- https://developer.apple.com/documentation/appstoreconnectapi/webhook-notifications
- https://developer.apple.com/documentation/appstoreconnectapi/uploading-assets-to-app-store-connect
- https://developer.apple.com/documentation/appstoreconnectapi/identifying-rate-limits
- https://developer.apple.com/help/app-store-connect/ · https://developer.apple.com/support/roles/
