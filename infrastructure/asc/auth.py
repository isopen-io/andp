"""JWT ES256 authentication for the App Store Connect API.

Apple requirements (https://developer.apple.com/documentation/appstoreconnectapi):
- header: alg=ES256, kid=<API key id>, typ=JWT
- claims: iss=<issuer id>, iat, exp (max 20 minutes ahead), aud="appstoreconnect-v1"
"""
import time

import jwt

AUDIENCE = "appstoreconnect-v1"
# Apple rejects tokens valid for more than 20 minutes; leave a safety margin.
TOKEN_LIFETIME_SECONDS = 19 * 60
# Regenerate slightly before real expiry so in-flight requests never carry a stale token.
REFRESH_MARGIN_SECONDS = 60


class ASCAuthError(Exception):
    """Raised when credentials are missing or the private key is unusable."""


class ASCAuth:
    def __init__(self, key_id, issuer_id, private_key, clock=time.time):
        if not key_id or not issuer_id or not private_key:
            raise ASCAuthError(
                "key_id, issuer_id and private_key are all required for App Store Connect auth"
            )
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.private_key = private_key
        self._clock = clock
        self._token = None
        self._expires_at = 0.0

    def token(self):
        now = self._clock()
        if self._token is None or now >= self._expires_at - REFRESH_MARGIN_SECONDS:
            self._token = self._generate(now)
            self._expires_at = now + TOKEN_LIFETIME_SECONDS
        return self._token

    def _generate(self, now):
        payload = {
            "iss": self.issuer_id,
            "iat": int(now),
            "exp": int(now) + TOKEN_LIFETIME_SECONDS,
            "aud": AUDIENCE,
        }
        headers = {"kid": self.key_id, "typ": "JWT"}
        try:
            return jwt.encode(payload, self.private_key, algorithm="ES256", headers=headers)
        except Exception as exc:
            raise ASCAuthError(f"Unable to sign App Store Connect JWT: {exc}") from exc
