import json
from uuid import uuid4

import httpx
import pytest

from cache_cli.client import CacheClient, CacheClientError
from cache_cli.schemas import PayloadCreate

PAYLOAD = PayloadCreate(list_1=["a"], list_2=["b"])


def make_client(handler: httpx.MockTransport) -> CacheClient:
    return CacheClient("http://api", transport=handler)


def test_create_posts_payload_and_reports_whether_it_was_new() -> None:
    payload_id = uuid4()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"id": str(payload_id), "message": "Payload created"})

    with make_client(httpx.MockTransport(handler)) as client:
        assert client.create(PAYLOAD) == (payload_id, True)

    assert seen[0].method == "POST"
    assert seen[0].url == "http://api/payload"
    assert json.loads(seen[0].content) == {"list_1": ["a"], "list_2": ["b"]}


def test_create_reports_existing_payload() -> None:
    payload_id = uuid4()
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"id": str(payload_id), "message": "exists"})
    )

    with make_client(transport) as client:
        assert client.create(PAYLOAD) == (payload_id, False)


def test_fetch_returns_output() -> None:
    payload_id = uuid4()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"output": "A, B"}))

    with make_client(transport) as client:
        assert client.fetch(payload_id) == "A, B"


def test_http_errors_are_reported_with_server_detail() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(404, json={"detail": "Payload not found"})
    )

    with make_client(transport) as client, pytest.raises(CacheClientError, match=r"404.*not found"):
        client.fetch(uuid4())


def test_connection_failures_are_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with (
        make_client(httpx.MockTransport(handler)) as client,
        pytest.raises(CacheClientError, match="connection refused"),
    ):
        client.create(PAYLOAD)
