"""ConfigError appartient à la taxonomie typée — un agent lit un seul type d'erreur."""
import pytest

from andp.errors import AndpError, ConfigError, XcodeError


def test_config_error_is_an_andp_error():
    err = ConfigError("boom", code="config_misplaced", remediation="fix it")
    assert isinstance(err, AndpError)
    assert err.code == "config_misplaced"
    assert err.remediation == "fix it"


def test_config_error_is_never_retryable():
    assert ConfigError("boom").to_dict()["retryable"] is False


def test_config_error_defaults_to_generic_code():
    assert ConfigError("boom").code == "config_error"


def test_context_is_absent_when_empty():
    assert "context" not in ConfigError("boom").to_dict()


def test_context_is_carried_into_the_envelope():
    err = ConfigError("boom", context={"searched": ["a", "b"]})
    assert err.to_dict()["context"] == {"searched": ["a", "b"]}


def test_caught_by_the_generic_handler():
    """C'est ce qui rend la traduction de service.py inutile."""
    with pytest.raises(AndpError):
        raise ConfigError("boom")


def test_andp_error_carries_context():
    err = AndpError(code="build_failed", message="boom", retryable=False,
                    remediation="lis le log", context={"errors": ["a.swift:1"]})
    assert err.to_dict()["context"] == {"errors": ["a.swift:1"]}


def test_andp_error_omits_empty_context():
    err = AndpError(code="x", message="m", retryable=False, remediation="")
    assert "context" not in err.to_dict()


def test_xcode_error_is_an_andp_error():
    err = XcodeError("boom", code="build_failed", context={"log": "/tmp/a.log"})
    assert isinstance(err, AndpError)
    assert err.retryable is False
    assert err.to_dict()["context"] == {"log": "/tmp/a.log"}


def test_xcode_error_can_be_retryable():
    """Seul le boot de simulateur l'est — mais le type doit le permettre."""
    assert XcodeError("boot", code="simulator_boot_failed",
                      retryable=True).to_dict()["retryable"] is True


def test_config_module_still_exports_config_error():
    """Les 4 sites qui font `from .config import ConfigError` ne cassent pas."""
    from andp.asc.config import ConfigError as Reexported
    assert Reexported is ConfigError
