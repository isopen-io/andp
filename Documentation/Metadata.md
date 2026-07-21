# Release notes, screenshots & preview videos (v1.2)

ANDP pushes App Store metadata and media from a **folder tree** — release
notes per language, screenshots per device, and preview *videos* per device.

## Folder convention

```
<metadata-dir>/
  en-US/
    whatsNew.txt          → "What's New" (release notes)
    description.txt       → App description
    keywords.txt          → Keywords
    promotionalText.txt   → Promotional text
    supportUrl.txt        → Support URL
    marketingUrl.txt      → Marketing URL
    screenshots/
      APP_IPHONE_67/        01.png  02.png  …   (per Apple display type)
      APP_IPAD_PRO_3GEN_129/ 01.png …
    previews/
      APP_IPHONE_67/        01.mp4  …           (preview videos)
  fr-FR/
    whatsNew.txt
    screenshots/…
```

- Locale folders use App Store Connect locale codes (`en-US`, `fr-FR`, …).
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

- The **app record**, pricing, availability and age-rating declarations are not
  handled here (App Store Connect UI / future work).
- ANDP does not pre-validate that all *required* metadata is present — Apple
  validates synchronously at submission and its error detail is surfaced.
