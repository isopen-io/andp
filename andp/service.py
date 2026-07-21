"""Service layer: the library both the CLI and the MCP server call.

Pure functions returning dicts — no printing, no sys.exit. This is what makes
the MCP server library-first: it drives the release machine directly instead
of scraping a CLI's stdout.
"""
import os
import time

from .asc.config import load_account
from .asc.managers import make_managers
from .core.errors import AndpError
from .core.ipa import read_metadata
from .core.release import ReleaseMachine, release_id
from .core.state import StateStore

STATE_DIR = os.path.join(".andp", "state")


def _store(project_root="."):
    return StateStore(os.path.join(project_root, STATE_DIR))


def _managers_for(account_id):
    """Return (managers, account, dry_run). managers is None in dry-run.
    Raises AndpError (not ConfigError) so callers have one error type to catch."""
    from .asc.config import ConfigError
    try:
        account = load_account(account_id)
    except ConfigError as exc:
        raise AndpError(code="config_error", message=str(exc), retryable=False,
                        remediation="Check secrets.yml and the --account name.")
    if not account.is_configured():
        return None, account, True
    return make_managers(account), account, False


def _snapshot_view(snap):
    """The agent-facing projection of a machine snapshot."""
    view = {
        "release_id": snap["release_id"],
        "state": snap["state"],
        "terminal": snap["state"] in ("done", "failed"),
        "bundle_id": snap["bundle_id"],
        "version": snap["version"],
        "build_number": snap["build_number"],
    }
    if snap.get("app_id"):
        view["app_id"] = snap["app_id"]
    if snap.get("build_id"):
        view["build"] = {"id": snap["build_id"],
                         "processing_state": snap.get("processing_state")}
    if snap.get("retry_after"):
        view["retry_after"] = snap["retry_after"]
    if snap.get("needs_approval"):
        # A human (or policy.allow_submit) must open the gate before the release
        # can proceed — signal it explicitly so an agent stops polling blindly.
        view["needs_approval"] = True
        view["next_action"] = "release approve <id> (or set policy.allow_submit)"
    if snap.get("needs_precheck_fix"):
        view["needs_precheck_fix"] = True
        view["precheck_report"] = snap.get("precheck_report")
        view["next_action"] = "fix the precheck errors (andp publish / ASC UI), then poll again"
    elif (snap.get("precheck_report") or {}).get("warnings"):
        # Precheck passed but flagged advisory warnings — surface them so the
        # agent/human sees them even on the happy path.
        view["precheck_warnings"] = snap["precheck_report"]["warnings"]
    if snap.get("submission_id"):
        view["submission_id"] = snap["submission_id"]
    if snap.get("error"):
        view["error"] = snap["error"]
    return view


def release_start(ipa_path, account="primary", group=None, ship=False,
                  metadata_dir=None, skip_precheck=False,
                  project_root=".", clock=time.time, reset=False):
    if not os.path.exists(ipa_path):
        return {"command": "release_start", "ok": False,
                "error": {"code": "ipa_not_found", "message": f"IPA not found: {ipa_path}",
                          "retryable": False, "remediation": "Build the IPA first."}}

    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("release_start", err)
    bundle_id, version, build_number = read_metadata(ipa_path)

    if dry_run:
        rid = release_id(account, bundle_id, version, build_number)
        plan = ["app_record", "upload", "processing"]
        if group:
            plan.append("testflight_group")
        if ship:
            plan += ["version", "build_attached", "compliance"]
            if metadata_dir:
                plan.append("metadata")
            plan.append("submit")
        return {"command": "release_start", "ok": True, "dry_run": True,
                "release_id": rid, "bundle_id": bundle_id, "plan": plan}

    policy = _load_policy(project_root)
    try:
        machine = ReleaseMachine.start(
            _store(project_root), managers, ipa_path,
            account=account, group=group, ship=ship, metadata_dir=metadata_dir,
            skip_precheck=skip_precheck,
            allow_submit=policy["allow_submit"],
            uses_non_exempt_encryption=policy["uses_non_exempt_encryption"],
            clock=clock, reset=reset,
        )
    except AndpError as err:
        return {"command": "release_start", "ok": False, "dry_run": False,
                "error": err.to_dict()}

    return {"command": "release_start", "ok": True, "dry_run": False,
            "release_id": machine.release_id, "state": machine.state, "next": "poll"}


