# Configuration TestFlight & App Store par API — Guide ANDP

État de l'art : **juillet 2026** (App Store Connect API 4.4). Base URL : `https://api.appstoreconnect.apple.com` (format JSON:API).

Ce document résume ce qui est nécessaire pour configurer une application pour TestFlight et l'App Store **entièrement par API**, et comment ANDP l'implémente (`infrastructure/asc/`).

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
| Release | `POST /v1/appStoreVersionReleaseRequests` ; phased release : `appStoreVersionPhasedReleases` | `appstore.py` |
| Pricing / territoires | `POST /v1/appPriceSchedules`, `/v3/appPricePoints`, `POST /v2/appAvailabilities` | *(à venir)* |
| Webhooks (ASC 4.0) | `POST /v1/webhooks` — 12 événements (`BUILD_UPLOAD_STATE_UPDATED`, `APP_STORE_VERSION_APP_VERSION_STATE_UPDATED`…), signature HMAC-SHA256 `X-Apple-Signature` | *(à venir)* |

## 4. Limites de l'API

- **Rate limit** ~3500 req/h par clé (header `X-Rate-Limit`), 429 → retry (géré par `client.py` avec `Retry-After`).
- Pagination par curseur (`links.next`, `limit` ≤ 200) — gérée par `ASCClient.get_all`.
- Impossible par API : création de la fiche app, agreements/banking/tax, suppression de devices (seulement `DISABLED`), App Groups/conteneurs iCloud, certificats Developer ID, transfert d'app, réponses au Resolution Center.

## 5. Utilisation ANDP

```bash
# Renseigner secrets.yml (copie de secrets.example.yml) avec key_id, issuer_id, key_content

./asc-manager.sh verify me.meeshy.app                        # préflight de publication
./asc-manager.sh upload build/exported/Meeshy.ipa            # Build Upload API
./asc-manager.sh status me.meeshy.app 42                     # polling processingState
./asc-manager.sh testflight me.meeshy.app "Beta" add jc@x.co # groupes + testeurs
./asc-manager.sh submit me.meeshy.app 1.2.0                  # Review Submission
./metadata-manager.sh sync metadata.json                     # métadonnées localisées
```

Sans credentials réels (placeholders de `secrets.example.yml`), toutes les commandes passent en **DRY-RUN** (aucun appel réseau, exit 0) — c'est ce qui permet à la CI de rester verte.

**Exception : `verify`.** C'est le préflight de publication ; son rôle est de dire la vérité sur la capacité à publier, donc il **échoue** (exit 1) tant que les credentials sont incomplets, en nommant précisément chaque champ manquant. Avec des credentials réels il enchaîne : signature JWT ES256 → authentification effective contre l'API (`GET /v1/apps`) → si un bundle id est fourni, vérification que la fiche app existe sur le compte. `PREFLIGHT PASSED` garantit que la chaîne upload/testflight/submit fonctionnera avec ces credentials.

## 6. Tests

Suite TDD complète : `infrastructure/tests/python/` (pytest, 71 tests) — JWT, client JSON:API (pagination, 429, erreurs), provisioning, fiche app, Build Upload, TestFlight, Review Submissions, screenshots, CLI dry-run. Lancée par `infrastructure/tests/run_tests.sh` et par le pipeline GitHub Actions.

## Sources

- https://developer.apple.com/documentation/appstoreconnectapi (spec 4.4, release notes 2.0 → 4.4)
- https://developer.apple.com/documentation/appstoreconnectapi/creating-api-keys-for-app-store-connect-api
- https://developer.apple.com/documentation/appstoreconnectapi/generating-tokens-for-api-requests
- https://developer.apple.com/documentation/appstoreconnectapi/build-uploads (WWDC25 sessions 324 & 328)
- https://developer.apple.com/documentation/appstoreconnectapi/webhook-notifications
- https://developer.apple.com/documentation/appstoreconnectapi/uploading-assets-to-app-store-connect
- https://developer.apple.com/documentation/appstoreconnectapi/identifying-rate-limits
- https://developer.apple.com/help/app-store-connect/ · https://developer.apple.com/support/roles/
