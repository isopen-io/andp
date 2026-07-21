# Design — App Store configuration parity (`deliver` 100 %)

**Goal.** Close the last two gaps vs. fastlane `deliver`: **pricing/territories** and
**age rating**, and expose them the same agent-native way as the rest of ANDP
(library-first service → CLI + MCP), while honouring the **recent** App Store
Connect API models (the pricing tier system is gone; availability moved to v2;
age rating was overhauled in 2025).

This is not a thin wrapper: it is a declarative "desired store state" that an
agent (or a human) writes once in `andp.yml`, and ANDP reconciles against the
live App Store Connect state — idempotently, with dry-run, validation, and an
audit trail.

---

## 1. Recent ASC API models (ground truth used here)

### 1.1 Pricing — `appPriceSchedules` (tiers removed)
The `appPriceTier` system is deprecated/removed. A price is now a *schedule*:

- Read: `GET /v1/apps/{id}/appPriceSchedule` → the current schedule (or none).
- Price points per territory:
  `GET /v1/apps/{id}/appPricePoints?filter[territory]=USA&include=territory`
  (paginated). Each `appPricePoint` has `attributes.customerPrice` (e.g. `"0.99"`,
  `"0.00"` = free) and encodes the tier in its id.
- Set: `POST /v1/appPriceSchedules` with relationships `app`, `baseTerritory`,
  `manualPrices`, plus an `included` array of `appPrices` that each reference an
  `appPricePoint` by a **client temp id** (`"${p0}"`). A `startDate: null` price
  goes live immediately. Prices in other territories are auto-derived from the
  base-territory price point.

```json
{
  "data": {"type": "appPriceSchedules",
    "relationships": {
      "app": {"data": {"type": "apps", "id": "APP"}},
      "baseTerritory": {"data": {"type": "territories", "id": "USA"}},
      "manualPrices": {"data": [{"type": "appPrices", "id": "${p0}"}]}}},
  "included": [
    {"type": "appPrices", "id": "${p0}",
     "attributes": {"startDate": null, "endDate": null},
     "relationships": {"appPricePoint": {"data": {"type": "appPricePoints", "id": "PP"}}}}]
}
```

**Free app** = pick the base-territory price point whose `customerPrice` parses to
`0`, and set the schedule with it.

### 1.2 Availability — `appAvailabilities` v2
`deliver` does **not** support territories at all → ANDP will *exceed* parity.

- Read: `GET /v1/apps/{id}/appAvailabilityV2` → `{id, attributes.availableInNewTerritories}`;
  then `GET /v2/appAvailabilities/{id}/territoryAvailabilities` (paginated, ≤50 per
  include) → per-territory `{available, territory}`.
- All territories: `GET /v1/territories` (paginated) → ids like `USA`, `FRA`, `DEU`.
- Set: `POST /v2/appAvailabilities` with attribute `availableInNewTerritories` and
  relationship `territoryAvailabilities`, plus an `included` array of
  `territoryAvailabilities` each `{available:true, territory:{id}}` via temp ids.

```json
{
  "data": {"type": "appAvailabilities",
    "attributes": {"availableInNewTerritories": false},
    "relationships": {
      "app": {"data": {"type": "apps", "id": "APP"}},
      "territoryAvailabilities": {"data": [{"type": "territoryAvailabilities", "id": "${t0}"}]}}},
  "included": [
    {"type": "territoryAvailabilities", "id": "${t0}",
     "attributes": {"available": true},
     "relationships": {"territory": {"data": {"type": "territories", "id": "USA"}}}}]
}
```

