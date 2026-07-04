from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.clickup.com/api/v2"


class ClickUpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"ClickUp API error {status}: {message}")
        self.status = status
        self.message = message


class ClickUpClient:
    def __init__(self, token: str | None = None, *, timeout: float = 30.0) -> None:
        self.token = token or os.environ.get("CLICKUP_TOKEN")
        if not self.token:
            raise ClickUpError(0, "CLICKUP_TOKEN not set (env var or .env file)")
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": self.token, "Content-Type": "application/json"},
            timeout=timeout,
        )

    def get(
        self,
        path: str,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    ) -> Any:
        resp = self._client.get(path, params=params)
        if resp.status_code >= 400:
            raise ClickUpError(resp.status_code, resp.text)
        return resp.json()

    def put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    ) -> Any:
        resp = self._client.put(path, json=json, params=params)
        if resp.status_code >= 400:
            raise ClickUpError(resp.status_code, resp.text)
        return resp.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ClickUpClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
