"""Persistent, crash-safe state for releases.

- Atomic writes (tmp + os.replace): a crash can never half-write state.
- Pid-based lock files with stale-lock takeover: two concurrent drivers of
  the same release fail fast (state_locked, retryable) instead of racing.
- Corruption is surfaced as a typed error, never silently reset.
"""
import contextlib
import errno
import json
import os

from .errors import AndpError


class StateStore:
    def __init__(self, directory):
        self.directory = directory

    # -- persistence -------------------------------------------------------

    def _path(self, release_id):
        return os.path.join(self.directory, f"{release_id}.json")

    def save(self, release_id, data):
        os.makedirs(self.directory, exist_ok=True)
        path = self._path(release_id)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)

    def load(self, release_id):
        path = self._path(release_id)
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            raw = f.read()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AndpError(
                code="state_corrupted",
                message=f"State file for '{release_id}' is not valid JSON: {exc}",
                retryable=False,
                remediation=(
                    f"Inspect {path}; restore it from a backup or delete it to "
                    "restart the release from scratch."
                ),
            )

    def list_ids(self):
        if not os.path.isdir(self.directory):
            return []
        return sorted(
            name[:-5] for name in os.listdir(self.directory)
            if name.endswith(".json")
        )

    # -- locking -----------------------------------------------------------

    def _lock_path(self, release_id):
        return os.path.join(self.directory, f"{release_id}.lock")

    @staticmethod
    def _pid_alive(pid):
        try:
            os.kill(pid, 0)
        except (OSError, OverflowError):
            return False
        return True

    def _try_acquire(self, lock_path):
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def lock(self, release_id):
        os.makedirs(self.directory, exist_ok=True)
        lock_path = self._lock_path(release_id)
        try:
            self._try_acquire(lock_path)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
            # Existing lock: stale (dead/garbled pid) -> break it; live -> fail fast.
            try:
                pid = int(open(lock_path).read().strip())
            except (ValueError, OSError):
                pid = None
            if pid is not None and self._pid_alive(pid):
                raise AndpError(
                    code="state_locked",
                    message=(
                        f"Release '{release_id}' is being driven by another "
                        f"process (pid {pid})."
                    ),
                    retryable=True,
                    remediation="Wait for the other process, then retry.",
                )
            os.unlink(lock_path)
            self._try_acquire(lock_path)
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                os.unlink(lock_path)
