"""Thin aiohttp client for the iZone ASH bridge local API.

V2 (documented): POST /iZoneRequestV2 {"iZoneV2Request":{"Type":x,"No":y,"No1":z}}
                 POST /iZoneCommandV2 {command object}
V1 (legacy):     POST /<CommandName> {command object}   e.g. POST /ZoneCommand
                 GET  /<resource>

Some firmware wants Content-Type: application/json, some rejects it. We probe
both and cache the polarity per bridge host.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

V2_ERROR_BACKOFF = 0.15
REQUEST_TIMEOUT = 12.0


def decode_device_body(raw: bytes) -> str:
    """Prefer UTF-8; some bridges embed 0xFF filler (e.g. LockCode)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def strip_ok(body: str) -> str:
    text = body.strip()
    if text.endswith("{OK}"):
        text = text[:-4]
    return text


class IZoneBridgeClient:
    """Raw HTTP client for one iZone bridge."""

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        self.host = host
        # None = unknown polarity, True/False = cached Content-Type mode.
        self._use_content_type: bool | None = None

    async def _post_once(
        self, path: str, body: bytes, *, use_content_type: bool
    ) -> str:
        headers = {"Content-Type": "application/json"} if use_content_type else {}
        async with self._session.post(
            f"http://{self.host}/{path}",
            data=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as response:
            if response.status != 200:
                return f"{{ERROR http {response.status}}}"
            return decode_device_body(await response.read())

    async def _post_adaptive(
        self, path: str, payload: dict[str, Any] | str
    ) -> tuple[str, bool | None]:
        """POST trying cached polarity first, then the other one."""
        body = (
            payload.encode("utf-8")
            if isinstance(payload, str)
            else json.dumps(payload).encode("utf-8")
        )
        order: list[bool]
        if self._use_content_type is None:
            order = [False, True]
        else:
            order = [self._use_content_type, not self._use_content_type]
        last = "{ERROR}"
        for mode in order:
            result = await self._post_once(path, body, use_content_type=mode)
            last = result
            text = result.strip()
            if text and not text.startswith("{ERROR"):
                self._use_content_type = mode
                return result, mode
            await asyncio.sleep(V2_ERROR_BACKOFF)
            result = await self._post_once(path, body, use_content_type=mode)
            if result.strip() and not result.strip().startswith("{ERROR"):
                self._use_content_type = mode
                return result, mode
            last = result
        return last, self._use_content_type

    async def post_raw(self, path: str, body: str) -> str:
        """POST an arbitrary string body to an arbitrary path. Returns raw text."""
        result, _mode = await self._post_adaptive(path, body)
        return result

    async def get_raw(self, path: str) -> str:
        async with self._session.get(
            f"http://{self.host}/{path}",
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as response:
            if response.status != 200:
                return f"{{ERROR http {response.status}}}"
            return decode_device_body(await response.read())

    async def request_v2(self, type_: int, no: int = 0, no1: int = 0) -> dict[str, Any]:
        """POST iZoneRequestV2 and return {ok, raw, parsed, mode}."""
        payload = {"iZoneV2Request": {"Type": type_, "No": no, "No1": no1}}
        raw, mode = await self._post_adaptive("iZoneRequestV2", payload)
        parsed: Any = None
        text = strip_ok(raw)
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        return {
            "ok": bool(text) and not text.startswith("{ERROR"),
            "mode": mode,
            "raw": raw[:48000],
            "parsed": parsed,
        }

    async def command_v2(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw, mode = await self._post_adaptive("iZoneCommandV2", payload)
        return {"ok": not raw.strip().startswith("{ERROR"), "mode": mode, "raw": raw[:8000]}

    async def command_v1(self, command: str, data: dict[str, Any]) -> dict[str, Any]:
        raw, mode = await self._post_adaptive(command, data)
        return {"ok": not raw.strip().startswith("{ERROR"), "mode": mode, "raw": raw[:16000]}
