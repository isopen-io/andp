# The metadata folder — texts, screenshots & preview videos

ANDP pushes App Store metadata and media from a **folder tree** — release
notes per language, screenshots per device, and preview *videos* per device.

## Folder convention

Both layouts are read — fastlane `deliver`'s snake_case names and ANDP's
camelCase ones — so an existing `fastlane/metadata` works as is.

```
<metadata-dir>/
  copyright.txt                → version copyright            (store apply)
  primary_category.txt         → primary category             (store apply)
  secondary_category.txt       → secondary category           (store apply)
  primary_first_sub_category.txt … secondary_second_sub_category.txt
  review_information/          → App Review details           (store apply)
    first_name.txt last_name.txt phone_number.txt email_address.txt
    demo_user.txt demo_password.txt demo_required.txt notes.txt
  default/                     → values for every locale that lacks them
  en-US/
    name.txt                   → app name (≤ 30)              (store apply)
    subtitle.txt               → subtitle (≤ 30)              (store apply)
    privacy_url.txt            → privacy policy URL           (store apply)
    privacy_choices_url.txt    → privacy choices URL          (store apply)
    apple_tv_privacy_policy.txt → privacy policy text (tvOS)  (store apply)
    description.txt            → description (≤ 4000)
    keywords.txt               → keywords (≤ 100)
    release_notes.txt | whatsNew.txt            → What's New (≤ 4000)
    promotional_text.txt | promotionalText.txt  → promotional text (≤ 170)
    support_url.txt | supportUrl.txt            → support URL
    marketing_url.txt | marketingUrl.txt        → marketing URL
    screenshots/
      APP_IPHONE_67/        01.png  02.png  …   (per Apple display type)
      APP_IPAD_PRO_3GEN_129/ 01.png …
    previews/
      APP_IPHONE_67/        01.mp4  …           (preview videos)
  fr-FR/
    …
```

- `andp publish` pushes the **version** texts (description → marketing URL)
  and the media; `andp store apply` pushes everything above, texts included,
  from the same folder (`store.metadata_dir` or `--metadata`). `andp.yml`
  (`store.localizations`, `store.version`, `store.review`…) overrides a file
  field by field.
- Do not commit secrets: prefer `store.review.demo_account_password_env`
  (and `_env` for the contact) to `demo_password.txt`.
- Every text is checked against Apple's limit before anything is sent; an
  empty file is ignored (it never blanks a field).
- Locale folders use App Store Connect locale codes (`en-US`, `fr-FR`, `it`, …).
- Device folders use Apple's raw **display type** (`APP_IPHONE_67`,
  `APP_IPAD_PRO_3GEN_129`, `APP_APPLE_TV`, `APP_APPLE_VISION_PRO`, …) — no
  guessing/aliasing, so what you name is what Apple gets.
- Screenshots: `.png/.jpg/.jpeg`; previews: `.mp4/.mov/.m4v`.
- **Idempotent:** a screenshot/preview set that already holds assets is skipped
  (not duplicated), so re-running is safe.

## Standalone

```bash
andp publish me.your.app 1.2.0 ./metadata --json
```

Pushes every locale's notes, screenshots and previews to version 1.2.0.

## During submission (`--ship`)

Add `--metadata <dir>` so the release machine pushes everything **before** the
approval gate:

```bash
andp release start build/App.ipa --ship --metadata ./metadata --json
# plan: … version → build_attached → compliance → metadata → submit
andp release poll <id> --json    # runs the metadata push as one resumable step
```

The metadata push is one machine step; a retryable failure re-runs it safely
(metadata is upserted, populated media sets are skipped).

## Limits

- Pricing, availability, age rating, categories, app name and the rest of the
  listing are `andp store plan` / `andp store apply`
  ([StoreConfig.md](StoreConfig.md)).
- `andp readiness appstore` checks the fields App Review requires; Apple stays
  the final authority at submission and its error detail is surfaced.