def _load_policy(project_root):
    from .policy import load_policy
    return load_policy(os.path.join(project_root, "andp.yml"))


def publish(bundle_id, version, metadata_dir, account="primary"):
    """Push release notes + screenshots + previews from a folder to a version."""
    from .publish import publish_metadata
    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("publish", err)
    if not os.path.isdir(metadata_dir):
        return {"command": "publish", "ok": False,
                "error": {"code": "not_found", "message": f"No metadata dir: {metadata_dir}",
                          "retryable": False, "remediation": "Create the folder tree."}}
    if dry_run:
        return {"command": "publish", "ok": True, "dry_run": True,
                "bundle_id": bundle_id, "version": version, "metadata_dir": metadata_dir}
    from .asc.client import ASCAPIError
    from .core.errors import from_asc_error, from_unexpected
    try:
        app = managers.apps.find_app(bundle_id)
        if app is None:
            return {"command": "publish", "ok": False,
                    "error": {"code": "app_not_found", "message": f"App {bundle_id} not found.",
                              "retryable": False, "remediation": "Create the app record in ASC."}}
        summary = publish_metadata(managers, app["id"], version, metadata_dir)
    except AndpError as err:
        return _error_result("publish", err)
    except ASCAPIError as err:
        return _error_result("publish", from_asc_error(err))
    except Exception as err:  # network / filesystem — always return a dict
        return _error_result("publish", from_unexpected(err))
    return {"command": "publish", "ok": True, "dry_run": False, **summary}


def _retryable_status(status):
    """A 429 or any 5xx is transient — the call can be retried unchanged."""
    return status == 429 or (isinstance(status, int) and 500 <= status < 600)


def verify_checks(account, managers, bundle_id=None):
    """Pure verify preflight core. Returns the verify envelope; never prints,
    never raises. `managers` is None in dry-run (placeholder credentials).

    Envelope: {command, ok, checks:[{name,ok,detail,missing?,retryable?}], app?}.
    Both the CLI (`_cmd_verify`) and the readiness gates drive this — the human
    rendering lives in the CLI, the shape is pinned by tests."""
    from .asc.auth import ASCAuthError
    from .asc.client import ASCAPIError

    checks = []
    missing = account.missing_fields()
    if missing:
        checks.append({"name": "credentials", "ok": False,
                       "detail": "missing or placeholder fields", "missing": missing})
        return {"command": "verify", "ok": False, "checks": checks}
    checks.append({"name": "credentials", "ok": True,
                   "detail": (f"credentials — key_id {account.key_id}, issuer_id set, "
                              "private key present")})

    try:
        managers.client.auth.token()
    except ASCAuthError as exc:
        checks.append({"name": "jwt", "ok": False, "detail": f"JWT signing failed: {exc}"})
        return {"command": "verify", "ok": False, "checks": checks}
    checks.append({"name": "jwt", "ok": True, "detail": "JWT signed (ES256)"})

    app_payload = None
    try:
        if bundle_id:
            app = managers.apps.find_app(bundle_id)
            checks.append({"name": "api_auth", "ok": True,
                           "detail": "API authentication accepted"})
            if app is None:
                checks.append({"name": "app_record", "ok": False,
                               "detail": (f"app '{bundle_id}' not found on this "
                                          "App Store Connect account")})
                return {"command": "verify", "ok": False, "checks": checks}
            name = (app.get("attributes") or {}).get("name", "?")
            app_payload = {"id": app["id"], "name": name, "bundle_id": bundle_id}
            checks.append({"name": "app_record", "ok": True,
                           "detail": f"app found: {name} ({bundle_id}) — id {app['id']}"})
        else:
            managers.client.get("/v1/apps", params={"limit": 1})
            checks.append({"name": "api_auth", "ok": True,
                           "detail": "API authentication accepted (GET /v1/apps)"})
    except ASCAPIError as exc:
        checks.append({"name": "api_auth", "ok": False,
                       "detail": f"API rejected the request: {exc}",
                       "retryable": _retryable_status(getattr(exc, "status", None))})
        return {"command": "verify", "ok": False, "checks": checks}
    except Exception as exc:  # network / unexpected — classify, never crash
        from .core.errors import from_unexpected
        checks.append({"name": "api_auth", "ok": False,
                       "detail": f"could not reach App Store Connect: {exc}",
                       "retryable": from_unexpected(exc).retryable})
        return {"command": "verify", "ok": False, "checks": checks}

    result = {"command": "verify", "ok": True, "checks": checks}
    if app_payload:
        result["app"] = app_payload
    return result


