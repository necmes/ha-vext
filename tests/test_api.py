"""Tests for the Vext API client: auth, headers, rate limiting, retries."""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.vext.api import (
    VextApi,
    VextApiError,
    VextAuthError,
    VextRateLimitError,
)
from custom_components.vext.const import APIKEY, BASE_URL, USER_AGENT

PASSWORD_URL = re.compile(r"/auth/v1/token\?grant_type=password$")
REFRESH_URL = re.compile(r"/auth/v1/token\?grant_type=refresh_token$")

SESSION_PAYLOAD = {
    "access_token": "tok-1",
    "refresh_token": "ref-1",
    "expires_in": 3600,
    "user": {"id": "user-1"},
}

TABLES = (
    "factory_resets",
    "cabinet_settings",
    "cabinet_telemetry_latest",
    "cabinet_data",
    "cabinet_plants",
)


def table(name: str) -> re.Pattern:
    return re.compile(rf"/rest/v1/{name}\?")


def response(
    status: int = 200,
    *,
    json: Any = None,
    text: str | None = None,
    headers: dict[str, str] | None = None,
) -> AiohttpClientMockResponse:
    """Build a canned response usable from a `side_effect`."""
    return AiohttpClientMockResponse(
        method="get",
        url=URL(BASE_URL),
        status=status,
        json=json,
        text=text,
        headers=headers,
    )


