"""The release machine: a resumable, crash-safe, single-effect-per-step engine
for driving a build from IPA to TestFlight distribution.

Design contract (see Documentation/Design/agentic-core.md):
- `step()` advances exactly one state and persists before returning; it never
  sleeps and performs at most one external mutation.
- Failure semantics: a *retryable* AndpError is raised and the state is left
  unchanged (the next step retries); a *non-retryable* failure transitions the
  machine to a terminal `failed` state (inspectable, no raise).
- Idempotency: the buildUploads attempt is written ahead of the effect
  (`upload_attempted`); on resume the machine never blindly re-uploads. Once a
  build is resolved its id is pinned in the state and never re-resolved.
"""
import re
import time

from ..asc.client import ASCAPIError
from .errors import AndpError, from_asc_error, from_unexpected
from .ipa import read_metadata, sha256

SCHEMA_VERSION = 1
TERMINAL = ("done", "failed")
_PROCESSING_RETRY_AFTER = 60
# ~2h at 60s/poll: Apple processing rarely exceeds this. Genuinely stuck
# releases are recovered with `release reset <id>`, not a short timeout.
_DEFAULT_POLL_BUDGET = 120


def release_id(account, bundle_id, version, build_number):
    raw = f"{account}-{bundle_id}-{version}-{build_number}"
    return re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").lower()