def verify(bundle_id=None, account="primary"):
    """Publish preflight as a library call (loader over `verify_checks`).

    Returns the verify envelope. A config/secrets problem is surfaced as a failed
    `credentials` check so a caller (e.g. readiness) can classify it as
    'unverified' rather than crashing."""
    try:
        managers, account_cfg, _dry_run = _managers_for(account)
    except AndpError as err:
        return {"command": "verify", "ok": False,
                "checks": [{"name": "credentials", "ok": False,
                            "detail": err.message, "missing": ["config"]}]}
    return verify_checks(account_cfg, managers, bundle_id)


def readiness_testflight(bundle_id, account="primary"):
    """Can this app be delivered to TestFlight? (credentials + app record)."""
    from .readiness import testflight_verdict
    return testflight_verdict(verify(bundle_id, account=account), bundle_id=bundle_id)


def readiness_appstore(bundle_id, version, account="primary"):
    """Can this version be submitted to the App Store? (editable + build + metadata)."""
    from .readiness import appstore_verdict
    return appstore_verdict(precheck(bundle_id, version, account=account),
                            bundle_id=bundle_id, version=version)


def build_number(strategy, bundle_id=None, floor=0, fmt=None, sha=None,
                 digits=7, account="primary", clock=None):
    """Compute the next iOS build number (CFBundleVersion) via a strategy:

      fastlane  = max(floor, latest ASC build) + 1  (monotonic; needs creds)
      timestamp = utc-now, formatted                (monotonic; no creds)
      commit    = int(git short sha, 16)            (unique, NOT monotonic; no creds)

    Returns a typed envelope; never raises. Only `fastlane` touches App Store
    Connect — `timestamp`/`commit` run with zero credentials."""
    from .buildnum import commit_build, timestamp_build

    # Coerce here too (not just in the CLI) so an MCP/library caller passing
    # floor/digits as a JSON string or float gets an envelope, never an exception.
    try:
        floor = int(floor)
        digits = int(digits)
    except (TypeError, ValueError):
        return _error_result("build_number", AndpError(
            code="bad_input", message="floor and digits must be integers",
            retryable=False, remediation="Pass integer floor and digits."))

    if strategy == "timestamp":
        try:
            value, monotonic = timestamp_build(clock=clock, fmt=fmt)
        except ValueError as exc:
            return _error_result("build_number", AndpError(
                code="bad_input", message=str(exc), retryable=False,
                remediation="Use a digit-only --format of <= 18 chars."))
        return {"command": "build_number", "ok": True, "strategy": "timestamp",
                "build_number": value, "monotonic": monotonic}

    if strategy == "commit":
        if sha is None:
            sha = os.environ.get("GITHUB_SHA")
        try:
            value = commit_build(sha, digits=digits)
        except ValueError as exc:
            return _error_result("build_number", AndpError(
                code="bad_input", message=str(exc), retryable=False,
                remediation="Pass a hex --sha or set $GITHUB_SHA."))
        return {"command": "build_number", "ok": True, "strategy": "commit",
                "build_number": value, "monotonic": False}

    if strategy == "fastlane":
        if not bundle_id:
            return _error_result("build_number", AndpError(
                code="bad_input", message="the fastlane strategy needs a bundle_id",
                retryable=False, remediation="Pass the app bundle id."))
        from .asc.client import ASCAPIError
        from .core.errors import from_asc_error, from_unexpected
        try:
            managers, _account_cfg, dry_run = _managers_for(account)
        except AndpError as err:
            return _error_result("build_number", err)
        if dry_run:
            return {"command": "build_number", "ok": False,
                    "error": {"code": "no_credentials",
                              "message": "The fastlane strategy needs real credentials to query App Store Connect.",
                              "retryable": False,
                              "remediation": "Fill in secrets.yml, or use --strategy timestamp/commit."}}
        try:
            app = managers.apps.find_app(bundle_id)
            if app is None:
                return {"command": "build_number", "ok": False,
                        "error": {"code": "app_not_found",
                                  "message": f"App {bundle_id} not found.",
                                  "retryable": False,
                                  "remediation": "Create the app record in ASC."}}
            latest, skipped = managers.builds.latest_build_number(app["id"])
        except ASCAPIError as err:
            return _error_result("build_number", from_asc_error(err))
        except Exception as err:
            return _error_result("build_number", from_unexpected(err))
        value = max(floor, latest) + 1
        result = {"command": "build_number", "ok": True, "strategy": "fastlane",
                  "build_number": str(value), "monotonic": True,
                  "source": {"floor": floor, "latest_asc": latest, "skipped": skipped}}
        if skipped:
            result["warning"] = (
                f"{skipped} build(s) on App Store Connect have non-integer "
                "versions and were ignored — the fastlane strategy assumes "
                "integer build numbers; the computed number may be too low. "
                "Verify, or pass --floor.")
        return result

    return _error_result("build_number", AndpError(
        code="bad_strategy", message=f"unknown build-number strategy '{strategy}'",
        retryable=False, remediation="Use fastlane, timestamp or commit."))


