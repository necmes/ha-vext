"""Data update coordinator for Vext."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VextApi, VextApiError, VextAuthError, VextRateLimitError
from .backoff import BackoffPolicy
from .const import (
    BACKOFF_FACTOR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_BACKOFF_INTERVAL,
    MIN_SCAN_INTERVAL,
    REFRESH_DEBOUNCE,
)

_LOGGER = logging.getLogger(__name__)


class VextCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls the Vext service and exposes cabinets keyed by their id.

    The service has no public API, so this coordinator is deliberately polite:
    a floor on the poll interval, exponential backoff while the service errors,
    respect for Retry-After, and a debounce so a burst of writes triggers one
    refresh instead of several.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: VextApi,
        scan_interval: timedelta | None = None,
    ) -> None:
        base = max(scan_interval or DEFAULT_SCAN_INTERVAL, MIN_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=base,
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REFRESH_DEBOUNCE, immediate=False
            ),
        )
        self.api = api
        self.entry = entry
        self._backoff = BackoffPolicy(base, MAX_BACKOFF_INTERVAL, BACKOFF_FACTOR)

    def set_scan_interval(self, scan_interval: timedelta) -> None:
        """Apply a new base interval (never below the floor) and clear backoff."""
        base = max(scan_interval, MIN_SCAN_INTERVAL)
        self._backoff = BackoffPolicy(base, MAX_BACKOFF_INTERVAL, BACKOFF_FACTOR)
        self.update_interval = base

    def _slow_down(self, retry_after: float | None = None) -> None:
        self.update_interval = self._backoff.failure(retry_after)
        _LOGGER.debug(
            "Vext update failed (%s in a row); next poll in %s",
            self._backoff.failures,
            self.update_interval,
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            data = await self.api.async_get_all()
        except VextAuthError as err:
            # Bad or revoked credentials: stop polling and ask the user, instead
            # of retrying a login that cannot succeed.
            raise ConfigEntryAuthFailed(str(err)) from err
        except VextRateLimitError as err:
            self._slow_down(err.retry_after)
            raise UpdateFailed(str(err)) from err
        except VextApiError as err:
            self._slow_down()
            raise UpdateFailed(str(err)) from err
        self.update_interval = self._backoff.reset()
        return data