class ReleaseMachine:
    def __init__(self, store, managers, state, clock=time.time):
        self.store = store
        self.managers = managers
        self._state = state
        self._clock = clock

    # -- construction ------------------------------------------------------

    @staticmethod
    def _sha256(path):
        return sha256(path)

    @classmethod
    def load(cls, store, managers, release_id, clock=time.time):
        state = store.load(release_id)
        if state is None:
            return None
        return cls(store, managers, state, clock=clock)

    @classmethod
    def start(cls, store, managers, ipa_path, *, account="primary", group=None,
              clock=time.time, poll_budget=_DEFAULT_POLL_BUDGET, reset=False):
        bundle_id, version, build_number = read_metadata(ipa_path)
        if not bundle_id:
            raise AndpError(
                code="ipa_unreadable",
                message=f"Could not read CFBundleIdentifier from {ipa_path}",
                retryable=False,
                remediation=(
                    "Ensure the path points to a valid signed .ipa. To resume an "
                    "existing release without the file, use `release poll <id>`."
                ),
            )
        rid = release_id(account, bundle_id, version, build_number)

        # Load existing state BEFORE touching the file further, and honour reset.
        existing = None if reset else store.load(rid)
        if existing is not None:
            if existing.get("ipa_sha256") != sha256(ipa_path):
                raise AndpError(
                    code="ipa_changed",
                    message=(
                        f"Release {rid} was started with a different IPA "
                        "(checksum mismatch)."
                    ),
                    retryable=False,
                    remediation=(
                        "Bump the build number for the new binary, or reset the "
                        f"release: `release reset {rid}`"
                    ),
                )
            if existing.get("state") in TERMINAL:
                raise AndpError(
                    code="release_terminal",
                    message=(
                        f"Release {rid} is already {existing['state']}."
                    ),
                    retryable=False,
                    remediation=f"Start a new build number, or reset it: `release reset {rid}`",
                )
            return cls(store, managers, existing, clock=clock)
        digest = sha256(ipa_path)

        state = {
            "schema_version": SCHEMA_VERSION,
            "release_id": rid,
            "account": account,
            "bundle_id": bundle_id,
            "version": version,
            "build_number": build_number,
            "ipa_path": ipa_path,
            "ipa_sha256": digest,
            "state": "created",
            "want_group": group,
            "app_id": None,
            "upload_attempted": False,
            "upload_id": None,
            "build_id": None,
            "processing_state": None,
            "poll_count": 0,
            "poll_budget": poll_budget,
            "history": ["created"],
            "error": None,
        }
        store.save(rid, state)
        return cls(store, managers, state, clock=clock)

    # -- introspection -----------------------------------------------------

    @property
    def release_id(self):
        return self._state["release_id"]

    @property
    def state(self):
        return self._state["state"]

    def is_terminal(self):
        return self._state["state"] in TERMINAL

    def snapshot(self):
        return dict(self._state)

    # -- persistence -------------------------------------------------------

    def _save(self):
        self.store.save(self._state["release_id"], self._state)

    def _transition(self, new_state):
        self._state["state"] = new_state
        self._state.setdefault("history", []).append(new_state)
        self._state.pop("retry_after", None)

    def _fail(self, err):
        self._state["error"] = err.to_dict()
        self._transition("failed")

    # -- the step ----------------------------------------------------------

    def step(self):
        if self.is_terminal():
            return self.snapshot()
        with self.store.lock(self._state["release_id"]):
            # Reload under the lock so we act on the latest committed state, not
            # a snapshot taken before another driver advanced the release.
            fresh = self.store.load(self._state["release_id"])
            if fresh is not None:
                self._state = fresh
            if self.is_terminal():
                return self.snapshot()
            try:
                getattr(self, f"_do_{self._state['state']}")()
            except ASCAPIError as api_err:
                err = from_asc_error(api_err)
                if err.retryable:
                    raise err
                self._fail(err)
            except AndpError as err:
                if err.retryable:
                    raise
                self._fail(err)
            except Exception as exc:  # transport/filesystem/unexpected
                err = from_unexpected(exc)
                if err.retryable:
                    raise err
                self._fail(err)
            self._save()
        return self.snapshot()

    # -- states ------------------------------------------------------------

    def _do_created(self):
        app = self.managers.apps.find_app(self._state["bundle_id"])
        if app is None:
            self._fail(AndpError(
                code="app_not_found",
                message=(
                    f"App {self._state['bundle_id']} not found on account "
                    f"'{self._state['account']}'."
                ),
                retryable=False,
                remediation="Create the app record in the App Store Connect UI first.",
            ))
            return
        self._state["app_id"] = app["id"]
        self._transition("app_resolved")

    def _do_app_resolved(self):
        if not self._state["upload_attempted"]:
            # Reserve first. A retryable failure of the reservation leaves the
            # flag UNSET (nothing persisted) -> a clean retry, never a brick.
            reservation_id = self.managers.builds.reserve_upload(
                self._state["app_id"],
                self._state["version"],
                self._state["build_number"],
            )
            # Write-ahead: the reservation exists now, so record it before moving
            # any bytes. A later failure can distinguish "reserved" from "not".
            self._state["upload_id"] = reservation_id
            self._state["upload_attempted"] = True
            self._save()
            self.managers.builds.transfer_reserved(reservation_id, self._state["ipa_path"])
            self._transition("uploaded")
            return

        # Resumed after a reservation was made: never re-reserve, never blindly
        # re-transfer. If the build is visible, advance; otherwise report an
        # actionable, retryable state (it may still be ingesting).
        build = self.managers.builds.find_build(
            self._state["app_id"], self._state["build_number"],
        )
        if build is None:
            raise AndpError(
                code="upload_incomplete",
                message=(
                    "A build was reserved but is not visible yet — inconclusive; "
                    "refusing to re-upload."
                ),
                retryable=True,
                remediation=(
                    "The build may still be ingesting: poll again shortly. If it "
                    f"never appears, restart with `release reset {self._state['release_id']}`."
                ),
            )
        self._pin_build(build)
        if self._state["processing_state"] in ("FAILED", "INVALID"):
            self._fail(self._processing_failed())
            return
        self._transition("uploaded")

    def _do_uploaded(self):
        self._state["poll_count"] = 0
        self._transition("processing")

    def _do_processing(self):
        build = self.managers.builds.find_build(
            self._state["app_id"], self._state["build_number"],
        )
        if build is None:
            self._tick_or_timeout()
            return
        self._pin_build(build)
        pstate = self._state["processing_state"]
        if pstate == "VALID":
            self._transition("valid")
        elif pstate in ("FAILED", "INVALID"):
            self._fail(self._processing_failed())
        else:
            self._tick_or_timeout()

    def _do_valid(self):
        if self._state["want_group"]:
            group = self.managers.testflight.ensure_group(
                self._state["app_id"], self._state["want_group"]
            )
            try:
                self.managers.testflight.add_build_to_group(
                    group["id"], self._state["build_id"]
                )
            except ASCAPIError as exc:
                if exc.status != 409:  # already-in-group is fine on resume
                    raise
            self._state["group_id"] = group["id"]
            self._transition("group_linked")
        else:
            self._transition("done")

    def _do_group_linked(self):
        self._transition("done")

    # -- helpers -----------------------------------------------------------

    def _pin_build(self, build):
        self._state["build_id"] = build["id"]
        self._state["processing_state"] = build.get("attributes", {}).get("processingState")

    def _tick_or_timeout(self):
        self._state["poll_count"] += 1
        if self._state["poll_count"] >= self._state["poll_budget"]:
            self._fail(AndpError(
                code="processing_timeout",
                message=(
                    f"Build {self._state['build_number']} did not finish "
                    f"processing within {self._state['poll_budget']} polls."
                ),
                retryable=False,
                remediation="Check the build's status in App Store Connect.",
            ))
        else:
            self._state["processing_state"] = "PROCESSING"
            self._state["retry_after"] = _PROCESSING_RETRY_AFTER

    def _processing_failed(self):
        return AndpError(
            code="processing_failed",
            message=(
                f"Build {self._state['build_number']} ended in state "
                f"{self._state['processing_state']}."
            ),
            retryable=False,
            remediation="Inspect the build in App Store Connect; fix and re-upload.",
        )
