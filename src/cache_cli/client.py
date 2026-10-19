from types import TracebackType
from typing import Self
from uuid import UUID

import httpx

from cache_service.schemas import PayloadCreate, PayloadCreated, PayloadRead


class CacheClientError(Exception):
    """The service could not be reached or rejected a request."""


class CacheClient:
    """Thin synchronous client for the caching service API."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=timeout)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._http.close()

    def create(self, payload: PayloadCreate) -> tuple[UUID, bool]:
        """Return the payload identifier and whether the server generated it just now."""
        response = self._request("POST", "/payload", json=payload.model_dump())
        return PayloadCreated.model_validate_json(response.content).id, response.status_code == 201

    def fetch(self, payload_id: UUID) -> str:
        response = self._request("GET", f"/payload/{payload_id}")
        return PayloadRead.model_validate_json(response.content).output

    def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        try:
            response = self._http.request(method, url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as error:
            raise CacheClientError(f"{method} {url} failed: {error}") from error
        if response.is_error:
            raise CacheClientError(
                f"{method} {url} failed with {response.status_code}: {response.text}"
            )
        return response
