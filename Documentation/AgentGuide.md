# ANDP Agent Guide — from code to the App Store

The complete operational playbook for an AI agent (Claude Code, Cursor, Codex, or
any MCP host) to drive an iOS app **from a source repo all the way to a live App
Store submission** — safely, resumably, and with a machine-readable contract at
every step.

> Companion docs: [Agents.md](Agents.md) (why ANDP is agent-native),
> [Metadata.md](Metadata.md) (folder convention), [StoreConfig.md](StoreConfig.md)
> (pricing/territories/age rating), [ASC-API.md](ASC-API.md) (API layer),
> [Troubleshooting.md](Troubleshooting.md).

---

## 0. Mental model (read this first)

- **Library-first.** One service layer (`andp/service.py`) is the single source of
  truth. The **CLI** (`andp …`) and the **MCP server** (`python3 -m andp.mcp`)
  are thin adapters over it — they return the *same* structured result. Never
  scrape human text; always take the JSON / `structuredContent`.
- **Every result is a typed envelope**: `{command, ok, ...}` on success, or
  `{command, ok:false, error:{code, message, retryable, remediation}}` on failure.
  An agent branches on `ok`, `error.code`, and `error.retryable` — never on prose.
- **A release is a resumable state machine**, not a blocking call. You *advance* it
  one step per `poll`; a crash loses nothing; it never re-uploads.
- **Destructive actions are gated.** Submitting to App Review needs an explicit
  approval (policy or an out-of-band `approve`). Shrinking territory availability
  is annotated destructive. Nothing irreversible happens by accident.
- **DRY-RUN when unconfigured.** With placeholder credentials every command returns
  a *plan* instead of calling Apple, so you can rehearse the whole flow offline.

The three questions an agent asks, and the primitive that answers each:

| Question | Primitive |
|---|---|
| *Can I even publish with these credentials?* | `verify` |
| *Get this build to beta / the App Store, resumably.* | `release start` → `release poll` |
| *Is this version submittable before I cross the point of no return?* | `precheck` |

---

## 1. Setup an agent must ensure exists

### 1.1 `secrets.yml` — credentials (never commit real ones)
```yaml
accounts:
  primary:
    asc_api:
      key_id:   "ABCDE12345"                 # App Store Connect API key id
      issuer_id: "69a6de89-....-...."          # Issuer id (UUID)
      key_content: |                          # the .p8 private key, inline
        -----BEGIN PRIVATE KEY-----
        ...
        -----END PRIVATE KEY-----
```
If any field is a placeholder / missing, ANDP runs in **DRY-RUN** (no API calls).
Use `--account <name>` / the `account` arg to select a non-`primary` account.

### 1.2 `andp.yml` — policy + store desired-state
```yaml
policy:
  allow_submit: false          # default: agents may NOT submit to App Review
compliance:
  uses_non_exempt_encryption: false   # or declare it in the IPA Info.plist
store:                          # optional; see §7 and StoreConfig.md
  pricing:      { base_territory: USA, price: "0.99" }
  availability: { territories: [USA, FRA, DEU] }
  age_rating:   { violenceCartoonOrFantasy: NONE, gambling: false }
```

### 1.3 Optional: audit trail
Set `ANDP_AUDIT_LOG=/path/audit.jsonl` — every API **mutation** (POST/PATCH/DELETE)
is appended as one JSON line (`ts`, `method`, `path`, `status`). Reads are not
logged. Turn this on when an agent publishes so "what did it do?" is always
answerable.

---

## 2. The golden path (end to end)

```
 (dev) ──► verify ──► build+sign ──► release start [--ship] ──► release poll* 
                                                          │
                          TestFlight ◄────────────────────┤ (beta: done at VALID/group)
                                                          │
                          store apply (price/territories/age) ── publish (metadata/media)
                                                          │
                                    precheck ──► approve gate ──► submitted ──► done
```

`poll*` = call repeatedly until `terminal:true`. Steps in detail below.

### Step 1 — `verify` (can I act?)
```bash
andp verify me.your.app --json
```
```json
{"command":"verify","ok":true,
 "checks":[{"name":"credentials","ok":true},{"name":"jwt","ok":true},
           {"name":"api_auth","ok":true},{"name":"app_record","ok":true}],
 "app":{"id":"6786703445","name":"YourApp","bundle_id":"me.your.app"}}
```
`ok:false` → the failing check names the blocker (e.g. `"missing":["issuer_id"]`),
exit code 1. **Do not build** until `ok`.