### 1.3 Age rating — `ageRatingDeclaration` (2025 overhaul)
- Read (app-global): `GET /v1/appInfos/{id}/ageRatingDeclaration` → `{id, attributes}`.
- Set: `PATCH /v1/ageRatingDeclarations/{id}` with the attribute subset.
- Field taxonomy (matches `deliver`'s `app_rating_config_path` keys + the 2025
  additions). Three value-kinds:
  - **Ternary** (`NONE | INFREQUENT_OR_MILD | FREQUENT_OR_INTENSE`):
    `alcoholTobaccoOrDrugUseOrReferences`, `contests`, `gamblingSimulated`,
    `gunsOrOtherWeapons`, `horrorOrFearThemes`, `matureOrSuggestiveThemes`,
    `medicalOrTreatmentInformation`, `profanityOrCrudeHumor`,
    `sexualContentGraphicAndNudity`, `sexualContentOrNudity`,
    `violenceCartoonOrFantasy`, `violenceRealistic`,
    `violenceRealisticProlongedGraphicOrSadistic`.
  - **Boolean**: `gambling`, `unrestrictedWebAccess`, `lootBox`, `advertising`,
    `ageAssurance`, `healthOrWellnessTopics`, `messagingAndChat`,
    `parentalControls`, `userGeneratedContent`.
  - **Enum**: `kidsAgeBand` (`FIVE_AND_UNDER|SIX_TO_EIGHT|NINE_TO_ELEVEN` or null),
    `ageRatingOverride` (`NONE|SEVENTEEN_PLUS|UNRATED`),
    `koreaAgeRatingOverride` (`NONE|FIFTEEN_PLUS|NINETEEN_PLUS`).

Unknown keys / wrong enum values are a **client-side validation error** with a
clear message (not an opaque Apple 400). The taxonomy lives in one dict so it is
trivial to extend when Apple adds fields.

---

## 2. Config surface — `andp.yml store:` (single declarative source)

App-global, version-independent store settings belong with policy, not the
per-locale metadata tree. New `store:` block (all keys optional):

```yaml
store:
  pricing:
    base_territory: USA
    price: "0.00"          # "0"/"0.00"/"free" => free; else exact customerPrice string
    # price_point_id: <id> # advanced escape hatch, wins over price
  availability:
    territories: [USA, FRA, DEU]   # or: all
    available_in_new_territories: false
  age_rating:
    violenceCartoonOrFantasy: NONE
    gambling: false
    ageRatingOverride: NONE
```

`load_policy()` gains a `store` key (default `{}`), parsed leniently. Age rating
can alternatively be pointed at a JSON file for `deliver` drop-in parity:
`age_rating: { config_path: fastlane/rating_config.json }`.

---

## 3. Managers (new modules under `andp/asc/`)

**`pricing.py` — `PricingManager`**
- `get_schedule(app_id)` → schedule dict or `None`.
- `list_price_points(app_id, territory)` → paginated list.
- `find_price_point(app_id, territory, customer_price)` → the point matching the
  target price (string compare on normalised float); `None` if absent.
- `find_free_price_point(app_id, territory)` → point with `customerPrice==0`.
- `current_base_price_point_id(app_id, base_territory)` → id in the live schedule
  for the base territory (for idempotency skip), or `None`.
- `set_schedule(app_id, base_territory, price_point_id, start_date=None)` → POST.

**`availability.py` — `AvailabilityManager`**
- `get_availability(app_id)` → `{id, available_in_new_territories}` or `None`.
- `list_available_territories(app_id)` → set of territory ids currently available.
- `list_all_territories()` → set of every territory id.
- `set_availability(app_id, territories, available_in_new_territories=False)` → POST.

**`agerating.py` — `AgeRatingManager`**
- `get_declaration(app_id)` → `{id, attributes}` (via `appInfos`) or `None`.
- `update_declaration(declaration_id, attributes)` → PATCH.
- `validate(config)` → `(clean_attributes, errors)` — pure, no I/O; enforces the
  taxonomy in §1.3, resolves `config_path`.

Wired into `Managers` as `.pricing`, `.availability`, `.age_rating`.

---

## 4. Service layer (`andp/service.py`) — library-first

Pure dict-returning, dry-run-aware, error-wrapped (same shape as `publish`/`precheck`):

- `configure_pricing(bundle_id, account, base_territory=None, price=None, price_point_id=None, project_root=".")`
- `configure_availability(bundle_id, account, territories=None, available_in_new_territories=None, project_root=".")`
- `configure_age_rating(bundle_id, account, declaration=None, project_root=".")`
- `configure_store(bundle_id, account, project_root=".")` — reads `andp.yml store:`
  and applies each present sub-block, returning a combined report
  `{pricing:{...}, availability:{...}, age_rating:{...}}`. Missing sub-blocks are
  skipped (reported as `skipped: "not configured"`). This is the one agent-facing
  "apply my store config" verb; the granular three are for targeted control.

