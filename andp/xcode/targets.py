"""Build-target resolution — a pure module, it launches no process.

Auto-detection needs the project's scheme list; that arrives by injection
(`scheme_lister`), which is what keeps this module testable without Xcode.
"""
import os
from collections import namedtuple

import yaml

from .. import paths
from ..errors import XcodeError

Target = namedtuple("Target", "name scheme platform destination configuration os")

PLATFORMS = ("iOS", "iPadOS", "watchOS", "tvOS", "macOS", "visionOS")
FIELDS = ("scheme", "platform", "destination", "configuration", "os")
DEFAULTS = {"scheme": None, "platform": "iOS", "destination": "generic",
            "configuration": "Debug", "os": None}
ENV_APP_DIR = "ANDP_APP_DIR"
_DEFAULTS_KEY = "defaults"


def _load_yaml(project_root):
    """andp.yml as a mapping — a typed error, never a raw YAMLError.

    Every reader in this module funnels through here, so one guard covers them
    all. A parse error escaping raw reaches the CLI as a traceback with nothing
    on stdout, which breaks the {ok, error} envelope an agent parses.
    """
    path = paths.policy_path(project_root)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as handle:
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        try:
            document = yaml.load(handle, Loader=loader) or {}
        except yaml.YAMLError as exc:
            raise XcodeError(
                "andp.yml is not valid YAML: %s" % exc,
                code="bad_config",
                remediation="Fix the YAML syntax in andp.yml.",
                context={"policy": path})
    if not isinstance(document, dict):
        raise XcodeError(
            "andp.yml must be a mapping, not a %s." % type(document).__name__,
            code="bad_config",
            remediation="Its top level holds keys: project:, targets:, store:",
            context={"policy": path, "found": type(document).__name__})
    return document


def load_targets(project_root="."):
    """The `targets:` block of andp.yml, minus `defaults`. {} when absent."""
    block = _load_yaml(project_root).get("targets")
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise XcodeError(
            "The `targets:` block of andp.yml must be a mapping of targets.",
            code="bad_target_config",
            remediation="targets:\n  my-target:\n    platform: iOS")
    # Names are normalised to strings because YAML reads an unquoted `26:` as an
    # integer. Left alone, `andp targets` would print a name that `andp build`
    # then rejects, and sorting a mix of both raises a bare TypeError.
    return dict((str(k), v) for k, v in block.items() if k != _DEFAULTS_KEY)


def project_dir(project_root="."):
    """Where the Xcode project lives: $ANDP_APP_DIR, then project.dir, then root.

    $ANDP_APP_DIR comes first because build.sh and test.sh already honoured it —
    the cascade extends what exists rather than competing with it.
    """
    from_env = os.environ.get(ENV_APP_DIR)
    if from_env:
        return from_env
    block = _load_yaml(project_root).get("project")
    if block is not None and not isinstance(block, dict):
        raise XcodeError(
            "The `project:` block of andp.yml must be a mapping.",
            code="bad_config",
            remediation="project:\n  dir: apps/ios",
            context={"policy": paths.policy_path(project_root),
                     "found": type(block).__name__})
    declared = (block or {}).get("dir")
    if declared:
        return os.path.join(project_root, declared)
    return project_root


def ensure_project(directory, project_root="."):
    """Fail once, up front, when there is no Xcode project to build.

    Without this, every target in the matrix launches xcodebuild only to
    rediscover the same absence — five identical failures instead of one
    actionable error naming the directory that was resolved and why.
    """
    if os.path.isdir(directory):
        for entry in os.listdir(directory):
            if entry.endswith((".xcodeproj", ".xcworkspace")):
                return directory
    raise XcodeError(
        "No Xcode project or workspace in `%s`." % directory,
        code="no_project",
        remediation=("Set $%s, or `project.dir` in andp.yml, to the directory "
                     "holding the .xcodeproj — and generate it if needed "
                     "(xcodegen)." % ENV_APP_DIR),
        context={"project_dir": directory,
                 "env": os.environ.get(ENV_APP_DIR),
                 "policy": paths.policy_path(project_root)})


