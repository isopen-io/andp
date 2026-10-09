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

Captures d'écran et vidéos d'aperçu : `andp publish` (voir [Metadata.md](Metadata.md)). L'API 4.5.1 introduit l'App Asset Library et **déprécie** `appScreenshotSets` et `appPreviewSets`, qui restent fonctionnels.

## 6. Informations pour l'App Review (`appStoreReviewDetails`, par version)

Modifiables à tout moment, y compris sur une version approuvée [H2].

| Champ | Sens | Limite / règle | Requis | andp |
|---|---|---|---|---|
| `contactFirstName`, `contactLastName` | contact Apple pendant la revue | texte | **oui** | `review.contact_first_name`… · `review_information/first_name.txt`… |
| `contactPhone` | téléphone du contact | **format international avec « + »** [H2] | **oui** | `review.contact_phone[_env]` · `phone_number.txt` |
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
| `koreaAgeRatingOverride`, `gracRatingClassificationNumber` | note coréenne alignée sur le numéro GRAC (RCN), verrouillé après approbation [N6] | `NONE`, `ALL`, `TWELVE_PLUS`, `FIFTEEN_PLUS`, `NINETEEN_PLUS` ; texte | idem |
| `developerAgeRatingInfoUrl` | « Age Suitability URL » : comment vous déterminez l'âge [N5] | URL | idem |
| `seventeenPlus`, `gamblingAndContests` | **retirés** dans l'API 4.0 [R] | — | ignorés avec un avertissement, jamais envoyés |
| notes par territoire (`territoryAgeRatings`) | note calculée par Apple pour chaque pays (Corée, Vietnam, Australie, Brésil…) | **lecture seule** | résumée par `store plan` |

`readiness appstore` bloque tant qu'une question requise est sans réponse et les nomme toutes : les 13 descripteurs, les 10 booléens, et `socialMediaAgeRestricted` quand `socialMedia` est vrai.

## 8. Accessibility Nutrition Labels (`accessibilityDeclarations`, par type d'appareil)

Déclaration **volontaire** pour l'instant. Apple annonce qu'elle deviendra obligatoire, sans date [H8].

Règle commune : une fonction ne se déclare que si **toutes les tâches courantes** (fonction principale, premier lancement, connexion, achat, réglages) sont réalisables avec elle. Une déclaration trompeuse relève de la guideline 2.3 [H8]. Les critères détaillés sont dans [C].

| Champ | Critère résumé | andp |
|---|---|---|
| `supportsVoiceover` | tout est faisable avec VoiceOver seul : libellés, traits, ordre, actions | `accessibility.<FAMILLE>.voiceover` |
| `supportsVoiceControl` | tout activable à la voix ; libellés identiques au texte visible | `voice_control` |
| `supportsLargerText` | 200 % ou la taille maximale, sans troncature ni chevauchement | `larger_text` |
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

## 12. Ce que l'API n'expose pas — à faire à la main dans App Store Connect

Ces ressources sont absentes de la spécification 4.5.1 (vérifié par recherche dans le fichier).

| Sujet | Où | Bloquant |
|---|---|---|
| **App Privacy** (« étiquettes de confidentialité » : données collectées, finalités, liaison, suivi) | barre latérale App Privacy → Publish [H4] | **oui** : les réponses sont requises |
| **Statut de trader UE (DSA)** | Business → Agreements → Compliance, puis réglage par app [H10] | **oui** : une app sans statut a été retirée de l'App Store UE le 17 février 2025. Le statut se déclare même hors UE. Seule une lecture indirecte existe, par `contentStatuses` `TRADER_STATUS_*` |
| **Dispositif médical réglementé** | App Information → App Store Regulations & Permits [H11] | oui pour les catégories Santé et forme ou Médecine, ou si le contenu médical est déclaré fréquent. Requis pour les nouvelles apps depuis le 2026-03-26, pour les existantes « début 2027 » |
| catégorie fiscale | Pricing and Availability [H12] | non (défaut « App Store software ») |
| contrats, banque, fiscalité | Business | contrat Apps payantes seulement si l'app est payante |
| App Clip, In-App Events, Game Center, Custom Product Pages | ressources dédiées de l'API (`appClips`, `appEvents`, `gameCenter*`, `appCustomProductPages`) | non. Elles existent dans l'API mais andp ne les pilote pas |

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