def precheck(bundle_id, version, account="primary"):
    """Read-only pre-submission validation. Never mutates."""
    from .precheck import run_precheck
    from .asc.client import ASCAPIError
    from .core.errors import from_asc_error, from_unexpected
    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("precheck", err)
    if dry_run:
        return {"command": "precheck", "ok": False,
                "error": {"code": "no_credentials",
                          "message": "Precheck needs real credentials.",
                          "retryable": False, "remediation": "Fill in secrets.yml."}}
    try:
        app = managers.apps.find_app(bundle_id)
        if app is None:
            return {"command": "precheck", "ok": False,
                    "error": {"code": "app_not_found", "message": f"App {bundle_id} not found.",
                              "retryable": False, "remediation": "Create the app record in ASC."}}
        version_res = managers.appstore.find_version(app["id"], version)
        if version_res is None:
            return {"command": "precheck", "ok": False,
                    "error": {"code": "version_not_found",
                              "message": f"No version {version} for {bundle_id}.",
                              "retryable": False,
                              "remediation": "Create the version in App Store Connect first."}}
        report = run_precheck(managers, app["id"], version_res["id"])
    except ASCAPIError as err:
        return _error_result("precheck", from_asc_error(err))
    except Exception as err:
        return _error_result("precheck", from_unexpected(err))
    return {"command": "precheck", **report}


_FREE_TOKENS = {"free", "0", "0.0", "0.00", "0.000"}


def _is_free(price):
    if price is None:
        return False
    token = str(price).strip().lower()
    if token in _FREE_TOKENS:
        return True
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(token) == 0
    except (InvalidOperation, ValueError):
        return False


