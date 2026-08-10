"""Async client for the Vext cloud service.

Design notes (deliberate, please keep):
* Every request carries a distinctive User-Agent so the service can tell this
  client apart in its logs.
* Only the columns the integration actually renders are requested, so responses
  stay small.
* The session is refreshed with the refresh token; the password grant is only
  used for the initial login or when the refresh token is rejected.
* Nothing here tries to reach data outside the signed-in user's own account.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import APIKEY, BASE_URL, REQUEST_TIMEOUT, USER_AGENT

_LOGGER = logging.getLogger(__name__)

# Explicit column lists: ask for what is used, nothing more.
SELECTS: dict[str, str] = {
    "factory_resets": "id,radxa_serial_number",
    "cabinet_settings": (
        "factory_reset_id,name,desired_brightness_pct,fog_duration_adjust_pct,"
        "cycle_length_adjust_pct,lights_on_time,lights_off_time,timezone_name_iana"
    ),
    "cabinet_telemetry_latest": (
        "factory_reset_id,top_temperature_c,top_humidity_pct,water_volume_ml,"
        "nutrient_grow_volume_ml,nutrient_bloom_volume_ml,wifi_ssid,wifi_rssi,"
        "firmware_version,water_refill_predicted_at,"
        "nutrient_grow_refill_predicted_at,nutrient_bloom_refill_predicted_at"
    ),
    "cabinet_data": "factory_reset_id,score,score_info_message,water_info_message",
    "cabinet_plants": (
        "plant_grid_position,plant_status,plant_health,factory_reset_id,"
        "plants_id(name,first_harvest_in,plant_image_id(source_url))"
    ),
}


class VextAuthError(Exception):
    """Invalid credentials / rejected session."""


class VextApiError(Exception):
    """Generic API/transport error."""


class VextRateLimitError(VextApiError):
    """The service asked us to slow down (HTTP 429 / 503)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after_seconds(resp: aiohttp.ClientResponse) -> float | None:
    """Parse a Retry-After header expressed in seconds."""
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw.strip()))
    except ValueError:
        return None


