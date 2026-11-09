"""Minimal Kibana API client (Agent Builder, Workflows). Uses the same API key as Elasticsearch."""

from __future__ import annotations

from typing import Any

import httpx

from app.config.settings import Settings


class KibanaError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Kibana {status}: {message}")
        self.status = status


class KibanaClient:
    def __init__(
        self,
        settings: Settings,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.kibana_url:
            raise KibanaError(0, "KUBECOMPASS_KIBANA_URL is not set")
        base = settings.kibana_url.rstrip("/")
        if settings.kibana_space:
            base += f"/s/{settings.kibana_space}"
        headers = {"kbn-xsrf": "true", "Content-Type": "application/json"}
        if settings.es_api_key:
            headers["Authorization"] = f"ApiKey {settings.es_api_key.get_secret_value()}"
        self._http = httpx.Client(
            base_url=base, headers=headers, timeout=timeout, transport=transport
        )

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None, *, allow_404: bool = False
    ) -> dict[str, Any] | None:
        try:
            resp = self._http.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise KibanaError(0, f"cannot reach Kibana ({exc})") from exc
        if resp.status_code == 404 and allow_404:
            return None
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message", resp.text)
            except ValueError:
                detail = resp.text
            raise KibanaError(resp.status_code, str(detail)[:500])
        return resp.json() if resp.content else {}

    def close(self) -> None:
        self._http.close()