Each returns `{command, ok, dry_run, changed: bool, detail...}`. `changed:false`
means the live state already matched (idempotent skip) — an agent can rely on it.

**Idempotency.**
- Pricing: skip POST if `current_base_price_point_id == target`.
- Availability: skip POST if the live available-territory set equals the target set
  **and** `available_in_new_territories` matches.
- Age rating: PATCH only the keys that differ from the live declaration; skip if
  none differ.

**Validation / safety.**
- Unknown territory codes → non-retryable error listing valid examples.
- `territories: all` expands via `list_all_territories()`.
- Empty target territory set → refuse (would delist the app) unless explicitly
  intended; report as an error with remediation.
- Age rating unknown key / bad enum → non-retryable error naming the field.

---

## 5. CLI (`andp store …`) + MCP tools

**CLI** — new `store` command with subcommands (mirrors `release` sub-dispatch):
- `andp store pricing <bundle_id> [--territory USA] [--price 0.00|free]`
- `andp store availability <bundle_id> [--territories USA,FRA | --all] [--new-territories]`
- `andp store age-rating <bundle_id> [--config <json>]`
- `andp store apply <bundle_id>`   (everything from `andp.yml`)
- `--json` supported throughout; DRY-RUN when unconfigured.

**MCP** — four library-first tools (via `service`, structuredContent):
`store_configure_pricing`, `store_configure_availability`, `store_set_age_rating`,
`store_apply`. Annotations: `readOnly:false`, `idempotent:true`,
`destructive:false` — but `store_configure_availability`'s description warns it
**replaces** the territory set (shrinking it delists territories).

---

## 6. Precheck integration (light)
`run_precheck` gains advisory checks (warnings, never hard-fail unless truly
blocking):
- `age_rating`: **error** if no declaration exists for the app (Apple blocks
  submission without one).
- `pricing`: **warning** if no price schedule is set.
- `availability`: **warning** if the app is available in zero territories.

Kept minimal to avoid scope creep; the guarded `_do_prechecked` confinement from
v1.3 already ensures a read error here can never brick a release.

---

## 7. Non-goals (explicit)
- In-app purchase pricing/availability (separate resource tree).
- Pre-orders, phased price changes beyond a single immediate price.
- Editing the *set* of territories incrementally via PATCH per-territory (we POST
  the whole desired set — simpler, declarative, matches "reconcile to state").

---

## 8. Test plan (TDD, FakeSession)
Manager unit tests (request shape + pagination + not-found), service tests
(dry-run, idempotent skip, validation errors, all-territories expansion,
free-price detection), CLI tests (arg parsing, --json, dry-run), MCP tests
(tool listing, dispatch, structuredContent, availability warning annotation),
precheck tests (age-rating-missing error, pricing/availability warnings).
Every branch RED→GREEN.

---

## 9. Review log

### 9.1 Design review (adversarial subagent) — resolved before implementation
Verified against Apple docs + spaceship/community usage. Decisions:

- **B1 (availability write cap / replace):** Reads use `client.get_all` over the
  dedicated `GET /v2/appAvailabilities/{id}/territoryAvailabilities` (community &
  spaceship use `limit=200`; pagination via `links.next` covers any size). Writes
  are a **single atomic POST** — JSON:API POST is all-or-nothing, so there is NO
  partial-delist failure mode; an oversized/invalid payload is a *loud* 4xx via
  `from_asc_error`, never a silent shrink. The silent-delist risk lives entirely
  in *read* pagination (B2) and the empty-set case (guarded). `POST /v2/appAvailabilities`
  is treated as set/replace per Apple's documented create; a 409 (availability
  already exists) surfaces cleanly with remediation. Not claimed live-verified.
- **B2 (pagination):** `list_all_territories`, `list_available_territories`,
  `list_price_points` MUST use `get_all`; tests assert >50 items across pages.
