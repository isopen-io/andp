"""Persistent state store: atomic writes, locking, corruption surfaced.

A release must survive crashes at any point; state on disk is the source of
truth an agent (or a human) can always inspect.
"""
import json
import os

import pytest

from andp.core.errors import AndpError
from andp.core.state import StateStore


@pytest.fixture
def store(tmp_path):
    return StateStore(str(tmp_path / ".andp" / "state"))


def test_save_and_load_roundtrip(store):
    store.save("rel-1", {"state": "created", "n": 1})
    assert store.load("rel-1") == {"state": "created", "n": 1}


def test_load_missing_returns_none(store):
    assert store.load("nope") is None


def test_list_ids_sorted(store):
    store.save("b", {"x": 1})
    store.save("a", {"x": 2})
    assert store.list_ids() == ["a", "b"]


def test_list_ids_empty_when_dir_missing(tmp_path):
    store = StateStore(str(tmp_path / "never-created"))
    assert store.list_ids() == []


def test_save_is_atomic_no_tmp_left_behind(store, tmp_path):
    store.save("rel-1", {"state": "created"})
    files = os.listdir(str(tmp_path / ".andp" / "state"))
    assert files == ["rel-1.json"]


def test_corrupted_state_surfaces_typed_error_not_silent_reset(store, tmp_path):
    store.save("rel-1", {"state": "created"})
    (tmp_path / ".andp" / "state" / "rel-1.json").write_text("{not json!!")

    with pytest.raises(AndpError) as excinfo:
        store.load("rel-1")
    assert excinfo.value.code == "state_corrupted"
    assert excinfo.value.retryable is False
    assert "rel-1" in excinfo.value.message


def test_lock_prevents_concurrent_access(store):
    with store.lock("rel-1"):
        with pytest.raises(AndpError) as excinfo:
            with store.lock("rel-1"):
                pass
    assert excinfo.value.code == "state_locked"
    assert excinfo.value.retryable is True


def test_lock_released_after_context(store):
    with store.lock("rel-1"):
        pass
    with store.lock("rel-1"):  # must not raise
        pass


def test_lock_released_even_on_exception(store):
    with pytest.raises(RuntimeError):
        with store.lock("rel-1"):
            raise RuntimeError("boom")
    with store.lock("rel-1"):
        pass


def test_stale_lock_from_dead_pid_is_broken(store, tmp_path):
    lock_path = tmp_path / ".andp" / "state" / "rel-1.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("999999999")  # certainly not a live pid

    with store.lock("rel-1"):  # must break the stale lock and proceed
        pass


def test_lock_with_unreadable_pid_is_treated_as_stale(store, tmp_path):
    lock_path = tmp_path / ".andp" / "state" / "rel-1.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("garbage")

    with store.lock("rel-1"):
        pass