> The app *record* must exist once in App Store Connect (there is no
> `POST /v1/apps`). Everything after that is API-driven.

### Step 2 — build + sign
Use your own pipeline (`xcodebuild archive` → `-exportArchive`) to produce a
signed `.ipa`. ANDP reads bundle id / version / build number from the IPA's own
`Info.plist`, so an agent **cannot** ship mismatched metadata.

### Step 3 — `release start`
```bash
andp release start build/App.ipa --group "Beta" --json          # TestFlight only
andp release start build/App.ipa --ship --group "Beta" --metadata ./fastlane/metadata --json
```
Returns a `release_id`. Flags:
- `--group <name>` — link the build to a TestFlight group.
- `--ship` — continue past TestFlight to an App Store submission (gated).
- `--metadata <dir>` — with `--ship`, push notes/screenshots/previews first (§6).
- `--no-precheck` — with `--ship`, skip the built-in precheck stage.
- Starting the **same IPA** again *resumes* the existing release (idempotent).

### Step 4 — `release poll` (the agent loop)
Advance one non-blocking step at a time until terminal:
```json
{"state":"processing","terminal":false,"retry_after":60}   // come back in 60s
{"state":"awaiting_approval","terminal":false,"needs_approval":true,
 "next_action":"release approve <id> (or set policy.allow_submit)"}
{"state":"done","terminal":true,"ok":true}
```
**Agent loop contract:**
1. `poll`. Read `state`, `terminal`, `retry_after`, `needs_approval`,
   `needs_precheck_fix`, `error`.
2. If `retry_after` present → wait that many seconds (or do other work), poll again.
3. If `needs_approval` → open the gate (§8), poll again.
4. If `needs_precheck_fix` → fix what `precheck_report` lists (§6/§7), poll again.
5. If `terminal:true` → stop. `state:"done"` = success; `state:"failed"` = read
   `error` (typed, with `remediation`).
6. Never busy-loop faster than `retry_after`.

### Step 5 — App Store metadata / store config (only with `--ship`)
Push localized text + media (§6) and set price/territories/age rating (§7). These
can be done before `release start` or while the release parks at
`awaiting_approval`.

### Step 6 — the approval gate → submitted → done
See §8. The machine **never** crosses into `submit` on its own.

---

## 3. The release state machine (authoritative)

```
created → app_resolved → uploaded → processing → valid
                                                   │
                         (--group) group_linked ◄──┤
                                                   │            (no --ship)
                                                   └──────────────► done
   --ship:                                         │
   valid / group_linked → version_ensured → build_attached → compliance_set
        → metadata_pending → prechecked → awaiting_approval → submitted → done

 terminal states: done | failed
```

| State | Meaning | What the agent does |
|---|---|---|
| `created` | just started | poll |
| `app_resolved` | app record found | poll |
| `uploaded` | binary uploaded (write-ahead, pinned build id) | poll |
| `processing` | Apple is ingesting the build | wait `retry_after`, poll |
| `valid` | build is VALID | poll |
| `group_linked` | build added to TestFlight group | poll |
| `version_ensured` | editable App Store version resolved | poll |
| `build_attached` | build attached to the version | poll |
| `compliance_set` | export compliance declared | poll |
| `metadata_pending` | pushing `--metadata` folder (if any) | poll |
| `prechecked` | precheck ran | if `needs_precheck_fix`: fix, poll. else poll |
| `awaiting_approval` | **gate** | `approve` (or policy), then poll |
| `submitted` | review submission created & submitted | poll |
| `done` | ✅ terminal success | stop |
| `failed` | ❌ terminal failure | read `error`, remediate, maybe `reset` |

Guarantees: each `poll` performs **at most one external effect** and persists
state to `.andp/state/<release_id>.json` *before* returning. Resumable across
crashes; never re-uploads; a reused build number never resolves the wrong binary.
`prechecked` and `awaiting_approval` are **non-terminal waiting** states — a read
error there never bricks the release into a re-upload.

Inspect without advancing: `andp release status <id> --json`,
`andp release list --json`. Recover a stuck/terminal release:
`andp release reset <id>` (discards its state so you can start over).

---

## 4. Full surface reference (CLI ↔ MCP ↔ service)

