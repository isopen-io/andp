"""BuildsManager.latest_build_number — true numeric global max, full pagination."""
from conftest import FakeResponse, FakeSession, make_test_managers


# latest_build_number returns (best_int, skipped_count): skipped counts
# non-empty non-integer (dotted/alphanumeric) versions, so the caller can warn
# that its integer-only max may be incomplete. Empty/in-flight versions are not
# counted as skipped (nothing actionable).

def test_numeric_max_defeats_lexicographic():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [
        {"attributes": {"version": "9"}},
        {"attributes": {"version": "1000"}},
        {"attributes": {"version": "42"}},
    ], "links": {}}))
    assert make_test_managers(session).builds.latest_build_number("app-1") == (1000, 0)


def test_no_builds_is_zero():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [], "links": {}}))
    assert make_test_managers(session).builds.latest_build_number("app-1") == (0, 0)


def test_skips_non_integer_versions_and_counts_them():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [
        {"attributes": {"version": "1.2.3"}},   # dotted -> skipped, counted
        {"attributes": {"version": "1300"}},
        {"attributes": {}},                      # missing/in-flight -> not counted
    ], "links": {}}))
    assert make_test_managers(session).builds.latest_build_number("app-1") == (1300, 1)


def test_full_pagination():
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"attributes": {"version": "100"}}],
                           "links": {"next": "https://api/next"}}),
        FakeResponse(200, {"data": [{"attributes": {"version": "250"}}], "links": {}}),
    )
    assert make_test_managers(session).builds.latest_build_number("app-1") == (250, 0)
