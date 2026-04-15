"""HTTP client for OData services with auth, retry, and rate limiting."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_BACKOFF = 1.0


class ODataClient:
    """Async HTTP client for OData services."""

    def __init__(
        self,
        base_url: str,
        auth: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._auth = auth or {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._client is None:
            headers = {"Accept": "application/json"}
            auth = None

            auth_type = self._auth.get("type", "none")

            if auth_type == "basic":
                auth = httpx.BasicAuth(
                    self._auth["user"], self._auth["password"]
                )
            elif auth_type == "bearer":
                headers["Authorization"] = f"Bearer {self._auth['token']}"
            elif auth_type == "oauth2":
                token = await self._fetch_oauth_token()
                headers["Authorization"] = f"Bearer {token}"

            self._client = httpx.AsyncClient(
                auth=auth,
                headers=headers,
                timeout=self.timeout,
                verify=True,
                follow_redirects=True,
            )
        return self._client

    async def _fetch_oauth_token(self) -> str:
        """Fetch an OAuth2 token using client credentials."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._auth["token_url"],
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._auth["client_id"],
                    "client_secret": self._auth["client_secret"],
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def fetch_metadata(self) -> str:
        """Fetch the $metadata document as XML text."""
        client = await self._get_client()
        url = f"{self.base_url}/$metadata"

        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.get(
                    url, headers={"Accept": "application/xml"}
                )
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                raise
            except httpx.TransportError:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                raise

        raise RuntimeError("Failed to fetch metadata after retries")

    async def get(self, url: str) -> dict[str, Any]:
        """GET request with retry."""
        return await self._request("GET", url)

    async def post(self, url: str, json: Any = None) -> dict[str, Any]:
        """POST request."""
        return await self._request("POST", url, json=json)

    async def patch(self, url: str, json: Any = None) -> dict[str, Any]:
        """PATCH request."""
        return await self._request("PATCH", url, json=json)

    async def delete(self, url: str) -> dict[str, Any]:
        """DELETE request."""
        return await self._request("DELETE", url)

    async def _request(
        self, method: str, url: str, json: Any = None
    ) -> dict[str, Any]:
        """Execute an HTTP request with retry logic."""
        client = await self._get_client()

        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.request(method, url, json=json)
                resp.raise_for_status()

                if resp.status_code == 204:
                    return {"status": "success", "code": 204}

                data = resp.json()
                # Unwrap OData V2 d.results pattern
                if isinstance(data, dict) and "d" in data:
                    inner = data["d"]
                    if isinstance(inner, dict) and "results" in inner:
                        return {"results": inner["results"]}
                    return inner
                # V4 value pattern
                if isinstance(data, dict) and "value" in data:
                    return {"results": data["value"]}
                return data

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429:
                    retry_after = int(
                        e.response.headers.get("Retry-After", "5")
                    )
                    logger.warning(
                        "Rate limited (429), waiting %ds", retry_after
                    )
                    await asyncio.sleep(retry_after)
                    continue
                if status >= 500 and attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                raise
            except httpx.TransportError:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                raise

        raise RuntimeError(f"{method} {url} failed after {MAX_RETRIES} retries")

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