| Purpose | CLI | MCP tool | service fn |
|---|---|---|---|
| Preflight | `verify [bundle]` | `verify` | — (CLI-backed) |
| Upload only | `upload <ipa>` | `upload` | — |
| Build status | `status <bundle> <build#>` | `status` | — |
| Start release | `release start <ipa> [flags]` | `release_start` | `release_start` |
| Advance release | `release poll <id>` | `release_poll` | `release_poll` |
| Read release | `release status <id>` | `release_status` | `release_status` |
| List releases | `release list` | `release_list` | `release_list` |
| Reset release | `release reset <id>` | — | `release_reset_by_id` |
| Approve gate | `release approve <id>` | — | `release_approve` |
| TestFlight testers | `testflight <bundle> <group> add <emails…>` | `testflight_add` | — |
| Push metadata/media | `publish <bundle> <ver> <dir>` | — | `publish` |
| Precheck | `precheck <bundle> <ver>` | `precheck` | `precheck` |
| Set price | `store pricing <bundle> [--price]` | `store_configure_pricing` | `configure_pricing` |
| Set territories | `store availability <bundle> [--all]` | `store_configure_availability` | `configure_availability` |
| Set age rating | `store age-rating <bundle> [--config]` | `store_set_age_rating` | `configure_age_rating` |
| Apply all store cfg | `store apply <bundle>` | `store_apply` | `configure_store` |
| Submit (gated) | `submit <bundle> <ver>` | `submit` | — |

Every CLI command accepts `--json` and `--account <name>`.

### MCP tool annotations (2025-03-26)
The host reads these to reason about risk *before* calling:

| tool | readOnly | destructive | idempotent |
|---|---|---|---|
| `verify`, `status`, `release_status`, `release_list`, `precheck` | ✅ | — | ✅ |
| `release_start`, `testflight_add`, `store_configure_pricing`, `store_set_age_rating`, `store_apply` | — | — | ✅ |
| `store_configure_availability` | — | ✅ | ✅ |
| `release_poll`, `upload` | — | — | ❌ |
| `submit` | — | ✅ | ❌ |

`store_configure_availability` is destructive because shrinking the set **delists**
the app in removed territories. `submit` is refused unless `policy.allow_submit:
true`.

MCP config (Claude Code / any host):
```json
{"mcpServers":{"andp":{"command":"python3","args":["-m","andp.mcp"],
 "cwd":"/path/to/your/project"}}}
```

---

## 5. Error taxonomy — how an agent reacts

Three regimes; branch on `error.retryable` and the state:

1. **Retryable** (`retryable:true`, state unchanged): rate limit (429),
   transient 5xx, build still ingesting. → poll again after `retry_after`.
2. **Non-terminal waiting** (state stays `prechecked`/`awaiting_approval`, a flag
   is set): `needs_precheck_fix` or `needs_approval`. → do the fix / open the gate,
   then poll. The release is **not** failed.
3. **Terminal failed** (`state:"failed"`, `retryable:false`): read
   `error.remediation`, fix the root cause, then `reset` and start over.

Common codes an agent should recognize:

| code | regime | remediation |
|---|---|---|
| `rate_limited` | retryable | wait `retry_after`, poll |
| `network_error` / 5xx | retryable | poll again |
| `version_not_editable` | terminal | bump the marketing version |
| `compliance_undeclared` | terminal | set `compliance` in andp.yml or IPA plist |
| `review_submission_conflict` | terminal | resolve the other open submission first |
| `price_point_not_found` | terminal | use an exact base-territory price, or `free` |
| `unknown_territory` | terminal | use ISO territory ids |
| `empty_territories` | terminal | list ≥1 territory (delist is UI-only) |
| `invalid_age_rating` | terminal | fix field name/value |
| `bad_config` | terminal | fix andp.yml / config file |
| `app_not_found` | terminal | create the app record in ASC |

Required App Store metadata that ANDP can't fully pre-validate is checked by Apple
*synchronously* at submit; its 409 detail is surfaced verbatim in `error.message`.

---

## 6. Metadata & media (the `publish` folder convention)