def _read_store(project_root, section=None):
    """Read store config from andp.yml, converting a malformed file into an
    AndpError (never a raw YAMLError leaking out of the {ok,error} envelope)."""
    import yaml
    try:
        store = _load_policy(project_root)["store"]
    except yaml.YAMLError as exc:
        raise AndpError(code="bad_config", message=f"andp.yml is not valid YAML: {exc}",
                        retryable=False, remediation="Fix the YAML syntax in andp.yml.")
    if section is None:
        return store
    return store.get(section) or {}


def configure_pricing(bundle_id, account="primary", base_territory=None, price=None,
                      price_point_id=None, project_root="."):
    """Set the app's price (or make it free) via the modern appPriceSchedules.

    Reconciles to a desired price: idempotent (changed=false when already set),
    dry-run aware, all API errors wrapped."""
    try:
        managers, _account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("configure_pricing", err)

    try:
        cfg = _read_store(project_root, "pricing")
    except AndpError as err:
        return _error_result("configure_pricing", err)
    base_territory = base_territory or cfg.get("base_territory") or "USA"
    if price is None:
        price = cfg.get("price")
    price_point_id = price_point_id or cfg.get("price_point_id")
    if price is None and price_point_id is None:
        return {"command": "configure_pricing", "ok": False,
                "error": {"code": "not_configured",
                          "message": "No price or price_point_id configured.",
                          "retryable": False,
                          "remediation": "Set store.pricing.price in andp.yml or pass --price."}}

    if dry_run:
        return {"command": "configure_pricing", "ok": True, "dry_run": True,
                "changed": None, "base_territory": base_territory,
                "price": price, "price_point_id": price_point_id}

    from .asc.client import ASCAPIError
    from .core.errors import from_asc_error, from_unexpected
    try:
        app = managers.apps.find_app(bundle_id)
        if app is None:
            return _app_not_found("configure_pricing", bundle_id)
        app_id = app["id"]

        if price_point_id is None:
            point = (managers.pricing.find_free_price_point(app_id, base_territory)
                     if _is_free(price)
                     else managers.pricing.find_price_point(app_id, base_territory, price))
            if point is None:
                return {"command": "configure_pricing", "ok": False,
                        "error": {"code": "price_point_not_found",
                                  "message": f"No price point for {price!r} in {base_territory}.",
                                  "retryable": False,
                                  "remediation": "Use an exact base-territory customerPrice, "
                                                 "or 'free'."}}
            price_point_id = point["id"]

        if managers.pricing.current_base_price_point_id(app_id, base_territory) == price_point_id:
            return {"command": "configure_pricing", "ok": True, "dry_run": False,
                    "changed": False, "base_territory": base_territory,
                    "price_point_id": price_point_id, "detail": "already set"}

        managers.pricing.set_schedule(app_id, base_territory, price_point_id)
    except AndpError as err:
        return _error_result("configure_pricing", err)
    except ASCAPIError as err:
        return _error_result("configure_pricing", from_asc_error(err))
    except Exception as err:
        return _error_result("configure_pricing", from_unexpected(err))
    return {"command": "configure_pricing", "ok": True, "dry_run": False,
            "changed": True, "base_territory": base_territory,
            "price_point_id": price_point_id}


