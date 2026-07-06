import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ASC_DIR = os.path.join(REPO_ROOT, "infrastructure", "asc")

for path in (ASC_DIR, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(scope="session")
def ec_private_key_pem():
    """A throwaway P-256 key, same curve as App Store Connect API keys."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture(scope="session")
def ec_public_key_pem(ec_private_key_pem):
    from cryptography.hazmat.primitives import serialization

    private_key = serialization.load_pem_private_key(ec_private_key_pem.encode(), password=None)
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, content=None):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}
        if content is None:
            # Une vraie réponse requests a un corps non vide dès qu'il y a du JSON.
            content = b"{}" if json_data is not None else b""
        self.content = content
        self.text = "" if json_data is None else str(json_data)

    def json(self):
        if self._json is None:
            raise ValueError("No JSON body")
        return self._json


class FakeSession:
    """Records every request and replays canned responses in order."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.requests = []

    def queue(self, *responses):
        self.responses.extend(responses)

    def request(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError(f"Unexpected request: {method} {url}")
        return self.responses.pop(0)


@pytest.fixture
def fake_session():
    return FakeSession()


@pytest.fixture
def asc_client(fake_session):
    """Un vrai ASCClient branché sur un transport factice."""
    from client import ASCClient

    class _StubAuth:
        def token(self):
            return "stub-jwt"

    return ASCClient(auth=_StubAuth(), session=fake_session, sleep=lambda s: None)


@pytest.fixture
def fake_response():
    return FakeResponse
