"""ConfigError appartient à la taxonomie typée — un agent lit un seul type d'erreur."""
import pytest

from andp.errors import AndpError, ConfigError


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


def test_config_module_still_exports_config_error():
    """Les 4 sites qui font `from .config import ConfigError` ne cassent pas."""
    from andp.asc.config import ConfigError as Reexported
    assert Reexported is ConfigError
