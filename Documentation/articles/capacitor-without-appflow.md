# Publishing a Capacitor app to TestFlight without Appflow — 100% API

*Ionic Appflow sunsets on December 31, 2027. This is the migration path we
used in production for a real Capacitor app, publishing to TestFlight with
nothing but the App Store Connect API and `xcodebuild`. No Appflow, no
fastlane, no Mac connected to an Apple ID.*

## What you need

- An App Store Connect **API key** (`.p8`, Key ID, Issuer ID) — created in
  *Users and Access → Integrations*. The Issuer ID is the UUID at the top of
  that page, not the 10-character Key ID (a classic mixup).
- An **Apple Distribution certificate** whose private key is in your keychain
  (or created via `POST /v1/certificates` from a CSR).
- The app record created once in the App Store Connect UI (the only step the
  API cannot do).
- [ANDP](../../README.md): `pip install -e .`

## Step 0 — Preflight before anything else

```bash
cp secrets.example.yml secrets.yml   # key_id, issuer_id, key_content
andp verify your.bundle.id
```

`verify` fails with the exact missing piece: placeholder credentials, a key
Apple rejects (401), or a missing app record. Fix what it names, re-run,
and only build once you see `PREFLIGHT PASSED`.

**Real-world catch:** our local Capacitor `appId` had drifted from the bundle
id registered on App Store Connect. `verify your.bundle.id` surfaced it
immediately ("app not found on this account") — before any build was wasted.
Align `capacitor.config.ts` (`appId`), the Xcode project's
`PRODUCT_BUNDLE_IDENTIFIER`, and your push topic on the ASC record's bundle id.

## Step 1 — Archive

```bash
npm run build && npx cap sync ios
xcodebuild -workspace ios/App/App.xcworkspace -scheme App \
  -sdk iphoneos -configuration Release \
  -archivePath build/App.xcarchive archive \
  -allowProvisioningUpdates \
  -authenticationKeyPath ~/.private_keys/AuthKey_XXXX.p8 \
  -authenticationKeyID XXXX -authenticationKeyIssuerID <issuer-uuid> \
  DEVELOPMENT_TEAM=<team-id>
```

## Step 2 — If the export hits "Cloud signing permission error"

`xcodebuild -exportArchive` with automatic signing may fail with:

```
error: exportArchive Cloud signing permission error
error: exportArchive No profiles for '<bundle-id>' were found
```

Your API key lacks xcodebuild's cloud-signing permission. You do **not** need
to escalate the key's role — create the distribution profile through the API
yourself (ANDP's `provisioning.py`):

1. `GET /v1/certificates?filter[certificateType]=DISTRIBUTION` → pick the one
   whose serial matches a keychain identity;
2. `GET /v1/bundleIds?filter[identifier]=<bundle-id>` → resource id;
3. `POST /v1/profiles` (`profileType: IOS_APP_STORE`, bundleId + certificate
   relationships) → decode `profileContent` (base64) into
   `~/Library/Developer/Xcode/UserData/Provisioning Profiles/`;
4. Export with **manual** signing:

```xml
<key>signingStyle</key><string>manual</string>
<key>method</key><string>app-store-connect</string>
<key>provisioningProfiles</key>
<dict><key>your.bundle.id</key><string>YourProfileName</string></dict>
```

## Step 3 — Upload through the Build Upload API

```bash
andp upload build/export/App.ipa
# Upload started: buildUploads/<id>
andp status your.bundle.id 1
# Build 1: VALID  <- it's in TestFlight
```

ANDP reads the bundle id, version and build number from the IPA's own
Info.plist, resolves the app record, and drives Apple's pure-HTTP
reserve/upload/commit flow (see
[the observed API contract](build-upload-api-observed-contract.md) for the
three undocumented requirements it handles for you).

## Step 4 — TestFlight distribution, by API too

```bash
andp testflight your.bundle.id "Beta" add tester@example.com
andp submit your.bundle.id 1.0        # App Review, when ready
```

## CI: the same flow as a 5-line workflow

```yaml
jobs:
  release:
    uses: isopen-io/andp/.github/workflows/andp-release.yml@main
    with: { scheme: App, app-dir: ., andp-ref: main }
    secrets: inherit
```

Or just gate your PRs with the preflight:

```yaml
- uses: isopen-io/andp@main
  with:
    key-id: ${{ secrets.ASC_KEY_ID }}
    issuer-id: ${{ secrets.ASC_ISSUER_ID }}
    private-key: ${{ secrets.ASC_PRIVATE_KEY }}
    bundle-id: your.bundle.id
```