def queue(
    mocker: AiohttpClientMocker,
    method: str,
    url: re.Pattern,
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Register `responses` to be returned in order for matching requests."""
    remaining = list(responses)

    async def _side_effect(_method: str, _url: URL, _data: Any) -> Any:
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    mocker.request(method, url, side_effect=_side_effect)


@pytest.fixture
def mocker() -> AiohttpClientMocker:
    return AiohttpClientMocker()


@pytest.fixture
async def session(mocker: AiohttpClientMocker):
    sess = mocker.create_session(asyncio.get_running_loop())
    yield sess
    await sess.close()


@pytest.fixture
def api(session) -> VextApi:
    return VextApi(session, "me@example.com", "hunter2")


def calls(mocker: AiohttpClientMocker, method: str) -> list[tuple]:
    return [c for c in mocker.mock_calls if c[0].lower() == method.lower()]


def logged_in(mocker: AiohttpClientMocker) -> None:
    mocker.post(PASSWORD_URL, json=SESSION_PAYLOAD)


# ------------------------------------------------------------------- auth


async def test_validate_uses_password_grant_with_useragent(api, mocker) -> None:
    logged_in(mocker)
    await api.validate()

    method, url, data, headers = mocker.mock_calls[0]
    assert method.lower() == "post"
    assert "grant_type=password" in str(url)
    assert data == {"email": "me@example.com", "password": "hunter2"}
    assert headers["User-Agent"] == USER_AGENT
    assert headers["apikey"] == APIKEY
    assert api.user_id == "user-1"


async def test_bad_credentials_raise_auth_error(api, mocker) -> None:
    mocker.post(PASSWORD_URL, status=400, json={"error_description": "Invalid login"})
    with pytest.raises(VextAuthError, match="Invalid login"):
        await api.validate()


async def test_login_without_message_still_reports_the_status(api, mocker) -> None:
    mocker.post(PASSWORD_URL, status=418, json={})
    with pytest.raises(VextAuthError, match="HTTP 418"):
        await api.validate()


async def test_transport_failure_raises_api_error(api, mocker) -> None:
    mocker.post(PASSWORD_URL, exc=aiohttp.ClientError("boom"))
    with pytest.raises(VextApiError, match="boom"):
        await api.validate()


async def test_rate_limited_login_reports_retry_after(api, mocker) -> None:
    mocker.post(PASSWORD_URL, status=429, headers={"Retry-After": "42"})
    with pytest.raises(VextRateLimitError) as err:
        await api.validate()
    assert err.value.retry_after == 42.0


async def test_unparsable_retry_after_is_ignored(api, mocker) -> None:
    mocker.post(
        PASSWORD_URL,
        status=503,
        headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"},
    )
    with pytest.raises(VextRateLimitError) as err:
        await api.validate()
    assert err.value.retry_after is None


async def test_expired_session_prefers_refresh_token(api, mocker) -> None:
    logged_in(mocker)
    await api.validate()
    api._expires_at = time.time() - 1  # pretend the access token aged out

    mocker.post(REFRESH_URL, json={**SESSION_PAYLOAD, "access_token": "tok-2"})
    mocker.get(table("factory_resets"), json=[])
    await api._select("factory_resets")

    refreshes = [c for c in calls(mocker, "post") if "refresh_token" in str(c[1])]
    assert len(refreshes) == 1
    assert refreshes[0][2] == {"refresh_token": "ref-1"}
    assert api._token == "tok-2"


async def test_rejected_refresh_token_falls_back_to_password(api, mocker) -> None:
    logged_in(mocker)
    await api.validate()
    api._expires_at = time.time() - 1

    mocker.clear_requests()
    mocker.post(REFRESH_URL, status=400, json={"error": "invalid_grant"})
    mocker.post(PASSWORD_URL, json={**SESSION_PAYLOAD, "access_token": "tok-3"})
    mocker.get(table("factory_resets"), json=[])
    await api._select("factory_resets")

    assert api._token == "tok-3"
    assert [str(c[1]).split("grant_type=")[1] for c in calls(mocker, "post")] == [
        "refresh_token",
        "password",
    ]


async def test_concurrent_calls_trigger_a_single_login(api, mocker) -> None:
    logged_in(mocker)
    for name in TABLES:
        mocker.get(table(name), json=[])

    await asyncio.gather(*(api._select(name) for name in TABLES))

    assert len(calls(mocker, "post")) == 1


# --------------------------------------------------------------- requests


async def test_request_headers_carry_bearer_and_useragent(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(table("cabinet_data"), json=[])
    await api._select("cabinet_data")

    _, _, _, headers = calls(mocker, "get")[0]
    assert headers["Authorization"] == "Bearer tok-1"
    assert headers["User-Agent"] == USER_AGENT
    assert headers["apikey"] == APIKEY


async def test_mid_flight_401_reauthenticates_once_then_succeeds(api, mocker) -> None:
    logged_in(mocker)
    queue(
        mocker,
        "get",
        table("cabinet_data"),
        [response(401, json={}), response(200, json=[{"factory_reset_id": "c1"}])],
    )

    assert await api._select("cabinet_data") == [{"factory_reset_id": "c1"}]
    assert len(calls(mocker, "post")) == 2  # initial login + forced re-login


async def test_persistent_401_raises_auth_error(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(table("cabinet_data"), status=401, json={})

    with pytest.raises(VextAuthError):
        await api._select("cabinet_data")


async def test_rate_limited_read_is_not_retried_as_wide_select(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(table("cabinet_data"), status=429, headers={"Retry-After": "30"})

    with pytest.raises(VextRateLimitError) as err:
        await api._select("cabinet_data")
    assert err.value.retry_after == 30.0
    assert "cabinet_data" not in api._wide_select


async def test_rejected_column_list_falls_back_to_wide_select(api, mocker) -> None:
    logged_in(mocker)
    queue(
        mocker,
        "get",
        table("cabinet_data"),
        [
            response(400, text="column does not exist"),
            response(200, json=[{"factory_reset_id": "c1"}]),
        ],
    )

    assert await api._select("cabinet_data") == [{"factory_reset_id": "c1"}]
    assert "cabinet_data" in api._wide_select

    urls = [str(c[1]) for c in calls(mocker, "get")]
    assert "select=*" not in urls[0]
    assert "select=*" in urls[1]

    # the widened select is remembered, so the next poll asks for `*` directly
    await api._select("cabinet_data")
    assert "select=*" in str(calls(mocker, "get")[-1][1])


async def test_other_http_errors_are_not_masked(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(table("cabinet_data"), status=500, text="server error")

    with pytest.raises(VextApiError, match="HTTP 500"):
        await api._select("cabinet_data")
    assert "cabinet_data" not in api._wide_select


async def test_empty_body_is_returned_as_none(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(table("cabinet_data"), status=204, text="")
    assert await api._select("cabinet_data") is None


async def test_reads_only_the_columns_it_renders(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(table("cabinet_telemetry_latest"), json=[])
    await api._select("cabinet_telemetry_latest")

    url = str(calls(mocker, "get")[0][1])
    assert "select=*" not in url
    assert "top_temperature_c" in url


# ------------------------------------------------------------------- data


async def test_get_all_merges_every_table_into_cabinets(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(
        table("factory_resets"),
        json=[{"id": "c1", "radxa_serial_number": "SN123456789"}],
    )
    mocker.get(
        table("cabinet_settings"),
        json=[
            {
                "factory_reset_id": "c1",
                "name": "Kitchen",
                "desired_brightness_pct": 80,
                "lights_on_time": "07:00:00",
            }
        ],
    )
    mocker.get(
        table("cabinet_telemetry_latest"),
        json=[
            {
                "factory_reset_id": "c1",
                "top_temperature_c": 21.5,
                "top_humidity_pct": 55,
                "firmware_version": "1.2.3",
            }
        ],
    )
    mocker.get(table("cabinet_data"), json=[{"factory_reset_id": "c1", "score": 92}])
    mocker.get(
        table("cabinet_plants"),
        json=[
            {
                "factory_reset_id": "c1",
                "plant_grid_position": 2,
                "plant_status": "READY",
                "plant_health": 90,
                "plants_id": {
                    "name": "Basil",
                    "plant_image_id": {"source_url": "http://img/1.jpg"},
                },
            },
            {
                "factory_reset_id": "c1",
                "plant_grid_position": 1,
                "plant_status": "GROWING",
                "plant_health": 80,
                "plants_id": {"name": "Mint", "plant_image_id": None},
            },
            {
                "factory_reset_id": "c1",
                "plant_grid_position": 3,
                "plant_status": "PAST_PRIME",
                "plant_health": 40,
                "plants_id": None,
            },
        ],
    )

    cabinet = (await api.async_get_all())["c1"]

    assert cabinet["name"] == "Kitchen"
    assert cabinet["temperature_c"] == 21.5
    assert cabinet["humidity_pct"] == 55
    assert cabinet["firmware_version"] == "1.2.3"
    assert cabinet["lights_on_time"] == "07:00:00"
    assert cabinet["score"] == 92
    assert cabinet["pods_total"] == 3
    assert cabinet["pods_ready"] == 1
    assert cabinet["pods_growing"] == 1
    assert cabinet["pods_past_prime"] == 1
    assert [p["plant"] for p in cabinet["pods"]] == ["Mint", "Basil", None]
    assert cabinet["pods"][1]["image"] == "http://img/1.jpg"
    assert cabinet["pods"][0]["image"] is None


async def test_get_all_falls_back_to_serial_when_unnamed(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(
        table("factory_resets"),
        json=[{"id": "c1", "radxa_serial_number": "SN123456789"}],
    )
    for name in TABLES[1:]:
        mocker.get(table(name), json=[])

    data = await api.async_get_all()
    assert data["c1"]["name"] == "Vext SN123456"
    assert data["c1"]["pods_total"] == 0


async def test_one_poll_is_five_reads_of_active_cabinets(api, mocker) -> None:
    logged_in(mocker)
    for name in TABLES:
        mocker.get(table(name), json=[])

    await api.async_get_all()

    urls = [str(c[1]) for c in calls(mocker, "get")]
    assert len(urls) == 5  # no per-cabinet fan-out
    assert any("is_active=eq.true" in url for url in urls)


async def test_set_settings_patches_only_that_cabinet(api, mocker) -> None:
    logged_in(mocker)
    mocker.patch(table("cabinet_settings"), status=204, text="")
    await api.async_set_settings("c1", {"desired_brightness_pct": 50})

    _, url, data, headers = calls(mocker, "patch")[0]
    assert "factory_reset_id=eq.c1" in str(url)
    assert data == {"desired_brightness_pct": 50}
    assert headers["Prefer"] == "return=minimal"
    assert headers["User-Agent"] == USER_AGENT


async def test_set_preferred_upserts_for_the_signed_in_user(api, mocker) -> None:
    logged_in(mocker)
    await api.validate()
    mocker.post(table("user_preferences"), status=204, text="")
    await api.async_set_preferred("c1")

    upserts = [c for c in calls(mocker, "post") if "user_preferences" in str(c[1])]
    assert upserts[0][2] == [{"user_id": "user-1", "preferred_factory_reset_id": "c1"}]


async def test_rate_limit_without_retry_after_header(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(table("cabinet_data"), status=429, json={})

    with pytest.raises(VextRateLimitError) as err:
        await api._select("cabinet_data")
    assert err.value.retry_after is None


async def test_transport_failure_on_a_read_raises_api_error(api, mocker) -> None:
    logged_in(mocker)
    mocker.get(table("cabinet_data"), exc=aiohttp.ClientError("connection reset"))

    with pytest.raises(VextApiError, match="connection reset"):
        await api._select("cabinet_data")




# --------------------------------------------------------- account scoping


async def test_a_second_waiter_reuses_the_session_the_first_one_renewed(
    api, mocker
) -> None:
    """Two polls racing on an expired token must not log in twice."""
    logged_in(mocker)
    await api.validate()
    api._expires_at = time.time() - 1  # both callers will see an expired token

    mocker.post(REFRESH_URL, json={**SESSION_PAYLOAD, "access_token": "tok-2"})
    mocker.get(table("cabinet_data"), json=[])
    mocker.get(table("cabinet_settings"), json=[])

    await asyncio.gather(
        api._select("cabinet_data"), api._select("cabinet_settings")
    )

    refreshes = [c for c in calls(mocker, "post") if "refresh_token" in str(c[1])]
    assert len(refreshes) == 1
    assert api._token == "tok-2"
    for _, _, _, headers in calls(mocker, "get"):
        assert headers["Authorization"] == "Bearer tok-2"


async def test_a_poll_never_pins_itself_to_one_account(api, mocker) -> None:
    """Nothing but the session token says whose data is being asked for."""
    logged_in(mocker)
    for name in TABLES:
        mocker.get(table(name), json=[])

    await api.async_get_all()

    for _, url, _, headers in calls(mocker, "get"):
        text = str(url)
        assert "me@example.com" not in text
        assert "user_id" not in text
        assert "user-1" not in text
        assert headers["Authorization"] == "Bearer tok-1"


async def test_each_account_gets_its_own_cabinets(session) -> None:
    """The same code, signed in as somebody else, returns their cabinets."""

    async def cabinets_of(email: str, cabinet_id: str, name: str) -> dict:
        mocker = AiohttpClientMocker()
        sess = mocker.create_session(asyncio.get_running_loop())
        other = VextApi(sess, email, "hunter2")
        mocker.post(PASSWORD_URL, json=SESSION_PAYLOAD)
        mocker.get(table("factory_resets"), json=[{"id": cabinet_id}])
        mocker.get(table("cabinet_settings"), json=[{"factory_reset_id": cabinet_id, "name": name}])
        for table_name in TABLES[2:]:
            mocker.get(table(table_name), json=[])
        try:
            return await other.async_get_all()
        finally:
            await sess.close()

    alice = await cabinets_of("alice@example.com", "cab-a", "Alice kitchen")
    bob = await cabinets_of("bob@example.com", "cab-b", "Bob balcony")

    assert list(alice) == ["cab-a"]
    assert alice["cab-a"]["name"] == "Alice kitchen"
    assert list(bob) == ["cab-b"]
    assert bob["cab-b"]["name"] == "Bob balcony"


async def test_set_preferred_logs_in_before_writing_when_called_cold(api, mocker) -> None:
    """No session yet: the upsert must authenticate first, not send a null user."""
    logged_in(mocker)
    mocker.post(table("user_preferences"), status=204, text="")

    await api.async_set_preferred("c1")

    posts = [str(c[1]) for c in calls(mocker, "post")]
    assert "grant_type=password" in posts[0]
    assert "user_preferences" in posts[1]
    upsert = calls(mocker, "post")[1][2]
    assert upsert == [{"user_id": "user-1", "preferred_factory_reset_id": "c1"}]


async def test_waiting_on_the_auth_lock_does_not_renew_twice(api) -> None:
    """The task that waited on the lock adopts the session, it does not re-login."""
    grants: list[str] = []
    gate = asyncio.Event()

    async def fake_token_request(grant: str, payload: dict) -> dict:
        grants.append(grant)
        await gate.wait()  # hold the lock until both callers are in flight
        return {**SESSION_PAYLOAD, "access_token": "tok-2"}

    api._token, api._refresh_token = "tok-1", "ref-1"
    api._expires_at = time.time() - 1
    api._token_request = fake_token_request

    first = asyncio.create_task(api._authenticate())
    await asyncio.sleep(0)  # first task takes the lock and blocks on the gate
    second = asyncio.create_task(api._authenticate())
    await asyncio.sleep(0)  # second task queues behind the lock
    gate.set()
    await asyncio.gather(first, second)

    assert grants == ["refresh_token"]
    assert api._token == "tok-2"
