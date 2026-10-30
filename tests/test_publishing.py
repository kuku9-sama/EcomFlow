from decimal import Decimal
from ecomflow.adapters.platforms import PlatformAAdapter, PlatformBAdapter
from ecomflow.core.models import Product
from ecomflow.database.store import Store
from ecomflow.ingestion.products import import_products
from ecomflow.services.publishing import publish_products
from ecomflow.clients.api import APIError


class Client:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def post(self, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise APIError("HTTP 500")
        return {"success": True, "id": "listing"}


def test_mapping():
    p = Product(sku="X", title="Title", price=Decimal("1.23"), currency="USD", stock=1)
    assert PlatformAAdapter(None).payload(p)["price"] == "1.23"
    assert PlatformBAdapter(None).payload(p)["amount"] == {
        "value": "1.23",
        "currency": "USD",
    }
    assert "sku" not in PlatformBAdapter(None).payload(p)


def test_publish_and_deduplicate(tmp_path):
    store = Store(str(tmp_path / "db"))
    import_products(store, "data/sample_products.csv", str(tmp_path))
    client = Client()
    adapter = PlatformAAdapter(client)
    assert publish_products(store, adapter)["success"] == 2
    assert publish_products(store, adapter)["success"] == 2
    assert client.calls == 2


def test_publish_failure_and_recovery(tmp_path):
    store = Store(str(tmp_path / "db"))
    import_products(store, "data/sample_products.csv", str(tmp_path))
    client = Client(True)
    adapter = PlatformAAdapter(client)
    assert publish_products(store, adapter)["failed"] == 2
    assert all(r["error"] for r in store.rows("SELECT * FROM platform_listings"))
    client.fail = False
    assert publish_products(store, adapter)["success"] == 2
    assert all(
        r["attempts"] == 2 for r in store.rows("SELECT * FROM platform_listings")
    )