class VextApi:
    """Talks to the Vext backend with a user's own email/password."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._auth_lock = asyncio.Lock()
        # Tables whose explicit column list was rejected once; fall back to `*`.
        self._wide_select: set[str] = set()
        self.user_id: str | None = None

    # ---------------------------------------------------------------- auth

    async def _token_request(self, grant: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{BASE_URL}/auth/v1/token?grant_type={grant}"
        headers = {
            "apikey": APIKEY,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.post(url, headers=headers, json=payload) as resp:
                    if resp.status in (429, 503):
                        raise VextRateLimitError(
                            f"HTTP {resp.status} on auth", _retry_after_seconds(resp)
                        )
                    data = await resp.json()
                    if resp.status != 200 or "access_token" not in data:
                        raise VextAuthError(
                            data.get("error_description")
                            or data.get("msg")
                            or data.get("error")
                            or f"login failed (HTTP {resp.status})"
                        )
                    return data
        except (aiohttp.ClientError, TimeoutError) as err:
            raise VextApiError(str(err)) from err

    def _store_session(self, data: dict[str, Any]) -> None:
        self._token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        self.user_id = (data.get("user") or {}).get("id") or self.user_id

    async def _authenticate(self, *, force_password: bool = False) -> None:
        """Renew the session, preferring the refresh token over a full login."""
        async with self._auth_lock:
            if not force_password and self._token and time.time() < self._expires_at:
                return  # another task refreshed while we waited
            if not force_password and self._refresh_token:
                try:
                    self._store_session(
                        await self._token_request(
                            "refresh_token", {"refresh_token": self._refresh_token}
                        )
                    )
                    return
                except VextAuthError:
                    _LOGGER.debug("Refresh token rejected, falling back to password grant")
                    self._refresh_token = None
            self._store_session(
                await self._token_request(
                    "password", {"email": self._email, "password": self._password}
                )
            )

    async def _ensure_token(self) -> None:
        if self._token is None or time.time() >= self._expires_at:
            await self._authenticate()

    async def validate(self) -> None:
        """Used by the config flow: raises on bad credentials."""
        await self._authenticate(force_password=True)

    # ------------------------------------------------------------- requests

    async def _send(self, method: str, path: str, json: Any, prefer: str | None) -> Any:
        headers = {
            "apikey": APIKEY,
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if prefer:
            headers["Prefer"] = prefer
        if json is not None:
            headers["Content-Type"] = "application/json"
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with self._session.request(
                method, f"{BASE_URL}{path}", headers=headers, json=json
            ) as resp:
                if resp.status == 401:
                    return _UNAUTHORIZED
                return await self._parse(resp)

    async def _request(
        self, method: str, path: str, *, json: Any = None, prefer: str | None = None
    ) -> Any:
        await self._ensure_token()
        try:
            result = await self._send(method, path, json, prefer)
            if result is _UNAUTHORIZED:
                # Token rejected mid-flight: renew once, then retry once.
                await self._authenticate(force_password=True)
                result = await self._send(method, path, json, prefer)
                if result is _UNAUTHORIZED:
                    raise VextAuthError("session rejected after re-authentication")
            return result
        except (aiohttp.ClientError, TimeoutError) as err:
            raise VextApiError(str(err)) from err

    @staticmethod
    async def _parse(resp: aiohttp.ClientResponse) -> Any:
        if resp.status in (429, 503):
            raise VextRateLimitError(
                f"HTTP {resp.status}: service asked to slow down",
                _retry_after_seconds(resp),
            )
        text = await resp.text()
        if resp.status >= 400:
            raise VextApiError(f"HTTP {resp.status}: {text[:200]}")
        if not text.strip():
            return None
        return await resp.json()

    async def _select(self, table: str, query: str = "") -> Any:
        """GET a table with an explicit column list, `*` only as a fallback."""
        columns = "*" if table in self._wide_select else SELECTS[table]
        path = f"/rest/v1/{table}?{query}select={columns}"
        try:
            return await self._request("GET", path)
        except VextRateLimitError:
            raise
        except VextApiError as err:
            if columns == "*" or "HTTP 400" not in str(err):
                raise
            # A column we asked for no longer exists: remember it and widen once.
            _LOGGER.warning(
                "Column list rejected for %s (%s); falling back to select=* — "
                "please report this at https://github.com/necmes/ha-vext/issues",
                table,
                err,
            )
            self._wide_select.add(table)
            return await self._request("GET", f"/rest/v1/{table}?{query}select=*")

    # ----------------------------------------------------------------- data

    async def async_get_all(self) -> dict[str, dict[str, Any]]:
        """Return every cabinet of the signed-in account, keyed by cabinet id."""
        resets = await self._select("factory_resets", "is_active=eq.true&")
        settings = await self._select("cabinet_settings")
        telem = await self._select("cabinet_telemetry_latest")
        cdata = await self._select("cabinet_data")
        plants = await self._select("cabinet_plants")

        by_s = {s["factory_reset_id"]: s for s in (settings or [])}
        by_t = {t["factory_reset_id"]: t for t in (telem or [])}
        by_c = {c["factory_reset_id"]: c for c in (cdata or [])}
        by_p: dict[str, list] = {}
        for p in plants or []:
            by_p.setdefault(p["factory_reset_id"], []).append(p)

        out: dict[str, dict[str, Any]] = {}
        for r in resets or []:
            frid = r["id"]
            s, t, c = by_s.get(frid, {}), by_t.get(frid, {}), by_c.get(frid, {})
            pods = sorted(by_p.get(frid, []), key=lambda x: x.get("plant_grid_position") or 0)
            counts: dict[str, int] = {}
            for p in pods:
                counts[p.get("plant_status")] = counts.get(p.get("plant_status"), 0) + 1
            out[frid] = {
                "factory_reset_id": frid,
                "serial": r.get("radxa_serial_number"),
                "name": s.get("name") or f"Vext {(r.get('radxa_serial_number') or frid)[:8]}",
                "temperature_c": t.get("top_temperature_c"),
                "humidity_pct": t.get("top_humidity_pct"),
                "water_volume_ml": t.get("water_volume_ml"),
                "nutrient_grow_ml": t.get("nutrient_grow_volume_ml"),
                "nutrient_bloom_ml": t.get("nutrient_bloom_volume_ml"),
                "wifi_ssid": t.get("wifi_ssid"),
                "wifi_rssi": t.get("wifi_rssi"),
                "firmware_version": t.get("firmware_version"),
                "water_refill_predicted_at": t.get("water_refill_predicted_at"),
                "nutrient_grow_refill_predicted_at": t.get("nutrient_grow_refill_predicted_at"),
                "nutrient_bloom_refill_predicted_at": t.get("nutrient_bloom_refill_predicted_at"),
                "desired_brightness_pct": s.get("desired_brightness_pct"),
                "fog_duration_adjust_pct": s.get("fog_duration_adjust_pct"),
                "cycle_length_adjust_pct": s.get("cycle_length_adjust_pct"),
                "lights_on_time": s.get("lights_on_time"),
                "lights_off_time": s.get("lights_off_time"),
                "timezone_name_iana": s.get("timezone_name_iana"),
                "score": c.get("score"),
                "score_info": c.get("score_info_message"),
                "water_info": c.get("water_info_message"),
                "pods_total": len(pods),
                "pods_ready": counts.get("READY", 0),
                "pods_growing": counts.get("GROWING", 0),
                "pods_past_prime": counts.get("PAST_PRIME", 0),
                "pods": [
                    {
                        "pos": p.get("plant_grid_position"),
                        "plant": (p.get("plants_id") or {}).get("name"),
                        "status": p.get("plant_status"),
                        "health": p.get("plant_health"),
                        "image": (((p.get("plants_id") or {}).get("plant_image_id")) or {}).get("source_url"),
                    }
                    for p in pods
                ],
            }
        return out

    async def async_set_settings(self, frid: str, fields: dict[str, Any]) -> None:
        await self._request(
            "PATCH",
            f"/rest/v1/cabinet_settings?factory_reset_id=eq.{frid}",
            json=fields,
            prefer="return=minimal",
        )

    async def async_set_preferred(self, frid: str) -> None:
        if not self.user_id:
            await self._ensure_token()
        await self._request(
            "POST",
            "/rest/v1/user_preferences?on_conflict=user_id",
            json=[{"user_id": self.user_id, "preferred_factory_reset_id": frid}],
            prefer="resolution=merge-duplicates,return=minimal",
        )


class _Unauthorized:
    """Sentinel telling `_request` the token was rejected."""


_UNAUTHORIZED = _Unauthorized()
