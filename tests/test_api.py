import requests
import pytest
from fastapi.testclient import TestClient
from ecomflow.clients.api import APIClient, APIError, AuthenticationError
from mock_platform.app import create_app


class Transport:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def response(status=200, text="{}", headers=None):
    r = requests.Response()
    r.status_code = status
    r._content = text.encode()
    r.headers.update(headers or {})
    return r


@pytest.mark.parametrize("status", [429, 500])
def test_transient_retry(status):
    session = Transport(
        [response(status, headers={"Retry-After": "1"}), response(200, '{"ok":true}')]
    )
    delays = []
    api = APIClient("http://localhost", session=session, sleep=delays.append)
    assert api.get("/orders")["ok"]
    assert session.calls == 2 and delays == [1.0]


def test_401():
    session = Transport([response(401)])
    with pytest.raises(AuthenticationError):
        APIClient("http://localhost", session=session).get("/")
    assert session.calls == 1


def test_timeout():
    session = Transport([requests.Timeout("slow")] * 3)
    with pytest.raises(APIError):
        APIClient("http://localhost", session=session, sleep=lambda _: None).get("/")
    assert session.calls == 3


def test_invalid_json():
    with pytest.raises(APIError, match="Invalid JSON"):
        APIClient("http://localhost", session=Transport([response(200, "bad")])).get(
            "/"
        )


def test_unsafe_post_not_retried():
    session = Transport([response(500)])
    with pytest.raises(APIError):
        APIClient("http://localhost", session=session).post("/")
    assert session.calls == 1


def test_mock_faults():
    with TestClient(create_app()) as client:
        assert client.get("/health").json()["status"] == "ok"
        for kind in ["401", "429", "500", "invalid_json", "duplicate"]:
            client.post("/control/platform_a/fault", json={"kind": kind})
            r = client.get("/platform_a/orders")
            if kind == "invalid_json":
                with pytest.raises(ValueError):
                    r.json()
            else:
                assert r.status_code == (
                    {"duplicate": 409}.get(kind, int(kind) if kind.isdigit() else 0)
                )
            assert client.get("/platform_a/orders").status_code == 200