def configure_availability(bundle_id, account="primary", territories=None,
                           available_in_new_territories=None, project_root="."):
    """Set (replace) the territories the app is available in — exceeds deliver.

    Refuses an empty set (would delist). Preserves availableInNewTerritories when
    unspecified. Idempotent, dry-run aware, errors wrapped."""
    try:
        managers, _account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("configure_availability", err)

    try:
        cfg = _read_store(project_root, "availability")
    except AndpError as err:
        return _error_result("configure_availability", err)
    if territories is None:
        territories = cfg.get("territories")
    if available_in_new_territories is None:
        available_in_new_territories = cfg.get("available_in_new_territories")
    if territories is None:
        return {"command": "configure_availability", "ok": False,
                "error": {"code": "not_configured",
                          "message": "No territories configured.",
                          "retryable": False,
                          "remediation": "Set store.availability.territories in andp.yml "
                                         "or pass --territories/--all."}}

    if dry_run:
        return {"command": "configure_availability", "ok": True, "dry_run": True,
                "changed": None, "territories": territories,
                "available_in_new_territories": available_in_new_territories}

    from .asc.client import ASCAPIError
    from .core.errors import from_asc_error, from_unexpected
    try:
        app = managers.apps.find_app(bundle_id)
        if app is None:
            return _app_not_found("configure_availability", bundle_id)
        app_id = app["id"]

        all_territories = managers.availability.list_all_territories()
        if _is_all(territories):
            target = set(all_territories)
        else:
            target = {str(t).strip().upper() for t in territories}
            unknown = target - all_territories
            if unknown:
                sample = ", ".join(sorted(all_territories)[:8])
                return {"command": "configure_availability", "ok": False,
                        "error": {"code": "unknown_territory",
                                  "message": f"Unknown territory codes: {sorted(unknown)}.",
                                  "retryable": False,
                                  "remediation": f"Use ISO territory ids (e.g. {sample}…)."}}
        if not target:
            return {"command": "configure_availability", "ok": False,
                    "error": {"code": "empty_territories",
                              "message": "Refusing to set zero territories (would delist the app).",
                              "retryable": False,
                              "remediation": "List at least one territory, or delist in the ASC UI."}}

        snapshot = managers.availability.availability_snapshot(app_id)
        if available_in_new_territories is None:
            available_in_new_territories = bool(
                snapshot["available_in_new_territories"]) if snapshot else False
        else:
            available_in_new_territories = bool(available_in_new_territories)

        if (snapshot and snapshot["territories"] == target
                and snapshot["available_in_new_territories"] == available_in_new_territories):
            return {"command": "configure_availability", "ok": True, "dry_run": False,
                    "changed": False, "territory_count": len(target),
                    "available_in_new_territories": available_in_new_territories,
                    "detail": "already set"}

        managers.availability.set_availability(app_id, target, available_in_new_territories)
    except AndpError as err:
        return _error_result("configure_availability", err)
    except ASCAPIError as err:
        return _error_result("configure_availability", from_asc_error(err))
    except Exception as err:
        return _error_result("configure_availability", from_unexpected(err))
    return {"command": "configure_availability", "ok": True, "dry_run": False,
            "changed": True, "territory_count": len(target),
            "available_in_new_territories": available_in_new_territories}


def configure_age_rating(bundle_id, account="primary", declaration=None, project_root="."):
    """Set the app's age rating declaration (2025 model). PATCHes only the keys
    that differ from the live declaration; validates the taxonomy first."""
    from .asc.agerating import validate_declaration
    try:
        managers, _account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("configure_age_rating", err)

    if declaration is None:
        try:
            declaration = _read_store(project_root, "age_rating")
        except AndpError as err:
            return _error_result("configure_age_rating", err)
    try:
        config = _resolve_age_rating_config(declaration, project_root)
    except (OSError, ValueError) as err:
        return {"command": "configure_age_rating", "ok": False,
                "error": {"code": "bad_config",
                          "message": f"Cannot read age rating config: {err}",
                          "retryable": False, "remediation": "Fix the config_path file."}}
    if not config:
        return {"command": "configure_age_rating", "ok": False,
                "error": {"code": "not_configured",
                          "message": "No age rating declaration configured.",
                          "retryable": False,
                          "remediation": "Set store.age_rating in andp.yml or pass a config."}}

    attributes, errors, warnings = validate_declaration(config)
    if errors:
        return {"command": "configure_age_rating", "ok": False,
                "error": {"code": "invalid_age_rating", "message": "; ".join(errors),
                          "retryable": False,
                          "remediation": "Fix the age rating field names/values."}}

    if dry_run:
        return {"command": "configure_age_rating", "ok": True, "dry_run": True,
                "changed": None, "fields": sorted(attributes), "warnings": warnings}

    from .asc.client import ASCAPIError
    from .core.errors import from_asc_error, from_unexpected
    try:
        app = managers.apps.find_app(bundle_id)
        if app is None:
            return _app_not_found("configure_age_rating", bundle_id)
        declaration_res = managers.age_rating.get_declaration(app["id"])
        if declaration_res is None:
            return {"command": "configure_age_rating", "ok": False,
                    "error": {"code": "no_declaration",
                              "message": "No editable age rating declaration found.",
                              "retryable": False,
                              "remediation": "Ensure the app has an editable version/appInfo."}}
        current = declaration_res.get("attributes", {}) or {}
        diff = {k: v for k, v in attributes.items() if current.get(k) != v}
        if not diff:
            return {"command": "configure_age_rating", "ok": True, "dry_run": False,
                    "changed": False, "warnings": warnings, "detail": "already set"}
        managers.age_rating.update_declaration(declaration_res["id"], diff)
    except AndpError as err:
        return _error_result("configure_age_rating", err)
    except ASCAPIError as err:
        return _error_result("configure_age_rating", from_asc_error(err))
    except Exception as err:
        return _error_result("configure_age_rating", from_unexpected(err))
    return {"command": "configure_age_rating", "ok": True, "dry_run": False,
            "changed": True, "updated_fields": sorted(diff), "warnings": warnings}