def _validate(name, spec):
    """Reject unknown fields outright.

    A warning would let a misspelled target silently compile the wrong thing —
    same reasoning as the age-rating typo guard (Documentation/StoreConfig.md).
    """
    if not isinstance(spec, dict):
        raise XcodeError(
            "Target `%s` must be a mapping of fields." % name,
            code="bad_target_config",
            remediation="Allowed fields: %s." % ", ".join(FIELDS),
            context={"target": name, "allowed": list(FIELDS)})
    for key in spec:
        if key not in FIELDS:
            raise XcodeError(
                "Unknown field `%s` in target `%s`." % (key, name),
                code="bad_target_config",
                remediation="Allowed fields: %s." % ", ".join(FIELDS),
                context={"target": name, "unknown": key, "allowed": list(FIELDS)})
    platform = spec.get("platform")
    if platform is not None and platform not in PLATFORMS:
        raise XcodeError(
            "Unknown platform `%s` in target `%s`." % (platform, name),
            code="bad_target_config",
            remediation="Allowed platforms: %s." % ", ".join(PLATFORMS),
            context={"target": name, "unknown": platform,
                     "allowed": list(PLATFORMS)})


def _validate_overrides(overrides):
    """Command-line overrides bypass andp.yml, and so bypassed its validation.

    Without this, `--platform Android` travelled all the way to xcodebuild as
    `platform=Android Simulator`: the failure then names a destination, never
    the flag that was mistyped.
    """
    platform = (overrides or {}).get("platform")
    if platform is not None and platform not in PLATFORMS:
        raise XcodeError(
            "Unknown platform `%s` passed with --platform." % platform,
            code="bad_target_config",
            remediation="Allowed platforms: %s." % ", ".join(PLATFORMS),
            context={"flag": "--platform", "unknown": platform,
                     "allowed": list(PLATFORMS)})


def _build(name, spec, defaults, overrides):
    _validate_overrides(overrides)
    merged = dict(DEFAULTS)
    merged.update(dict((k, v) for k, v in defaults.items() if v is not None))
    merged.update(dict((k, v) for k, v in spec.items() if v is not None))
    # argparse leaves unpassed flags at None: filter them out, or an absent flag
    # would erase what andp.yml declares.
    merged.update(dict((k, v) for k, v in (overrides or {}).items()
                       if v is not None and k in FIELDS))
    return Target(name=name, **merged)


def _autodetect(project_root, scheme_lister, overrides):
    # An explicit --scheme decides alone. Checked before the listing, not after:
    # scheme_lister launches xcodebuild, and the answer would be discarded.
    if overrides and overrides.get("scheme"):
        return _build("default", {"scheme": overrides["scheme"]}, {}, overrides)
    if scheme_lister is None:
        from .runner import list_schemes as scheme_lister
    schemes = scheme_lister(project_dir(project_root))
    if len(schemes) == 1:
        return _build("default", {"scheme": schemes[0]}, {}, overrides)
    # Refusing is not enough: hand back the YAML to paste.
    raise XcodeError(
        "Several schemes in the project and no `targets:` block in andp.yml.",
        code="ambiguous_scheme",
        remediation=("Declare your targets:\n\ntargets:\n  defaults:\n"
                     "    scheme: %s\n  dev:\n    platform: iOS\n"
                     % (schemes[0] if schemes else "MyScheme")),
        context={"schemes": list(schemes)})


def resolve(name=None, project_root=".", scheme_lister=None, overrides=None):
    """Target `name`, or the project's only target. Raises otherwise."""
    raw = _load_yaml(project_root).get("targets") or {}
    defaults = raw.get(_DEFAULTS_KEY) or {} if isinstance(raw, dict) else {}
    declared = load_targets(project_root)

    if name is None:
        if len(declared) == 1:
            name = list(declared.keys())[0]
        elif not declared:
            return _autodetect(project_root, scheme_lister, overrides)
        else:
            raise XcodeError(
                "Several targets declared: name one, or pass --all.",
                code="ambiguous_target",
                remediation="andp build %s" % " | ".join(sorted(declared)),
                context={"available": sorted(declared)})

    if name not in declared:
        raise XcodeError(
            "Unknown target: %s." % name,
            code="target_not_found",
            remediation="Declared targets: %s." % (", ".join(sorted(declared))
                                                   or "none"),
            context={"requested": name, "available": sorted(declared)})

    _validate(_DEFAULTS_KEY, defaults)
    _validate(name, declared[name])
    return _build(name, declared[name], defaults, overrides)


def resolve_all(project_root=".", scheme_lister=None, overrides=None):
    """Every declared target, or the auto-detected one when none is declared."""
    declared = load_targets(project_root)
    if not declared:
        return [resolve(None, project_root, scheme_lister, overrides)]
    return [resolve(n, project_root, scheme_lister, overrides)
            for n in sorted(declared)]
