"""Assemble the App Store Connect manager stack from an account's credentials.

Shared by every adapter (CLI, MCP service layer) so they all drive the same
auth -> client -> managers pipeline.
"""
from .agerating import AgeRatingManager
from .apps import AppsManager
from .appstore import AppStoreManager
from .assets import PreviewManager, ScreenshotManager
from .auth import ASCAuth
from .availability import AvailabilityManager
from .builds import BuildsManager
from .client import ASCClient
from .pricing import PricingManager
from .testflight import TestFlightManager


class Managers:
    def __init__(self, client):
        self.client = client
        self.apps = AppsManager(client)
        self.builds = BuildsManager(client)
        self.testflight = TestFlightManager(client)
        self.appstore = AppStoreManager(client)
        self.screenshots = ScreenshotManager(client)
        self.previews = PreviewManager(client)
        self.pricing = PricingManager(client)
        self.availability = AvailabilityManager(client)
        self.age_rating = AgeRatingManager(client)


def make_managers(account):
    auth = ASCAuth(
        key_id=account.key_id,
        issuer_id=account.issuer_id,
        private_key=account.key_content,
    )
    return Managers(ASCClient(auth))
