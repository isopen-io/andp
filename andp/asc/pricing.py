"""App pricing via the modern App Store Connect API.

The legacy appPriceTier system is gone: a price is an *appPriceSchedule* whose
manualPrice for the base territory references an *appPricePoint*; prices in other
territories auto-derive from it. Setting a schedule REPLACES the previous one.
"""
from decimal import Decimal, InvalidOperation


def _price_eq(a, b):
    """Money equality — Decimal, never float (0.1-style drift)."""
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError, TypeError):
        return str(a) == str(b)


class PricingManager:
    def __init__(self, client):
        self.client = client

    def get_schedule(self, app_id):
        """The app's current appPriceSchedule, or None."""
        return (self.client.get(f"/v1/apps/{app_id}/appPriceSchedule") or {}).get("data")

    def list_price_points(self, app_id, territory):
        """Every appPricePoint available for a territory (paginated — B2)."""
        return self.client.get_all(
            f"/v1/apps/{app_id}/appPricePoints",
            params={"filter[territory]": territory},
        )

    def find_price_point(self, app_id, territory, customer_price):
        """The price point whose customerPrice equals customer_price, or None."""
        for pt in self.list_price_points(app_id, territory):
            if _price_eq(pt.get("attributes", {}).get("customerPrice"), customer_price):
                return pt
        return None

    def find_free_price_point(self, app_id, territory):
        """The $0.00 (free) price point for a territory, or None."""
        return self.find_price_point(app_id, territory, "0")

    def current_base_price_point_id(self, app_id, base_territory, today=None):
        """The appPricePoint id of the price live NOW in the base territory.

        Live means startDate is null (immediate) OR in the past; among the live
        base-territory prices the latest-starting one wins (S3). Future-scheduled
        prices are ignored. Returns None with no schedule or no live base price
        (so the caller re-applies — safe)."""
        if self.get_schedule(app_id) is None:
            return None
        if today is None:
            import datetime
            today = datetime.date.today().isoformat()
        response = self.client.get(
            f"/v1/apps/{app_id}/appPriceSchedule/manualPrices",
            params={"include": "appPricePoint"},
        ) or {}
        prices = response.get("data", []) or []
        included = {inc["id"]: inc for inc in response.get("included", []) or []}
        best = None  # (effective_start, price_point_id) for the base territory
        for price in prices:
            start = price.get("attributes", {}).get("startDate")
            effective = start or ""       # null => "" => sorts before any real date
            if effective > today:
                continue                  # future-scheduled, not live yet
            pp = ((price.get("relationships") or {}).get("appPricePoint") or {}).get("data") or {}
            pp_id = pp.get("id")
            point = included.get(pp_id, {})
            terr = (((point.get("relationships") or {}).get("territory") or {}).get("data") or {}).get("id")
            if terr == base_territory and (best is None or effective >= best[0]):
                best = (effective, pp_id)
        return best[1] if best else None

    def set_schedule(self, app_id, base_territory, price_point_id, start_date=None):
        """Set (replace) the app's price schedule from a base-territory price point.

        start_date=None => the price goes live immediately."""
        temp = "${price0}"
        payload = {
            "data": {
                "type": "appPriceSchedules",
                "relationships": {
                    "app": {"data": {"type": "apps", "id": app_id}},
                    "baseTerritory": {"data": {"type": "territories", "id": base_territory}},
                    "manualPrices": {"data": [{"type": "appPrices", "id": temp}]},
                },
            },
            "included": [
                {
                    "type": "appPrices",
                    "id": temp,
                    "attributes": {"startDate": start_date},
                    "relationships": {
                        "appPricePoint": {
                            "data": {"type": "appPricePoints", "id": price_point_id}
                        }
                    },
                }
            ],
        }
        return (self.client.post("/v1/appPriceSchedules", payload) or {}).get("data")
