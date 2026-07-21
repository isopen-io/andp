# Store configuration — pricing, territories, age rating

ANDP configures the three App Store settings that `fastlane deliver` covers
(pricing, age rating) plus one it does not (territory availability), the same
agent-native way as the rest of the tool: a declarative block in `andp.yml`,
reconciled to App Store Connect idempotently, with dry-run and an audit trail.

These use the **current** App Store Connect API models: pricing is
`appPriceSchedules`/`appPricePoints` (the tier system is gone), availability is
`appAvailabilities` v2, age rating is the 2025-overhauled `ageRatingDeclaration`.

## `andp.yml`

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
    # content descriptors: NONE | INFREQUENT_OR_MILD | FREQUENT_OR_INTENSE
    violenceCartoonOrFantasy: NONE
    matureOrSuggestiveThemes: NONE
    # booleans (incl. 2025 additions: lootBox, messagingAndChat, parentalControls,
    # userGeneratedContent, advertising, ageAssurance, healthOrWellnessTopics …)
    gambling: false
    unrestrictedWebAccess: false
    # overrides: ageRatingOverride NONE|SEVENTEEN_PLUS|UNRATED ;
    #            koreaAgeRatingOverride NONE|FIFTEEN_PLUS|NINETEEN_PLUS ;
    #            kidsAgeBand FIVE_AND_UNDER|SIX_TO_EIGHT|NINE_TO_ELEVEN
    ageRatingOverride: NONE
    # deliver drop-in: point at a JSON file instead of inlining keys
    # config_path: fastlane/rating_config.json
```

Every block is optional. Unknown age-rating **field names** are rejected (typo
guard); a **value** ANDP doesn't recognise yet passes through with a warning so a
value Apple adds later still works.

## CLI

```bash
andp store pricing me.app.bundle --price 0.99        # or --price free
andp store availability me.app.bundle --territories USA,FRA   # or --all [--new-territories]
andp store age-rating me.app.bundle --config rating.json
andp store apply me.app.bundle                       # everything from andp.yml
```

All accept `--json` for a structured envelope and run in DRY-RUN without
credentials. Each result reports `changed: true|false` — `false` means the live
state already matched (idempotent skip).

## MCP tools

`store_configure_pricing`, `store_configure_availability` (annotated
**destructive** — shrinking the set delists territories), `store_set_age_rating`,
`store_apply`. All library-first (they drive the service layer directly, not a
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
  without ever blocking the hard checks.
