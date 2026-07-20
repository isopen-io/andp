"""HTTP client for the App Store Connect API (JSON:API over HTTPS).

Handles Bearer-token injection, JSON:API error surfacing, cursor pagination
(links.next) and 429 rate-limit retries with Retry-After support.
"""
import time

import requests

BASE_URL = "https://api.appstoreconnect.apple.com"
MAX_RATE_LIMIT_RETRIES = 3
DEFAULT_RETRY_AFTER_SECONDS = 30.0


class ASCAPIError(Exception):
    def __init__(self, status, errors):
        self.status = status
        self.errors = errors or []
        details = "; ".join(
            e.get("detail") or e.get("title") or e.get("code") or "unknown error"
            for e in self.errors
        ) or "no error details"
        super().__init__(f"App Store Connect API error {status}: {details}")


class ASCClient:
    def __init__(self, auth, session=None, base_url=BASE_URL, sleep=time.sleep):
        self.auth = auth
        self.session = session or requests.Session()
        self.base_url = base_url
        self._sleep = sleep

    # -- verbs ---------------------------------------------------------------

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def post(self, path, payload):
        return self._request("POST", path, json=payload)

    def patch(self, path, payload):
        return self._request("PATCH", path, json=payload)

    def delete(self, path, payload=None):
        kwargs = {"json": payload} if payload is not None else {}
        return self._request("DELETE", path, **kwargs)

    def get_all(self, path, params=None):
        """Follow links.next until exhausted; return the concatenated data list."""
        items = []
        response = self.get(path, params=params)
        while True:
            items.extend(response.get("data", []))
            next_url = (response.get("links") or {}).get("next")
            if not next_url:
                return items
            response = self._request("GET", next_url)

    # -- internals -----------------------------------------------------------

    def _request(self, method, path, **kwargs):
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            headers["Authorization"] = f"Bearer {self.auth.token()}"
            if "json" in kwargs:
                headers["Content-Type"] = "application/json"
            response = self.session.request(method, url, headers=headers, **kwargs)

            if response.status_code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                retry_after = float(
                    response.headers.get("Retry-After", DEFAULT_RETRY_AFTER_SECONDS)
                )
                self._sleep(retry_after)
                continue
            return self._parse(response)
        raise AssertionError("unreachable")

    @staticmethod
    def _parse(response):
        if response.status_code == 204 or not response.content:
            if response.status_code >= 400:
                raise ASCAPIError(response.status_code, [])
            return None
        body = response.json()
        if response.status_code >= 400:
            raise ASCAPIError(response.status_code, body.get("errors", []))
        return body