def configure_store(bundle_id, account="primary", project_root="."):
    """Apply every configured store block (pricing/availability/age_rating) from
    andp.yml. Best-effort: independent, idempotent blocks; a re-run heals a
    partially-applied state. ok=false if any configured block failed."""
    try:
        store = _read_store(project_root)
    except AndpError as err:
        return _error_result("configure_store", err)
    blocks, any_fail, dry_run = {}, False, None
    plan = [
        ("pricing", lambda: configure_pricing(bundle_id, account, project_root=project_root)),
        ("availability", lambda: configure_availability(bundle_id, account, project_root=project_root)),
        ("age_rating", lambda: configure_age_rating(bundle_id, account, project_root=project_root)),
    ]
    for name, run in plan:
        if not store.get(name):
            blocks[name] = {"skipped": "not configured"}
            continue
        try:
            result = run()
        except Exception as exc:  # a block must never abort the others (S4 best-effort)
            from .core.errors import from_unexpected
            result = _error_result(f"configure_{name}", from_unexpected(exc))
        blocks[name] = result
        if result.get("dry_run"):
            dry_run = True
        if not result.get("ok"):
            any_fail = True
    return {"command": "configure_store", "ok": not any_fail, "dry_run": bool(dry_run),
            "blocks": blocks}


def _is_all(territories):
    if isinstance(territories, str):
        return territories.strip().lower() == "all"
    if isinstance(territories, (list, tuple, set)) and len(territories) == 1:
        return str(next(iter(territories))).strip().lower() == "all"
    return False