`deliver`-style tree; idempotent **per file** (a retry uploads only what's missing):
```
metadata/
  en-US/
    description.txt  whatsNew.txt  keywords.txt  promotionalText.txt
    supportUrl.txt   marketingUrl.txt
    screenshots/APP_IPHONE_67/*.png      # Apple display types, per device
    previews/APP_IPHONE_67/*.mp4
  fr-FR/ …
```
Push it standalone (`andp publish me.app 1.2 ./metadata`) or as part of ship
(`release start --ship --metadata ./metadata`). Empty files never overwrite a
field; empty locale dirs create no phantom localization.

---

## 7. Store configuration (pricing / territories / age rating)

Declarative in `andp.yml` `store:` (full reference: [StoreConfig.md](StoreConfig.md)).
Apply everything at once, or target one:
```bash
andp store apply me.your.app --json          # pricing + availability + age rating
andp store pricing me.your.app --price free
andp store availability me.your.app --territories USA,FRA   # or --all
andp store age-rating me.your.app --config fastlane/rating.json
```
Each result carries `changed: true|false` (`false` = already at desired state,
idempotent skip). `store apply` is best-effort: an independent, idempotent block
per setting, so a re-run heals a partially-applied state. Precheck adds advisory
warnings if price/territories/age rating look unset (never blocking).

---

## 8. The approval gate (the one destructive line)

The ship machine stops at `awaiting_approval` and **never** submits on its own. It
crosses only when one of these is true:
- `policy.allow_submit: true` in `andp.yml` (a repo pre-authorises CI/agents), **or**
- an out-of-band `andp release approve <id>` (recorded with a timestamp + plan
  hash; changing the plan re-closes the gate).

```bash
andp release poll <id> --json     # ... → awaiting_approval, needs_approval:true
andp release approve <id>         # human/operator opens the gate
andp release poll <id> --json     # ... → submitted → done
```
Honest threat model: for an **MCP-only** agent the gate (and the server refusing to
expose `submit` without policy) is a real barrier. A **shell-wielding** agent can
run `andp submit` or edit `andp.yml` itself — so effective enforcement is the
host's permission prompt on the command, not ANDP. ANDP's job is to make the
irreversible action explicit, annotated, gated, and audited.

---

## 9. Worked example — agent pseudo-code, repo → submitted

```python
# 1. Gate on provable credentials
v = verify("me.your.app")                       # MCP: verify / CLI: andp verify --json
if not v["ok"]:
    stop(f"cannot publish: {v}")                # fix credentials/app record first

# 2. Build + sign with your pipeline -> build/App.ipa (xcodebuild)

# 3. Configure the store desired-state (idempotent; safe to repeat)
store_apply("me.your.app")                      # price / territories / age rating from andp.yml

# 4. Start a resumable ship release (metadata pushed as part of it)
r = release_start("build/App.ipa", ship=True, group="Beta",
                  metadata_dir="./fastlane/metadata")
rid = r["release_id"]

# 5. Drive the machine to the gate
while True:
    s = release_poll(rid)
    if s.get("retry_after"):                    # processing — non-blocking wait
        sleep(s["retry_after"]); continue
    if s.get("needs_precheck_fix"):             # precheck flagged real problems
        fix(s["precheck_report"]); continue     # e.g. add screenshots, then poll
    if s.get("needs_approval"):
        break                                    # parked at the gate
    if s["terminal"]:
        break

# 6. Cross the gate deliberately (human, or policy.allow_submit pre-authorised)
if s.get("needs_approval"):
    release_approve(rid)                         # out-of-band, audited
    while not (s := release_poll(rid))["terminal"]:
        sleep(s.get("retry_after", 5))

assert s["state"] == "done", s.get("error")     # submitted to App Review
```

---

## 10. Safety rails an agent MUST respect

- **Never** flip `policy.allow_submit` to bypass a human unless explicitly told to.
- **Never** call `store_configure_availability` with a shrinking set without
  confirming — it delists territories (empty set is refused outright).
- Treat `submit` / crossing `awaiting_approval` as irreversible; confirm intent.
- Respect `retry_after`; do not hammer the API (there are real rate limits).
- Take the machine-readable field, not the human line. If `ok:false`, act on
  `error.code` + `remediation`, don't guess.
- Rehearse in DRY-RUN (placeholder creds) before touching a real account.

---

## 11. Quick troubleshooting

| Symptom | Likely cause → action |
|---|---|
| `verify` `ok:false`, `missing:[…]` | fill those fields in `secrets.yml` |
| stuck on `processing` | normal — Apple ingest; keep polling `retry_after` |
| `version_not_editable` | that version is published/in review → bump version |
| `compliance_undeclared` | set `compliance.uses_non_exempt_encryption` in andp.yml |
| parked at `awaiting_approval` | expected gate → `release approve` or set policy |
| `needs_precheck_fix` | read `precheck_report.checks` (missing screenshots/description) |
| `price_point_not_found` | price must match an exact base-territory point, or `free` |
| everything is DRY-RUN | credentials are placeholders → real `secrets.yml` |

See [Troubleshooting.md](Troubleshooting.md) for the long form.