- **B3 (age rating appInfo):** `get_declaration` selects the **editable** appInfo
  (state in an editable set), not `appInfos[0]`, avoiding a PATCH on the locked
  live declaration. Write endpoint `PATCH /v1/ageRatingDeclarations/{id}`.
- **S1:** `availableInNewTerritories` is read and carried forward when the caller
  omits it (never silently flipped to false).
- **S2:** dry-run returns `changed: null` (planned) and never dereferences
  `managers` (guarded behind `dry_run`).
- **S3:** pricing POST is full-replace (documented here + in MCP tool text); the
  idempotency "current base price" is the manualPrice active now (startDate null
  or past, latest such).
- **S4:** `configure_store` is **best-effort-with-report**: each block runs
  independently, per-block `ok`, top-level `ok=false` if any block failed; blocks
  are idempotent so a re-run heals a split state.
- **S5:** precheck checks the declaration is *answered* (heuristic: exists and not
  entirely unanswered), not mere existence.
- **S6:** price equality uses `decimal.Decimal`, never `float`.
- **S7:** all four `configure_*` use the full `publish()` envelope
  (`ASCAPIError→from_asc_error`, `AndpError→_error_result`, `Exception→from_unexpected`).
- **S8:** MCP `store_configure_availability` is `destructiveHint: true`.
- **N1:** `get_all` reads drop `include=` (it discards sideloaded objects); territory
  id read from `relationships.territory.data.id`.
- **N2:** available-territory set filters `attributes.available == true`.
- **N4:** unknown age-rating *keys* → hard error (typo guard); unknown *enum values*
  on a known key → passthrough **with a warning** (forward-compat with new Apple
  values without shipping a new ANDP release).
- **N7:** `load_policy` `store` parsing is isolated/lenient — a malformed `store:`
  block cannot regress `allow_submit`/`compliance`.
- **N8:** the `changed` flag compares only the base-territory price point and the
  territory set; per-territory manual overrides / future scheduled changes are out
  of scope (documented, not oversold).

### 9.2 Code review (adversarial subagent) — resolved before commit
Three real defects found, all fixed with tests that exercise the failing input:

- **BLOCKER 1 — pricing idempotency only recognised `startDate == null`,
  contradicting S3.** A live price read back with a *past* `startDate` (Apple's
  normal representation once it has gone live) was treated as not-current →
  `current_base_price_point_id` returned None → a same-price reconcile re-POSTed a
  full-replace schedule (breaking the `idempotentHint:true` contract and wiping
  any future-scheduled price). Fixed: a manualPrice is live when `startDate` is
  null OR `<= today`; the latest-starting live base-territory price wins. New test
  `test_current_base_price_point_id_recognizes_a_past_start_date`.
- **SHOULD-FIX 2 — `_resolve_age_rating_config` leaked `TypeError` on a non-object
  config file.** A `config_path` JSON file whose top level is an array/number/bool
  made `dict.update` raise `TypeError` (not caught by `except ValueError`), leaking
  a traceback (and, worse, aborting `configure_store` after earlier blocks had
  already POSTed). Fixed: reject a non-dict with a `ValueError` → `bad_config`
  envelope; AND `configure_store` now wraps each block so a raising block is
  recorded as that block's failure, never aborting the rest (true S4 best-effort).
  Tests `test_age_rating_config_path_non_dict_is_bad_config`,
  `test_configure_store_contains_a_raising_block`.
- **SHOULD-FIX 3 — a malformed `andp.yml` leaked `yaml.YAMLError` out of the
  `{ok,error}` envelope.** The policy read sat before the try/except. Fixed with
  `_read_store`, which converts a YAML parse error into an AndpError `bad_config`;
  all four `configure_*` guard it. Test `test_pricing_malformed_andp_yml_is_wrapped`.
- **NIT (coverage) — added `test_availability_all_idempotent_skip`** to pin the
  `territories: all` reconcile behaviour.
- NIT (precheck store reads re-run each poll) acknowledged; correctness-safe
  (warnings only, reads swallowed) — left as-is.

Verified clean by the reviewer and not changed: Decimal/free price matching, the
MCP `["all"]` schema, `_take_opt` with a missing value. Final: **298 tests pass.**
