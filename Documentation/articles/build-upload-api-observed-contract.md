# The App Store Connect Build Upload API: the contract you'll actually hit

*Observed live against App Store Connect API 4.4, July 2026. Every error
message below is verbatim from the API.*

Apple's Build Upload API (GA since late 2025) finally lets you upload an IPA
to App Store Connect with nothing but HTTPS — no `altool`, no Transporter, no
Xcode. The flow is: reserve a build upload, reserve the file, PUT the chunks,
commit. Simple — except the documentation omits three things you will hit on
your very first real upload. This article documents them, with the exact
errors, so you don't have to burn an afternoon.

## The flow

```
POST  /v1/buildUploads          -> reserve the build slot
POST  /v1/buildUploadFiles      -> reserve the file, get uploadOperations
PUT   <each operation URL>      -> upload the chunks
PATCH /v1/buildUploadFiles/{id} -> uploaded=true (commit)
GET   /v1/builds                -> poll processingState until VALID
```

Authentication is the standard ES256 JWT (`kid` = Key ID, `iss` = Issuer ID,
`aud: appstoreconnect-v1`, max 20-minute lifetime).

## Gotcha 1 — `buildUploads` requires an `app` relationship

Send the documented attributes alone:

```json
{ "data": { "type": "buildUploads", "attributes": {
    "cfBundleShortVersionString": "1.0",
    "cfBundleVersion": "1",
    "platform": "IOS" } } }
```

and you get:

```
409: You must provide a value for the relationship 'app' with this request
```

The reservation must be linked to the app record:

```json
{ "data": { "type": "buildUploads",
    "attributes": { "cfBundleShortVersionString": "1.0",
                    "cfBundleVersion": "1", "platform": "IOS" },
    "relationships": { "app": { "data": { "type": "apps", "id": "<app-id>" } } } } }
```

Resolve the app id first with `GET /v1/apps?filter[bundleId]=<bundle-id>` —
and read the bundle id from the IPA's own `Info.plist`
(`CFBundleIdentifier`), not from your repo's config: the API checks the
binary, and mismatched metadata is rejected later at processing time.

## Gotcha 2 — `assetType` is `ASSET`, not `IPA`

Intuition says the file you are reserving is of type `IPA`. The API disagrees:

```
409: 'IPA' is not a valid value for the attribute 'assetType'.
Expected one of: 'ASSET', 'ASSET_DESCRIPTION', 'ASSET_SPI'
```

Your IPA is an `ASSET`.

## Gotcha 3 — `uti` is mandatory

Same request, second half of the same 409:

```
409: You must provide a value for the attribute 'uti' with this request
```

The Uniform Type Identifier for an IPA is `com.apple.ipa`. The working
`buildUploadFiles` reservation is therefore:

```json
{ "data": { "type": "buildUploadFiles",
    "attributes": { "fileName": "App.ipa", "fileSize": 5556953,
                    "assetType": "ASSET", "uti": "com.apple.ipa" },
    "relationships": { "buildUpload": { "data": {
        "type": "buildUploads", "id": "<reservation-id>" } } } } }
```

The response's `uploadOperations` array gives you the PUT targets (method,
url, offset, length, headers). Upload each chunk, PATCH `uploaded=true`, then
poll `GET /v1/builds` until `processingState` leaves `PROCESSING` —
`VALID` means the build is in TestFlight.

## Use it without writing it

All of the above is implemented — with the observed contract encoded in
contract tests — in [ANDP](../../README.md), including an honest preflight
that tells you *before* building whether the upload can work:

```bash
pip install -e .
andp verify me.your.app     # credentials -> JWT -> live API -> app record
andp upload build/Your.ipa  # reads bundle id/version/build from the IPA itself
```