def _resolve_age_rating_config(declaration, project_root):
    """Merge a config_path JSON file (if any) with inline keys (inline wins)."""
    cfg = dict(declaration or {})
    path = cfg.pop("config_path", None)
    merged = {}
    if path:
        import json
        full = path if os.path.isabs(path) else os.path.join(project_root, path)
        with open(full, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError(
                f"age rating config must be a JSON object, got {type(loaded).__name__}")
        merged.update(loaded)
    merged.update(cfg)
    return merged


def _app_not_found(command, bundle_id):
    return {"command": command, "ok": False,
            "error": {"code": "app_not_found", "message": f"App {bundle_id} not found.",
                      "retryable": False, "remediation": "Create the app record in ASC."}}


def release_approve(release_id_arg, account="primary", project_root=".", clock=time.time):
    """Record an out-of-band human approval opening the submit gate."""
    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("release_approve", err)
    try:
        machine = ReleaseMachine.load(
            _store(project_root), managers if not dry_run else None,
            release_id_arg, clock=clock)
    except AndpError as err:
        return _error_result("release_approve", err)
    if machine is None:
        return {"command": "release_approve", "ok": False,
                "error": {"code": "not_found", "message": f"No release '{release_id_arg}'.",
                          "retryable": False, "remediation": "Check the id with release_list."}}
    snap = machine.approve()
    view = _snapshot_view(snap)
    view.update({"command": "release_approve", "ok": True})
    return view


def _error_result(command, err):
    payload = err.to_dict() if isinstance(err, AndpError) else {
        "code": "internal_error", "message": str(err), "retryable": False,
        "remediation": "Unexpected error.",
    }
    return {"command": command, "ok": False, "error": payload}


def release_poll(release_id_arg, account="primary", project_root=".", clock=time.time):
    try:
        managers, account_cfg, dry_run = _managers_for(account)
    except AndpError as err:
        return _error_result("release_poll", err)
    if dry_run:
        return {"command": "release_poll", "ok": False,
                "error": {"code": "no_credentials",
                          "message": "Polling a real release requires credentials.",
                          "retryable": False,
                          "remediation": "Fill in secrets.yml (see andp verify)."}}

    # Inject a LIVE policy read so revoking allow_submit in andp.yml stops an
    # in-flight release at the gate (rather than honouring a stale start value).
    allow_submit_fn = lambda: _load_policy(project_root)["allow_submit"]
    try:
        machine = ReleaseMachine.load(_store(project_root), managers, release_id_arg,
                                      clock=clock, allow_submit_fn=allow_submit_fn)
    except AndpError as err:
        return _error_result("release_poll", err)
    if machine is None:
        return {"command": "release_poll", "ok": False,
                "error": {"code": "not_found",
                          "message": f"No release '{release_id_arg}'.",
                          "retryable": False,
                          "remediation": "Start it first with release_start, or check the id."}}

    try:
        snap = machine.step()
    except AndpError as err:
        view = _snapshot_view(machine.snapshot())
        view.update({"command": "release_poll", "ok": False, "error": err.to_dict()})
        return view

    view = _snapshot_view(snap)
    ok = snap["state"] != "failed"
    view.update({"command": "release_poll", "ok": ok})
    return view


def release_status(release_id_arg, project_root="."):
    try:
        snap = _store(project_root).load(release_id_arg)
    except AndpError as err:
        return _error_result("release_status", err)
    if snap is None:
        return {"command": "release_status", "ok": False,
                "error": {"code": "not_found",
                          "message": f"No release '{release_id_arg}'.",
                          "retryable": False,
                          "remediation": "Check the id with release_list."}}
    view = _snapshot_view(snap)
    view.update({"command": "release_status", "ok": True})
    return view


def release_list(project_root="."):
    store = _store(project_root)
    releases = []
    for rid in store.list_ids():
        try:
            snap = store.load(rid)
        except AndpError as err:
            # One corrupted release must not hide all the others.
            releases.append({"release_id": rid, "state": "unreadable",
                             "error": err.to_dict()})
            continue
        if snap:
            releases.append(_snapshot_view(snap))
    return {"command": "release_list", "ok": True, "releases": releases}


def release_reset(ipa_path, account="primary", group=None, project_root=".",
                  clock=time.time):
    """Discard a terminal/stuck release's state and start it over."""
    result = release_start(ipa_path, account=account, group=group,
                           project_root=project_root, clock=clock)
    return result


def release_reset_by_id(release_id_arg, project_root="."):
    """Delete a release's state file by id (recovery escape hatch)."""
    import os
    path = os.path.join(project_root, STATE_DIR, f"{release_id_arg}.json")
    if os.path.exists(path):
        os.remove(path)
        return {"command": "release_reset", "ok": True, "release_id": release_id_arg,
                "detail": "state discarded"}
    return {"command": "release_reset", "ok": False,
            "error": {"code": "not_found", "message": f"No release '{release_id_arg}'.",
                      "retryable": False, "remediation": "Check the id with release_list."}}
