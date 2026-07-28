"""Local tooling layer — Xcode builds, simulators, devices.

Sibling of `andp/asc/`, and deliberately independent of it: building a binary
does not talk to Apple. Dependencies run one way only — this package imports
`andp.errors` and `andp.paths`, never `andp.asc` nor `andp.core`.

`targets` and `destination` are pure modules: they launch no process, so they
are testable without Xcode. `runner`, `simulator` and `device` take their
process launcher by injection, for the same reason.
"""
