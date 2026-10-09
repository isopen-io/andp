# Store configuration — the whole App Store listing

ANDP declares the App Store listing in `andp.yml` (`store:`) and a metadata
folder, shows the exact diff with `andp store plan` (read-only), and writes it
with `andp store apply` — idempotently, with dry-run and an audit trail. It
covers every field the App Store Connect API (4.5.1) exposes for defining an
app and its submission: app attributes, categories, names / subtitles / privacy
URLs per language, version attributes and texts, App Review details and
attachments, phased release, age rating, Accessibility Nutrition Labels,
export-compliance declaration, custom EULA, price and territories.

What each field means, its limits, whether App Review requires it, and what
the API does **not** expose (App Privacy, EU trader status, regulated medical
device…): [AppStoreFields.md](AppStoreFields.md).

## The listing

```yaml
store:
  platform: IOS                       # IOS | MAC_OS | TV_OS | VISION_OS
  metadata_dir: fastlane/metadata     # deliver or andp layout (see Metadata.md)
  env_file: fastlane/.env             # gitignored KEY=VALUE, for *_env keys

  app:
    primary_locale: en-US
    content_rights: DOES_NOT_USE_THIRD_PARTY_CONTENT   # | USES_THIRD_PARTY_CONTENT
    accessibility_url: https://example.com/accessibility
    # subscription_status_url / _version (V1|V2) / _sandbox / _version_sandbox,
    # streamlined_purchasing

  categories:                         # or primary_category.txt, secondary_category.txt
    primary: SOCIAL_NETWORKING
    secondary: EDUCATION
    # primary_subcategory_one … (GAMES_* / STICKERS_* only)

  localizations:                      # overrides the metadata files, field by field
    en-US:
      name: My App                    # ≤ 30
      subtitle: Short pitch           # ≤ 30
      privacy_policy_url: https://example.com/privacy
      privacy_choices_url: https://example.com/privacy/choices
      promotional_text: …             # ≤ 170 (also: description, keywords,
                                      # whats_new, support_url, marketing_url)

  version:
    copyright: "2026 Example Inc."    # or copyright.txt
    release_type: SCHEDULED           # MANUAL | AFTER_APPROVAL | SCHEDULED
    earliest_release_date: 2026-11-02T08:00:00Z   # SCHEDULED only, with a time zone
    downloadable: true
    phased_release: true              # 7-day phased release (created INACTIVE)

  review:                             # or review_information/*.txt
    contact_first_name: Ada
    contact_last_name: Lovelace
    contact_phone_env: REVIEW_PHONE   # "+33 …" — international format
    contact_email_env: REVIEW_EMAIL
    demo_account_required: true
    demo_account_name_env: DEMO_USER
    demo_account_password_env: DEMO_PASSWORD
    notes_file: fastlane/review_notes.txt   # ≤ 4000 bytes
    attachments: [fastlane/review/demo.mov]

  accessibility:                      # Accessibility Nutrition Labels, per device
    IPHONE: {voiceover: true, dark_interface: true, larger_text: true}
    IPAD:   {voiceover: true, dark_interface: true}

  encryption:                         # only when a declaration is needed
    app_description: End-to-end encrypted messaging with standard algorithms
    contains_proprietary_cryptography: false
    contains_third_party_cryptography: true
    available_on_french_store: true
    document: compliance/french-declaration.pdf

  eula: standard                      # or {file: legal/eula.txt, territories: all}

  media:
    prune: false                      # true: remove placements absent from the folder
```

Screenshots, previews and creative assets (product page header, search
results) come from the metadata folder and go through the App Asset Library —
iPhone Duo included ([Metadata.md](Metadata.md), [AppStoreFields.md § 12](AppStoreFields.md)).

- **Keys**: snake_case, the deliver file names, or the API camelCase names, all
  accepted; two keys disagreeing on one field is an error; an unknown key is an
  error (typo guard).
- **Secrets never live in the repository**: any key takes an `_env` suffix (an
  environment variable, or a line of `env_file`) and text keys a `_file`
  suffix. Review contact and demo account are masked in every output.
- **Validated before any write**: Apple's limits (name / subtitle 30, keywords
  100, promotional text 170, description and What's New 4000, review notes 4000
  bytes), enums, URLs, ISO dates with a time zone, cross-field rules
  (`SCHEDULED` needs a future date, `demo_account_required` needs both
  credentials, an international phone), category ↔ subcategory parent.
- **Locks**: once a version or the app info is live, its fields are 🔒 in the
  plan and `apply` refuses them (promotional text stays editable).

### `andp store plan`

```bash
andp store plan me.app.bundle [--version 1.2.0] [--metadata fastlane/metadata] [--json]
```

