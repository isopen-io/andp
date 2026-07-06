"""Tests for infrastructure/asc/auth.py — JWT ES256 pour l'App Store Connect API.

Contraintes Apple : header kid + alg ES256, claims iss/iat/exp/aud,
durée de vie maximale de 20 minutes, aud = "appstoreconnect-v1".
"""
import time

import jwt as pyjwt
import pytest

from auth import ASCAuth, ASCAuthError

KEY_ID = "TESTKEY123"
ISSUER_ID = "69a6de70-0000-47e3-e053-5b8c7c11a4d1"


def _decode(token, public_pem):
    return pyjwt.decode(token, public_pem, algorithms=["ES256"], audience="appstoreconnect-v1")


def test_token_is_signed_es256_with_kid_header(ec_private_key_pem, ec_public_key_pem):
    auth = ASCAuth(key_id=KEY_ID, issuer_id=ISSUER_ID, private_key=ec_private_key_pem)
    token = auth.token()

    header = pyjwt.get_unverified_header(token)
    assert header["alg"] == "ES256"
    assert header["kid"] == KEY_ID
    assert header["typ"] == "JWT"

    claims = _decode(token, ec_public_key_pem)
    assert claims["iss"] == ISSUER_ID
    assert claims["aud"] == "appstoreconnect-v1"


def test_token_lifetime_is_at_most_20_minutes(ec_private_key_pem, ec_public_key_pem):
    auth = ASCAuth(key_id=KEY_ID, issuer_id=ISSUER_ID, private_key=ec_private_key_pem)
    claims = _decode(auth.token(), ec_public_key_pem)

    assert claims["exp"] - claims["iat"] <= 20 * 60
    assert claims["exp"] > time.time()


def test_token_is_cached_while_valid(ec_private_key_pem):
    auth = ASCAuth(key_id=KEY_ID, issuer_id=ISSUER_ID, private_key=ec_private_key_pem)
    assert auth.token() == auth.token()


def test_token_is_regenerated_after_expiry(ec_private_key_pem):
    fake_now = [1_000_000.0]
    auth = ASCAuth(
        key_id=KEY_ID,
        issuer_id=ISSUER_ID,
        private_key=ec_private_key_pem,
        clock=lambda: fake_now[0],
    )
    first = auth.token()
    fake_now[0] += 21 * 60  # au-delà de la durée de vie max
    second = auth.token()
    assert first != second


def test_invalid_private_key_raises_auth_error():
    with pytest.raises(ASCAuthError):
        ASCAuth(key_id=KEY_ID, issuer_id=ISSUER_ID, private_key="not-a-pem-key").token()


def test_missing_credentials_raise_auth_error(ec_private_key_pem):
    with pytest.raises(ASCAuthError):
        ASCAuth(key_id="", issuer_id=ISSUER_ID, private_key=ec_private_key_pem)
    with pytest.raises(ASCAuthError):
        ASCAuth(key_id=KEY_ID, issuer_id="", private_key=ec_private_key_pem)
    with pytest.raises(ASCAuthError):
        ASCAuth(key_id=KEY_ID, issuer_id=ISSUER_ID, private_key="")
