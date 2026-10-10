# Les champs App Store Connect d'une app et de sa soumission

Référence relevée le **2026-10-09**. Elle vient de quatre sources :

- la spécification OpenAPI de l'App Store Connect API **4.5.1**, publiée par Apple le 2026-10-06 et téléchargée sur [App Store Connect API](https://developer.apple.com/sample-code/app-store-connect/app-store-connect-openapi-specification.zip) ;
- l'aide App Store Connect ;
- les notes de version de l'API ;
- des **observations faites sur une app en production** (me.meeshy.app). Quand une observation contredit la documentation, la colonne « andp » applique le contrat observé, et le texte le signale.

Pour chaque champ, les tableaux donnent :

- son sens ;
- les valeurs admises ou la limite ;
- sa **portée** : `app`, `langue` (par langue de l'app), `version`, `version × langue`, `appareil` ;
- s'il est **requis à la soumission** ;
- la ressource de l'API qui l'expose ;
- la clé `andp.yml` (bloc `store:`) ou le fichier du dossier de métadonnées qui le renseigne.

Une case « — » dans la colonne andp signifie qu'andp ne pilote pas ce champ. La raison est donnée sous le tableau.

`andp store plan` montre le diff sans rien écrire, `andp store apply` l'écrit, et `andp readiness appstore` bloque sur les champs requis. Le mode d'emploi est dans [StoreConfig.md](StoreConfig.md).

## 1. L'app (`apps/{id}`, PATCH)

| Champ API | Sens | Valeurs / limite | Portée | Requis | andp |
|---|---|---|---|---|---|
| `contentRightsDeclaration` | « L'app contient-elle, montre-t-elle ou donne-t-elle accès à du contenu de tiers ? » Si oui, vous attestez détenir les droits nécessaires dans chaque pays [H1] | `DOES_NOT_USE_THIRD_PARTY_CONTENT`, `USES_THIRD_PARTY_CONTENT` | app | **oui** (bloque si vide) | `app.content_rights` |
| `primaryLocale` | langue principale : celle qui s'affiche quand la langue de l'utilisateur n'est pas fournie | code de langue ASC (`fr-FR`, `en-US`…) | app | oui (fixée à la création) | `app.primary_locale` |
| `accessibilityUrl` | page publique décrivant l'accessibilité de l'app. Affichée avec les Accessibility Nutrition Labels, sauf sur Apple TV [H9] | URL http(s) | app | non | `app.accessibility_url` |
| `subscriptionStatusUrl` / `…Version` | URL des notifications serveur App Store (abonnements) | URL, `V1` ou `V2` | app | non (seulement avec des achats intégrés) | `app.subscription_status_url[_version]` |
| `subscriptionStatusUrlForSandbox` / `…VersionForSandbox` | la même chose pour le bac à sable | URL, `V1` ou `V2` | app | non | `app.subscription_status_url_sandbox`, `…_version_sandbox` |
| `streamlinedPurchasingEnabled` | achat simplifié (Family Sharing / Ask to Buy) | booléen | app | non | `app.streamlined_purchasing` |
| `bundleId`, `sku`, `name` | identité. `name` reflète le nom de la langue principale | — | app | fixés à la création | — (non modifiables sans risque) |
| `isOrEverWasMadeForKids` | l'app est ou a été « Made for Kids » | booléen, **lecture seule** | app | — | affiché par `store plan` |

Contenu généré par les utilisateurs : aucune source Apple ne dit s'il compte comme « contenu tiers » pour `contentRightsDeclaration`. La guideline 1.2 le régit séparément (filtrage, signalement, blocage, contact). Les aperçus de liens (titres et vignettes de sites tiers) relèvent en revanche, à la lettre de [H1], de « montrer du contenu tiers ».

## 2. Catégories (`appInfos/{id}`, relations, sur l'appInfo modifiable)

| Relation | Sens | Valeurs | Requis | andp |
|---|---|---|---|---|
| `primaryCategory` | catégorie principale | identifiant `appCategories` : `BOOKS`, `BUSINESS`, `DEVELOPER_TOOLS`, `EDUCATION`, `ENTERTAINMENT`, `FINANCE`, `FOOD_AND_DRINK`, `GAMES`, `GRAPHICS_AND_DESIGN`, `HEALTH_AND_FITNESS`, `LIFESTYLE`, `MAGAZINES_AND_NEWSPAPERS`, `MEDICAL`, `MUSIC`, `NAVIGATION`, `NEWS`, `PHOTO_AND_VIDEO`, `PRODUCTIVITY`, `REFERENCE`, `SHOPPING`, `SOCIAL_NETWORKING`, `SPORTS`, `STICKERS`, `TRAVEL`, `UTILITIES`, `WEATHER` (relevé par `GET /v1/appCategories?filter[platforms]=IOS`) | **oui** | `categories.primary` ou `primary_category.txt` |
| `secondaryCategory` | catégorie secondaire | mêmes valeurs | non | `categories.secondary` ou `secondary_category.txt` |
| `primarySubcategoryOne` / `Two`, `secondarySubcategoryOne` / `Two` | sous-catégories. **Seuls `GAMES` et `STICKERS` en ont** (`GAMES_PUZZLE`, `STICKERS_EMOJI_AND_EXPRESSIONS`…) [H1] | identifiant préfixé par le parent | non | `categories.primary_subcategory_one`… ou `primary_first_sub_category.txt`… |

L'appInfo « en ligne » (`READY_FOR_DISTRIBUTION`) refuse les écritures. andp écrit sur l'appInfo modifiable, qui n'existe que pendant la préparation d'une version. Sans elle, `store plan` marque ces champs 🔒.

## 3. Informations par langue de l'app (`appInfoLocalizations`)

| Champ | Sens | Limite | Portée | Requis | andp |
|---|---|---|---|---|---|
| `name` | nom affiché sur l'App Store | 2 à **30 caractères** [H1]. Modifiable seulement avec une nouvelle version | langue | **oui** (et pour créer une langue) | `localizations.<l>.name` ou `<l>/name.txt` |
| `subtitle` | phrase sous le nom | **30 caractères** | langue | non | `subtitle` ou `<l>/subtitle.txt` |
| `privacyPolicyUrl` | politique de confidentialité. Aussi exigée **dans** l'app (guideline 5.1.1(i)) [H4][G] | URL | langue | **oui** pour iOS et macOS | `privacy_policy_url` / `privacy_url` ou `<l>/privacy_url.txt` |
| `privacyChoicesUrl` | page où l'utilisateur consulte, modifie ou supprime ses données [H5] | URL | langue | non | `privacy_choices_url` ou `<l>/privacy_choices_url.txt` |
| `privacyPolicyText` | politique en texte, **tvOS seulement** | texte | langue | tvOS | `privacy_policy_text` ou `<l>/apple_tv_privacy_policy.txt` |

## 4. La version (`appStoreVersions/{id}`, PATCH)

| Champ | Sens | Valeurs | Requis | andp |
|---|---|---|---|---|
| `copyright` | « année + titulaire ». Le symbole © est ajouté par Apple [H2] | texte | **oui** | `version.copyright` ou `copyright.txt` |
| `releaseType` | sortie après approbation : manuelle, automatique, ou automatique pas avant une date [H17] | `MANUAL`, `AFTER_APPROVAL`, `SCHEDULED` | oui (défaut `MANUAL`) | `version.release_type` |
| `earliestReleaseDate` | date de sortie au plus tôt | ISO 8601 **avec fuseau**, dans le futur. Seulement avec `SCHEDULED` | si `SCHEDULED` | `version.earliest_release_date` |
| `downloadable` | la version reste téléchargeable | booléen | non | `version.downloadable` |
| `reviewType` | revue App Store ou notarisation (distribution alternative UE, macOS) | `APP_STORE`, `NOTARIZATION` | non | `version.review_type` |
| `usesIdfa` | **déprécié**. L'usage de l'identifiant publicitaire se déclare dans App Privacy | booléen | non | `version.uses_idfa` (avertissement) |
| sortie progressive | `appStoreVersionPhasedReleases` : 7 jours (1, 2, 5, 10, 20, 50, 100 %), pauses de 30 jours au plus [H16]. États `INACTIVE`, `ACTIVE`, `PAUSED`, `COMPLETE` | booléen côté andp | non | `version.phased_release` (crée un état `INACTIVE` ; ne retire qu'un état `INACTIVE`) |

## 5. Textes de la version par langue (`appStoreVersionLocalizations`)

| Champ | Sens | Limite | Requis | andp (andp.yml ou fichier deliver ou fichier andp) |
|---|---|---|---|---|
| `description` | description, texte brut | **4000 caractères** | **oui** | `description` · `description.txt` |
| `keywords` | mots-clés séparés par des virgules, sans le nom de l'app ni d'autres marques | **100**. L'aide dit « octets » [H2], mais l'API accepte 100 **caractères** (observé : 101 octets en de-DE, 129 octets en ar-SA, acceptés) | oui | `keywords` · `keywords.txt` |
| `whatsNew` | nouveautés de la version | **4000 caractères** | **oui pour toute mise à jour**, absent pour la 1re version [H2] | `whats_new` / `release_notes` · `release_notes.txt` · `whatsNew.txt` |
| `promotionalText` | texte en tête de fiche, **modifiable sans nouvelle soumission** | **170 caractères** | non | `promotional_text` · `promotional_text.txt` · `promotionalText.txt` |
| `supportUrl` | page menant à de vraies coordonnées | URL | **oui** | `support_url` · `support_url.txt` · `supportUrl.txt` |
| `marketingUrl` | site de l'app | URL | non | `marketing_url` · `marketing_url.txt` · `marketingUrl.txt` |

Captures, vidéos d'aperçu et assets créatifs : `andp publish` et `andp store apply`, par l'App Asset Library (§ 12).

## 6. Informations pour l'App Review (`appStoreReviewDetails`, par version)

Modifiables à tout moment, y compris sur une version approuvée [H2].

| Champ | Sens | Limite / règle | Requis | andp |
|---|---|---|---|---|
| `contactFirstName`, `contactLastName` | contact Apple pendant la revue | texte | **oui** | `review.contact_first_name`… · `review_information/first_name.txt`… |
| `contactPhone` | téléphone du contact | **format international avec « + »**, obligatoire depuis le 2026-08-19 [H2] | **oui** (andp bloque sans « + ») | `review.contact_phone[_env]` · `phone_number.txt` |
| `contactEmail` | e-mail du contact | adresse e-mail | **oui** | `review.contact_email[_env]` · `email_address.txt` |
| `demoAccountRequired` | l'app exige une connexion | booléen | oui si l'app exige une connexion | `review.demo_account_required` · `demo_required.txt` |
| `demoAccountName`, `demoAccountPassword` | compte démo **sans expiration**. Les comptes supplémentaires vont dans les notes [H2] | texte | si `demoAccountRequired` | `review.demo_account_name_env`, `review.demo_account_password_env` (jamais en clair dans le dépôt) |
| `notes` | instructions pour le réviseur. Toute nouvelle fonction doit y être décrite (guideline 2.3.1(a)) [G] | **4000 octets** | non | `review.notes[_file]` · `review_information/notes.txt` |
| pièces jointes | `appStoreReviewAttachments` : envoi en trois temps (réservation, envoi, validation MD5) | formats et taille non documentés | non | `review.attachments: [chemins]` (idempotent par nom de fichier) |

andp masque le téléphone, l'e-mail et le compte démo dans toute sortie.

## 7. Déclaration d'âge (`ageRatingDeclarations`, sur l'appInfo)

Questionnaire de 2025-2026 :

- **2025-07-24** : paliers 4+, 9+, **13+, 16+, 18+**, et nouvelles questions requises pour toutes les apps, avec réponse attendue avant le 31 janvier 2026 [N1] ;
- **2026-06-08** : les fonctions de réseau social imposent **13+ minimum**, avec réponse obligatoire pour toute version dès septembre 2026 [N2][N3].

| Champ | Sens [H6] | Valeurs | andp |
|---|---|---|---|
| 13 descripteurs de contenu : `alcoholTobaccoOrDrugUseOrReferences`, `contests`, `gamblingSimulated`, `gunsOrOtherWeapons`, `horrorOrFearThemes`, `matureOrSuggestiveThemes`, `medicalOrTreatmentInformation`, `profanityOrCrudeHumor`, `sexualContentGraphicAndNudity`, `sexualContentOrNudity`, `violenceCartoonOrFantasy`, `violenceRealistic`, `violenceRealisticProlongedGraphicOrSadistic` | fréquence du contenu | `NONE`, `INFREQUENT`, `FREQUENT`. `INFREQUENT_OR_MILD` et `FREQUENT_OR_INTENSE` sont **dépréciés depuis l'API 4.1** [R] et passent avec un avertissement | `age_rating.<champ>` |
| `messagingAndChat` | communication directe entre utilisateurs (texte, voix, vidéo) | booléen | idem |
| `userGeneratedContent` | diffusion large de contenu créé par les utilisateurs | booléen | idem |
| `socialMedia` | redistribution ou interaction avec du contenu utilisateur via un fil ou une découverte visibles par beaucoup → **13+** | booléen | idem |
| `socialMediaAgeRestricted` | fonctions sociales coupées aux moins de 13 ans, ce qui exige au minimum la Declared Age Range API [N2]. Posée seulement si `socialMedia` | booléen | idem |
| `advertising` | publicité payante (bannière, vidéo, native) | booléen | idem |
| `parentalControls` | outils de surveillance ou de restriction parentale | booléen | idem |
| `ageAssurance` | vérification d'âge (Declared Age Range, estimation, pièce d'identité) | booléen | idem |
| `healthOrWellnessTopics` | conseils d'hygiène de vie → 9+ | booléen | idem |
| `lootBox` | conteneurs **payants** au contenu aléatoire → 9+ (18+ au Brésil) | booléen | idem |
| `gambling`, `unrestrictedWebAccess` | jeux d'argent réels ; accès web sans restriction (navigateur intégré) | booléen | idem |
| `kidsAgeBand` | tranche « Made for Kids », irréversible une fois approuvée [H7] | `FIVE_AND_UNDER`, `SIX_TO_EIGHT`, `NINE_TO_ELEVEN` | idem |
| `ageRatingOverrideV2` | relève la note calculée (jamais la baisser). Obligatoire si le CLUF impose un âge supérieur [H7] | `NONE`, `NINE_PLUS`, `THIRTEEN_PLUS`, `SIXTEEN_PLUS`, `EIGHTEEN_PLUS`, `UNRATED` (distribution alternative UE) | idem |
| `ageRatingOverride` | **déprécié** au profit de V2 | `…SEVENTEEN_PLUS…` | accepté, avec un avertissement |
| `koreaAgeRatingOverride`, `gracRatingClassificationNumber` | note coréenne alignée sur le numéro GRAC (RCN), verrouillé après approbation [N6]. andp refuse une surcharge sans son numéro | `NONE`, `ALL`, `TWELVE_PLUS`, `FIFTEEN_PLUS`, `NINETEEN_PLUS` ; texte | idem |
| `developerAgeRatingInfoUrl` | « Age Suitability URL » : comment vous déterminez l'âge [N5] | URL | idem |
| `seventeenPlus`, `gamblingAndContests` | **retirés** dans l'API 4.0 [R] | — | ignorés avec un avertissement, jamais envoyés |
| notes par territoire (`territoryAgeRatings`) | note calculée par Apple pour chaque pays. L'Australie passe à **16+** (le palier 15+ disparaît le 2026-06-18) ; le Vietnam a **00+ / 12+ / 16+ / 18+** (valeur `ZERO_ZERO`) ; la Corée suit l'override ci-dessus. Rien de modifiable par l'API | **lecture seule** | résumée par `store plan` |

`readiness appstore` bloque tant qu'une question requise est sans réponse et les nomme toutes : les 13 descripteurs, les 10 booléens, et `socialMediaAgeRestricted` quand `socialMedia` est vrai.

## 8. Accessibility Nutrition Labels (`accessibilityDeclarations`, par type d'appareil)

Déclaration **volontaire** pour l'instant. Apple annonce qu'elle deviendra obligatoire, sans date [H8].

Règle commune : une fonction ne se déclare que si **toutes les tâches courantes** (fonction principale, premier lancement, connexion, achat, réglages) sont réalisables avec elle. Une déclaration trompeuse relève de la guideline 2.3 [H8]. Les critères détaillés sont dans [C].

| Champ | Critère résumé | andp |
|---|---|---|
| `supportsVoiceover` | tout est faisable avec VoiceOver seul : libellés, traits, ordre, actions | `accessibility.<FAMILLE>.voiceover` |
| `supportsVoiceControl` | tout activable à la voix ; libellés identiques au texte visible | `voice_control` |
| `supportsLargerText` | 200 % ou la taille maximale, sans troncature ni chevauchement. Ouvert à tvOS (`APPLE_TV`) depuis les notes de version d'App Store Connect de 2026 | `larger_text` |
| `supportsDarkInterface` | sombre par défaut ou suivi du mode sombre | `dark_interface` |
| `supportsDifferentiateWithoutColorAlone` | aucune information portée par la seule couleur | `differentiate_without_color_alone` |
| `supportsSufficientContrast` | environ 4,5:1 par défaut, ou « Augmenter le contraste » effectif | `sufficient_contrast` |
| `supportsReducedMotion` | animations perpétuelles, parallaxe et carrousels coupés quand le réglage est actif | `reduced_motion` |
| `supportsCaptions` | sous-titres et transcriptions, possibilité d'en joindre au contenu des utilisateurs | `captions` |
| `supportsAudioDescriptions` | narration descriptive | `audio_descriptions` |

- **Familles d'appareils** : `IPHONE`, `IPAD`, `APPLE_TV`, `APPLE_WATCH`, `MAC`, `VISION`.
- **États** : `DRAFT` → `PUBLISHED` → `REPLACED`. La publication n'est possible que pour un appareil qui a une version en ligne [H9].
- **Comportement d'andp** : il crée un brouillon, ou met à jour le brouillon existant, puis le publie. Les réponses déjà publiées et non redéclarées sont conservées.

## 9. Chiffrement à l'export

| Élément | Sens | andp |
|---|---|---|
| `ITSAppUsesNonExemptEncryption` (Info.plist), `builds.usesNonExemptEncryption` | `NO` si l'app, bibliothèques comprises, n'utilise aucun chiffrement ou seulement un chiffrement exempté [D1][D2] | `compliance.uses_non_exempt_encryption` (machine de release), lecture de l'IPA |
| `appEncryptionDeclarations` (POST, lecture par `filter[app]`) | `appDescription`, `containsProprietaryCryptography`, `containsThirdPartyCryptography` (algorithmes standard **en plus** de ceux de l'OS), `availableOnFrenchStore`, tous requis. Ensuite `exempt`, `codeValue` et l'état sont posés par Apple | `encryption:` (les quatre champs) |
| document joint (`appEncryptionDeclarationDocuments`) | CCATS américain ou déclaration française [H13] | `encryption.document` |

Pièces exigées selon le chiffrement [H13] :

| Chiffrement utilisé | Pièce |
|---|---|
| seulement celui de l'OS Apple | aucune |
| algorithmes standard hors OS | déclaration française si l'app est en France |
| algorithmes propriétaires | CCATS + déclaration française |

Observé le 2026-10-09 : `GET /v1/apps/{id}/appEncryptionDeclarations` répond 404 (« relationship does not exist »). andp lit donc par `GET /v1/appEncryptionDeclarations?filter[app]=…`.

## 10. CLUF (`endUserLicenseAgreements`)

Sans CLUF personnalisé, le CLUF standard d'Apple s'applique [H19]. Le CLUF personnalisé est du texte brut ; ses traductions vont dans le même champ, avec une liste de territoires.

andp : `eula: standard` supprime un CLUF personnalisé. `eula: {file: chemin, territories: all | [FRA, …]}` le crée ou le met à jour.

## 11. Prix, disponibilité, pré-commandes

| Élément | API | andp |
|---|---|---|
| prix | `appPriceSchedules` (prix manuel du territoire de base, les autres en dérivent). Les prix se lisent sur `/v1/appPriceSchedules/{id}/manualPrices` : `/v1/apps/{id}/appPriceSchedule/manualPrices` répond 404 (observé) | `pricing:` |
| territoires | `appAvailabilities` v2 (remplacement atomique). `contentStatuses` explique un refus (`CANNOT_SELL`, `TRADER_STATUS_*`…) | `availability:` |
| pré-commande | `territoryAvailabilities` (`preOrderEnabled`, `releaseDate`, `preOrderPublishDate`), `endAppAvailabilityPreOrders`. Date entre 2 et 180 jours pour une première sortie, 365 pour un nouveau territoire. Impossible là où l'app est déjà sortie [H18] | — : sans objet pour une app déjà publiée. À piloter dans App Store Connect |

## 12. Visuels de la fiche — App Asset Library

Depuis le **2026-10-05**, les visuels passent par l'**App Asset Library** (API 4.5.1). Les captures et vidéos classiques (`appScreenshotSets`, `appPreviewSets`) sont **dépréciées** mais fonctionnent encore. andp s'en sert en repli quand l'Asset Library ne répond pas.

### Le modèle

| Ressource | Sens | API |
|---|---|---|
| bibliothèque | les images et vidéos de l'app, envoyées une seule fois | `GET /v1/apps/{id}/assetLibrary`. Le contenu se lit sur `/v1/appAssetLibraries/{id}/images` et `…/videos` : ces chemins sont absents de la spécification, mais donnés par les liens de la réponse (observé le 2026-10-09) |
| image / vidéo | un fichier, avec sa catégorie (`APP_SCREENSHOTS_AND_PREVIEWS` ou `CREATIVE_ASSETS`) et son état (`AWAITING_UPLOAD` → `UPLOAD_COMPLETE` → `COMPLETE` → … → `APPROVED`, `REJECTED`, `ARCHIVED`) | `POST /v1/appAssetLibraryImages` ou `Videos`, envoi des octets, puis `PATCH uploaded: true` (sans somme de contrôle) |
| placement | pose un fichier sur une page, pour un **type d'emplacement** et un **groupe** | `POST/GET/DELETE /v1/appAssetLibraryPlacements`, lu par langue sur `/v1/appStoreVersionLocalizations/{id}/placements?sort=placementGroupPosition`. États : `ASSET_PROCESSING`, `FAILED`, `PARENT_*`, et `ACTIVE`, observé sur une version en ligne mais absent de l'énumération |
| ordre | l'ordre d'affichage d'un groupe | `POST /v1/appAssetLibraryPlacementOrderingRequests` (`placementGroup` + placements ordonnés) |
| données de référence | spécifications (`specId`), groupes, classes d'affichage, limites | `GET /v1/appAssetLibraryRefData`. andp les lit en direct quand il a des identifiants, sinon il utilise l'instantané du 2026-10-09 (`andp/asc/asset_refdata.py`) |

Un placement se pose sur une langue de **version**, de **page produit personnalisée**, de **traitement d'expérience** ou d'**événement in-app**. andp pilote la langue de version.

### Les types d'emplacement

| Type | Sens | Catégorie | Limite par groupe (version) | andp (dossier) |
|---|---|---|---|---|
| `APP_SCREENSHOT` | captures de la fiche | captures et vidéos | **10** | `<langue>/screenshots/<GROUPE>/` |
| `APP_PREVIEW` | vidéos d'aperçu, 15 à 30 s | captures et vidéos | **3** | `<langue>/previews/<GROUPE>/` |
| `IMESSAGE_APP_SCREENSHOT` | captures de l'app iMessage | captures et vidéos | 10 | `<langue>/imessage_screenshots/<GROUPE>/` |
| `PRODUCT_PAGE_HEADER_ASSET` | **en-tête de la fiche** : image PNG 5244×2950 (16:9) ou 3840×1646 (21:9), ou vidéo 3840×1646 de 5 à 30 s | assets créatifs | **1** | `<langue>/product_page_header/` |
| `APP_STORE_SEARCH_RESULTS_ASSET` | **visuel des résultats de recherche** : PNG 5244×2950, image 3:2 de 1920 à 3840 px de large, ou vidéo 3:2 de 5 à 30 s | assets créatifs | **1** | `<langue>/search_results/` |
| `SEARCH_RESULTS_ADS_ASSET`, `TODAY_TAB_ADS_ASSET` | publicités Apple Ads | assets créatifs | — | — (relèvent d'Apple Ads) |
| `EVENT_CARD_ASSET`, `EVENT_DETAILS_PAGE_ASSET` | carte et page d'un événement in-app | assets créatifs | 1 | — (événements in-app non pilotés) |
| `RETENTION_MESSAGE_ASSET` | messages de rétention (abonnements) | assets créatifs | — | — |

### Les groupes, leurs classes d'affichage et les dimensions acceptées

Le nom du dossier `<GROUPE>` peut s'écrire de trois façons :

- le groupe lui-même (`IPHONE_DUO_PROFILE`) ;
- sa classe d'affichage (`IPHONE_DUO`, `IPAD_11_DISPLAY`) ;
- l'ancien type de capture (`APP_IPHONE_67` → `IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE`, `APP_IPAD_PRO_3GEN_129` → `IPAD_13_PROFILE`…). Ces correspondances sont observées sur me.meeshy.app : ses anciens jeux y apparaissent comme placements de ces groupes.

Une dimension de « Captures » se lit largeur × hauteur. Chaque groupe accepte le portrait et le paysage, PNG ou JPEG sans transparence, 500 Mo au plus. Une vidéo `APP_PREVIEW` fait de 15 à 30 s, entre 23 et 30 images par seconde. Relevé de `appAssetLibraryRefData` le 2026-10-09 :

| Groupe (dossier) | Classe d'affichage | Écrans | Captures `APP_SCREENSHOT` | Vidéos `APP_PREVIEW` |
|---|---|---|---|---|
| `IPAD_105_PROFILE` | `IPAD_105_DISPLAY` | 2224x1668 | 1668×2224, 2224×1668 | 1200×1600, 1600×1200 |
| `IPAD_11_PROFILE` | `IPAD_11_DISPLAY` | 2266x1488, 2360x1640, 2388x1668, 2420x1668 | 1488×2266, 1640×2360, 1668×2388, 1668×2420, 2266×1488, 2360×1640, 2388×1668, 2420×1668 | 1200×1600, 1600×1200 |
| `IPAD_129_PROFILE` | `IPAD_129_DISPLAY` | 2732x2048 | 2048×2732, 2732×2048 | 1200×1600, 1200×900, 1600×1200, 900×1200 |
| `IPAD_13_PROFILE` | `IPAD_13_DISPLAY` | 2732x2048, 2752x2064 | 2048×2732, 2064×2752, 2732×2048, 2752×2064 | 1200×1600, 1600×1200 |
| `IPAD_97_PROFILE` | `IPAD_97_DISPLAY` | 1024x768, 2048x1536 | 1024×748, 1024×768, 1536×2008, 1536×2048, 2048×1496, 2048×1536, 768×1004, 768×1024 | 1200×900, 900×1200 |
| `IPHONE_DUO_PROFILE` | `IPHONE_DUO` | 2853x2007, 2034x1398 | 1398×2034, 2007×2853, 2034×1398, 2853×2007 | 1920×886, 886×1920 |
| `IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE` | `IPHONE_DYNAMIC_ISLAND_LARGE_DISPLAY` | 2736x1260, 2796x1290, 2868x1320 | 1260×2736, 1290×2796, 1320×2868, 2736×1260, 2796×1290, 2868×1320 | 1920×886, 886×1920 |
| `IPHONE_DYNAMIC_ISLAND_MEDIUM_PROFILE` | `IPHONE_DYNAMIC_ISLAND_MEDIUM_DISPLAY` | 2556x1179, 2622x1206 | 1179×2556, 1206×2622, 2556×1179, 2622×1206 | 1920×886, 886×1920 |
| `IPHONE_FACE_ID_LARGE_PROFILE` | `IPHONE_FACE_ID_LARGE_DISPLAY` | 2688x1242, 2778x1284 | 1242×2688, 1284×2778, 2688×1242, 2778×1284 | 1920×886, 886×1920 |
| `IPHONE_FACE_ID_MEDIUM_PROFILE` | `IPHONE_FACE_ID_MEDIUM_DISPLAY` | 2340x1080, 2436x1125, 2532x1170 | 1080×2340, 1125×2436, 1170×2532, 2340×1080, 2436×1125, 2532×1170 | 1920×886, 886×1920 |
| `IPHONE_HOME_BUTTON_35_PROFILE` | `IPHONE_HOME_BUTTON_35_DISPLAY` | 960x640, 960x600, 920x640 | 320×460, 320×480, 480×300, 480×320, 640×920, 640×960, 960×600, 960×640 | — |
| `IPHONE_HOME_BUTTON_40_PROFILE` | `IPHONE_HOME_BUTTON_40_DISPLAY` | 1136x640, 1136x600, 1096x640 | 1136×600, 1136×640, 640×1096, 640×1136 | 1080×1920, 1920×1080 |
| `IPHONE_HOME_BUTTON_LARGE_PROFILE` | `IPHONE_HOME_BUTTON_LARGE_DISPLAY` | 2208x1242 | 1242×2208, 2208×1242 | 1080×1920, 1920×1080 |
| `IPHONE_HOME_BUTTON_MEDIUM_PROFILE` | `IPHONE_HOME_BUTTON_MEDIUM_DISPLAY` | 1334x750 | 1334×750, 750×1334 | 1334×750, 750×1334 |
| `MAC_PROFILE` | `DEFAULT` | — | 1280×800, 1440×900, 2560×1600, 2880×1800 | 1920×1080 |
| `TV_PROFILE` | `DEFAULT` | — | 1920×1080, 3840×2160 | 1920×1080 |
| `VISION_PRO_PROFILE` | `DEFAULT` | — | 3840×2160 | 3840×2160 |
| `WATCH_SERIES_10_PROFILE` | `WATCH_SERIES_10` | 42, 46 | 416×496 | — |
| `WATCH_SERIES_3_PROFILE` | `WATCH_SERIES_3` | 38, 42 | 312×390 | — |
| `WATCH_SERIES_4_PROFILE` | `WATCH_SERIES_4` | 40, 44 | 368×448 | — |
| `WATCH_SERIES_7_PROFILE` | `WATCH_SERIES_7` | 41, 45 | 396×484 | — |
| `WATCH_ULTRA_PROFILE` | `WATCH_ULTRA` | 49 | 410×502, 422×514 | — |

Les groupes `IMESSAGE_*` reprennent les mêmes classes pour l'app iMessage. `DEFAULT_PROFILE` porte les assets créatifs.

### iPhone Duo

L'iPhone Duo est l'iPhone à deux écrans géré par iOS 27. Sa classe `IPHONE_DUO` n'a **pas** d'équivalent dans l'ancien `screenshotDisplayType` : ses captures ne passent **que** par l'Asset Library. Ses spécifications ont été publiées le 2026-09-09, et l'App Store accepte les apps optimisées iPhone Duo depuis le 2026-10-05.

| | Portrait | Paysage |
|---|---|---|
| écran extérieur | 1398×2034 | 2034×1398 |
| écran intérieur | 2007×2853 | 2853×2007 |
| vidéo d'aperçu | 886×1920 | 1920×886 |

- **Exigence** : les captures iPhone Duo sont **obligatoires pour toute soumission à partir d'avril 2027** (App Store Connect, 2026-10-05). Apple les annonce aussi obligatoires pour toute app compilée avec le SDK iOS 27.1 ou plus.
- **Ce que fait `readiness appstore`** : il avertit aujourd'hui et **bloque à partir du 2027-04-01** pour une version iOS dont une langue n'a pas de capture `IPHONE_DUO_PROFILE`.

Les mêmes notes de version ajoutent des spécifications pour l'iPhone 18 Pro et Pro Max (classe `IPHONE_DYNAMIC_ISLAND_LARGE_DISPLAY`, qui gagne 2736×1260), l'Apple Watch Ultra 4 (422×514) et la Series 12.

### Ce qu'andp vérifie et fait

- **Avant tout envoi**, pour chaque fichier : l'extension, les **dimensions exactes lues dans le fichier** (PNG, JPEG, et les boîtes `tkhd`/`mvhd` des MP4 et MOV), la taille, la durée d'une vidéo et le nombre maximal par groupe. La moindre erreur arrête tout, avant la première requête.
- **Envoi** : un fichier est envoyé une seule fois dans la bibliothèque. Un fichier de même nom et de même taille déjà présent est réutilisé. Il est ensuite placé dans chaque langue, puis le groupe est ordonné selon l'ordre des noms de fichiers ; les placements absents du dossier passent après.
- **Placements absents du dossier** : ils sont gardés et signalés, ou retirés avec `store.media.prune: true`.
- **Plan** : `store plan` liste chaque envoi, placement, remise en ordre ou retrait (famille `media`) sans rien écrire.
- **Sans Asset Library** : les groupes qui ont un ancien type passent par `appScreenshotSets` / `appPreviewSets`. iPhone Duo et les assets créatifs sont refusés, avec la raison.

## 13. Événements in-app (`appEvents`, `appEventLocalizations`)

Un événement in-app est une carte de l'App Store (fiche, recherche, Aujourd'hui, Apple Games) qui annonce un moment limité dans le temps : saison, compétition, première. andp le déclare dans `store.app_events` (voir [StoreConfig.md](StoreConfig.md)), le réconcilie par `store plan` / `store apply` (famille `app_event`) et le soumet par `store submit-events`.

| Champ | API | Limite / valeurs | andp |
|---|---|---|---|
| nom de référence | `referenceName` | 64 caractères, unique par app [H20] | `reference_name` — clé de rapprochement |
| badge | `badge` | `LIVE_EVENT`, `PREMIERE`, `CHALLENGE`, `COMPETITION`, `NEW_SEASON`, `MAJOR_UPDATE`, `SPECIAL_EVENT` | `badge` (requis) |
| objectif | `purpose` | `APPROPRIATE_FOR_ALL_USERS`, `ATTRACT_NEW_USERS`, `KEEP_ACTIVE_USERS_INFORMED`, `BRING_BACK_LAPSED_USERS` | `purpose` (requis) |
| priorité | `priority` | `HIGH`, `NORMAL` | `priority` |
| achat requis | `purchaseRequirement` | `NO_COST_ASSOCIATED`, `IN_APP_PURCHASE` | `purchase_requirement` |
| lien profond | `deepLink` | URI ; Apple recommande un lien universel | `deep_link` (https ou schéma de l'app) |
| langue principale | `primaryLocale` | code de langue | `primary_locale` |
| calendrier | `territorySchedules[]` | `territories`, `publishStart`, `eventStart`, `eventEnd` | `territories` + trois dates, ou `schedules:` |
| nom | `appEventLocalizations.name` | 30 caractères [H20] | par langue |
| description courte | `shortDescription` | 50 caractères, affichée sur la carte [H20] | par langue |
| description longue | `longDescription` | 120 caractères, affichée sur la page de détail [H20] | par langue |
| état | `eventState` (lecture seule) | `DRAFT` → `READY_FOR_REVIEW` → `WAITING_FOR_REVIEW` → `IN_REVIEW` → `ACCEPTED`/`APPROVED` → `PUBLISHED` → `PAST` → `ARCHIVED` ; `REJECTED` | modifiable en `DRAFT`, `READY_FOR_REVIEW`, `REJECTED` ; figé ensuite (🔒) |

**Règles d'Apple** [H20], contrôlées hors ligne : un événement dure de 15 minutes à 31 jours ; sa publication précède son début de 14 jours au plus ; les débuts par territoire tiennent dans 48 heures ; 10 événements publiés et 15 approuvés au plus en même temps, 10 qui se chevauchent au plus.

**Visuels** — placements de l'App Asset Library sur la langue de l'événement (`POST /v1/appAssetLibraryPlacements` avec la relation `appEventLocalization`, lus par `GET /v1/appEventLocalizations/{id}/placements`, OpenAPI 4.5.1 du 2026-10-06). Un seul visuel par type (limite `IN_APP_EVENTS` des données de référence) ; un fichier différent remplace le précédent :

| Type | Dossier | Image | Vidéo |
|---|---|---|---|
| `EVENT_CARD_ASSET` | `app_events/<clé>/<langue>/event_card/` | 16:9, 1920×1080 à 3840×2160, PNG/JPEG sans transparence | 16:9, 15 à 30 s, 30 ou 60 i/s |
| `EVENT_DETAILS_PAGE_ASSET` | `app_events/<clé>/<langue>/event_details_page/` | 9:16, 1080×1920 à 2160×3840 | 9:16, 15 à 30 s, 30 ou 60 i/s |

Les anciennes ressources `appEventScreenshots` / `appEventVideoClips` existent encore dans l'API ; andp ne s'en sert pas.

**Soumission** [H21] — une app déjà approuvée peut soumettre un événement seul : il est examiné avec la dernière version de la plateforme choisie. Une app jamais approuvée soumet son premier événement avec sa première version. `store submit-events` crée une soumission (ou reprend un brouillon qui ne contient que des événements), y ajoute chaque événement (`reviewSubmissionItems.appEvent`) et la soumet ; il refuse un brouillon qui contient une version.

## 14. Ce que l'API n'expose pas — à faire à la main dans App Store Connect

Ces ressources sont absentes de la spécification 4.5.1 (vérifié par recherche dans le fichier).

| Sujet | Où | Bloquant |
|---|---|---|
| **App Privacy** (« étiquettes de confidentialité » : données collectées, finalités, liaison, suivi) | barre latérale App Privacy → Publish [H4] | **oui** : les réponses sont requises |
| **Statut de trader UE (DSA)** | Business → Agreements → Compliance, puis réglage par app [H10] | **oui** : une app sans statut a été retirée de l'App Store UE le 17 février 2025. Le statut se déclare même hors UE. Seule une lecture indirecte existe, par `contentStatuses` `TRADER_STATUS_*` |
| **Dispositif médical réglementé** | App Information → App Store Regulations & Permits [H11] | oui pour les catégories Santé et forme ou Médecine, ou si le contenu médical est déclaré fréquent. Requis pour les nouvelles apps depuis le 2026-03-26, pour les existantes « début 2027 » |
| catégorie fiscale | Pricing and Availability [H12] | non (défaut « App Store software ») |
| contrats, banque, fiscalité | Business | contrat Apps payantes seulement si l'app est payante |
| App Clip, Game Center, Custom Product Pages | ressources dédiées de l'API (`appClips`, `gameCenter*`, `appCustomProductPages`) | non. Elles existent dans l'API mais andp ne les pilote pas (les événements in-app, eux, sont pilotés : § 13) |

## Sources

Aide App Store Connect (préfixe `https://developer.apple.com/help/app-store-connect/`) :

- [H1] `reference/app-information/app-information`
- [H2] `reference/app-information/platform-version-information`
- [H3] `reference/app-information/required-localizable-and-editable-properties`
- [H4] `manage-app-information/manage-app-privacy`
- [H5] `reference/app-information/app-privacy`
- [H6] `reference/app-information/age-ratings-values-and-definitions`
- [H7] `manage-app-information/set-an-app-age-rating`
- [H8] `manage-app-accessibility/overview-of-accessibility-nutrition-labels`
- [H9] `manage-app-accessibility/manage-accessibility-nutrition-labels`
- [H10] `manage-compliance-information/manage-european-union-digital-services-act-trader-requirements`
- [H11] `manage-app-information/declare-regulated-medical-device-status`
- [H12] `manage-app-information/set-a-tax-category`
- [H13] `reference/app-information/export-compliance-documentation-for-encryption`
- [H16] `update-your-app/release-a-version-update-in-phases`
- [H17] `manage-your-apps-availability/select-an-app-store-version-release-option`
- [H18] `manage-your-apps-availability/publish-for-pre-order`
- [H19] `manage-app-information/provide-a-custom-license-agreement`
- [H20] `offer-in-app-events/offer-in-app-events` (lu le 2026-10-10)
- [H21] `manage-submissions-to-app-review/submit-an-in-app-event` (lu le 2026-10-10)
- [C] `manage-app-accessibility/<fonction>-evaluation-criteria`

Documentation de l'API (préfixe `https://developer.apple.com/documentation/appstoreconnectapi/`) :

- attributs de `ageratingdeclaration`, `app`, `accessibilitydeclaration`, `appencryptiondeclaration`, `appstorereviewdetail`, `territoryavailability`
- [R] notes de version `app-store-connect-api-{3-8 … 4-5-1}-release-notes`

Autres documents Apple :

- [D1] https://developer.apple.com/documentation/security/complying-with-encryption-export-regulations
- [D2] https://developer.apple.com/documentation/bundleresources/information-property-list/itsappusesnonexemptencryption
- [G] App Review Guidelines, https://developer.apple.com/app-store/review/guidelines/

Actualités Apple (`https://developer.apple.com/news/?id=…`) :

- [N1] `ks775ehf`
- [N2] `0d2gpmml`
- [N3] `tlur8uvi`
- [N5] `y1bckxf8`
- [N6] `oj3r9pvw`