GET only. One line per field that would change — `family [scope] field:
current → desired` with `+` create, `~` update, `-` delete, `↑` upload — then
the read-only facts (Apple's computed rating per territory, Made for Kids) and
"nothing was written". Without credentials it validates everything offline.
Exit 1 on a validation error.

### `andp store apply`

```bash
andp store apply me.app.bundle [--version 1.2.0] [--metadata fastlane/metadata]
```

Runs pricing, availability, age rating, then the listing block — the same diff
as the plan, family by family; a failing family is reported and the others
still run; a re-plan afterwards is empty. A listing with validation errors is
refused whole. Without `--version`, the editable version of `platform` is used.

### Readiness

`andp readiness appstore <bundle> <version>` blocks on what App Review
requires: content rights, primary category, app name and privacy policy URL in
every language of the version, copyright, scheduled release without date, App
Review contact (phone in international format), demo account, every unanswered
age rating question (named), Apple's length limits, and screenshots per
language (legacy sets or Asset Library). Missing iPhone Duo screenshots warn
today and block from 2027-04-01.

## Pricing, territories, age rating

These use the **current** App Store Connect API models: pricing is
`appPriceSchedules`/`appPricePoints` (the tier system is gone), availability is
`appAvailabilities` v2, age rating is the 2025-overhauled `ageRatingDeclaration`.

### `andp.yml`

```yaml
store:
  pricing:
    base_territory: USA
    price: "0.99"          # "0" / "0.00" / "free" => Free; else an exact
                           # base-territory customerPrice that must match a price point
    # price_point_id: <id> # advanced escape hatch (wins over price)

  availability:
    territories: [USA, FRA, DEU]   # or: all
    available_in_new_territories: false   # omit to preserve the current value

  age_rating:
    # content descriptors: NONE | INFREQUENT | FREQUENT
    # (INFREQUENT_OR_MILD / FREQUENT_OR_INTENSE: deprecated since API 4.1, warned)
    violenceCartoonOrFantasy: NONE
    matureOrSuggestiveThemes: NONE
    # booleans: gambling, unrestrictedWebAccess, lootBox, advertising,
    # ageAssurance, healthOrWellnessTopics, messagingAndChat, parentalControls,
    # userGeneratedContent, socialMedia (+ socialMediaAgeRestricted when true)
    gambling: false
    unrestrictedWebAccess: false
    socialMedia: false
    # overrides: ageRatingOverrideV2 NONE|NINE_PLUS|THIRTEEN_PLUS|SIXTEEN_PLUS|EIGHTEEN_PLUS|UNRATED
    #            (ageRatingOverride is deprecated) ;
    #            koreaAgeRatingOverride NONE|ALL|TWELVE_PLUS|FIFTEEN_PLUS|NINETEEN_PLUS
    #            + gracRatingClassificationNumber ;
    #            kidsAgeBand FIVE_AND_UNDER|SIX_TO_EIGHT|NINE_TO_ELEVEN ;
    #            developerAgeRatingInfoUrl (an http(s) URL)
    ageRatingOverrideV2: NONE
    # deliver drop-in: point at a JSON file instead of inlining keys
    # config_path: fastlane/rating_config.json
```

Every block is optional. Unknown age-rating **field names** are rejected (typo
guard); a **value** ANDP doesn't recognise yet passes through with a warning so a
value Apple adds later still works. `seventeenPlus`, removed from the API in 4.0,
is ignored with a warning instead of being sent.

## CLI

```bash
andp store pricing me.app.bundle --price 0.99        # or --price free
andp store availability me.app.bundle --territories USA,FRA   # or --all [--new-territories]
andp store age-rating me.app.bundle --config rating.json
andp store plan me.app.bundle                        # read-only diff of everything
andp store apply me.app.bundle                       # everything from andp.yml
```

All accept `--json` for a structured envelope and run in DRY-RUN without
credentials. Each result reports `changed: true|false` — `false` means the live
state already matched (idempotent skip).

## MCP tools

`store_plan` (read-only), `store_configure_pricing`,
`store_configure_availability` (annotated **destructive** — shrinking the set
delists territories), `store_set_age_rating`, `store_apply` (`version`,
`metadata_dir`). All library-first (they drive the service layer directly, not a
captured CLI stdout) and return `structuredContent`.

## Safety & semantics

- **Idempotent reconcile.** Re-running applies nothing when the live state already
  matches. Pricing recognises a live price whether its start date is null or past.
- **Full replace.** Setting a price replaces the schedule; setting availability
  replaces the territory set — a single atomic POST (no partial delist).
- **Delist guard.** An empty territory set is refused (delist via the ASC UI).
- **Preserve.** `available_in_new_territories` is carried forward when unspecified.
- **Best-effort apply.** `store apply` runs each block independently; a failed
  block is reported, the others still run, and a re-run heals a split state.
- Precheck adds advisory warnings (no price / zero territories / unset age rating)
  and blocking errors for the listing fields App Review requires (see Readiness).
