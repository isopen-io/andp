"""Assemble the App Store Connect manager stack from an account's credentials.

Shared by every adapter (CLI, MCP service layer) so they all drive the same
auth -> client -> managers pipeline.
"""
from .apps import AppsManager
from .appstore import AppStoreManager
from .auth import ASCAuth
from .builds import BuildsManager
from .client import ASCClient
from .testflight import TestFlightManager


class Managers:
    def __init__(self, client):
        self.client = client
        self.apps = AppsManager(client)
        self.builds = BuildsManager(client)
        self.testflight = TestFlightManager(client)
        self.appstore = AppStoreManager(client)


def make_managers(account):
    auth = ASCAuth(
        key_id=account.key_id,
        issuer_id=account.issuer_id,
        private_key=account.key_content,
    )
    return Managers(ASCClient(auth))
