# Contributing to ANDP

Thanks for considering a contribution. ANDP is an API-first Apple delivery
platform; correctness against the **real** App Store Connect API is its core
value, so contributions follow a few strict rules.

## Ground rules

1. **TDD is not optional.** Every behavior change lands with a test that
   failed first. The suite (`python3 -m pytest tests/`) must stay green.
2. **Encode the observed API contract.** When the live API behaves differently
   from Apple's documentation (it happens — see the mandatory `app`
   relationship or `assetType: ASSET` in `builds.py`), the mock in the tests
   must encode the *observed* behavior, with a comment citing the observation
   date.
3. **DRY-RUN stays honest.** Commands without real credentials must not touch
   the network and must exit 0 — except `verify`, whose contract is to fail
   when publishing is impossible.
4. **Never weaken secrets handling.** No credentials in code, tests, fixtures
   or CI files. Test fixtures use placeholder ids and deliberately truncated,
   non-functional PEM fragments.

## Development setup

```bash
pip install -e . pytest
python3 -m pytest tests/          # 80+ tests, sub-second
./infrastructure/tests/run_tests.sh   # full pipeline suite (needs macOS for some steps)
```

## Pull requests

- One logical change per PR, with the reasoning in the description.
- Update `CHANGELOG.md` under the unreleased section.
- CI (`ANDP Pipeline`) must pass; it runs the full pipeline against the
  example app in `examples/meeshy/`.

## Repository layout

See the README's "Repository layout" section. Rule of thumb: Python that talks
to App Store Connect lives in `andp/asc/`; pipeline orchestration lives in
shell scripts at the root and in `infrastructure/`.
