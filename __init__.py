"""Support for nibe uplink."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Dict, Optional, TypeVar, cast

import homeassistant.helpers.config_validation as cv
import nibeuplink
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.const import CONF_NAME
from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from nibeuplink import Uplink, UplinkSession
from nibeuplink.typing import ParameterId, ParameterType, System

from .const import (
    CONF_ACCESS_DATA,
    CONF_BINARY_SENSORS,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CLIMATE_SYSTEMS,
    CONF_CLIMATES,
    CONF_CURRENT_TEMPERATURE,
    CONF_FANS,
    CONF_REDIRECT_URI,
    CONF_SENSORS,
    CONF_SWITCHES,
    CONF_SYSTEM,
    CONF_SYSTEMS,
    CONF_THERMOSTATS,
    CONF_UNITS,
    CONF_VALVE_POSITION,
    CONF_WATER_HEATERS,
    CONF_WRITEACCESS,
    DATA_NIBE_CONFIG,
    DATA_NIBE_ENTRIES,
    DOMAIN,
    SCAN_INTERVAL,
)
from .services import async_register_services, async_track_delta_time

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")

ParameterSet = Dict[ParameterId, Optional[ParameterType]]


def ensure_system_dict(value: dict[int, T] | list[T] | None) -> dict[int, T]:
    """Wrap value in list if it is not one."""
    if value is None:
        return {}
    if isinstance(value, list):
        value_schema = vol.Schema(
            [
                vol.Schema(
                    {vol.Required(CONF_SYSTEM): cv.positive_int}, extra=vol.ALLOW_EXTRA
                )
            ]
        )
        value_dict = value_schema(value)
        return {x[CONF_SYSTEM]: x for x in value_dict}
    if isinstance(value, dict):
        return value
    value_any = SYSTEM_SCHEMA(value)
    return {value_any[CONF_SYSTEM]: value_any}


THERMOSTAT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CLIMATE_SYSTEMS, default=[1]): vol.All(cv.ensure_list, [int]),
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_CURRENT_TEMPERATURE): cv.entity_id,
        vol.Optional(CONF_VALVE_POSITION): cv.entity_id,
    }
)

SYSTEM_SCHEMA = vol.Schema(
    vol.All(
        cv.deprecated(CONF_CLIMATES),
        cv.deprecated(CONF_WATER_HEATERS),
        cv.deprecated(CONF_FANS),
        cv.deprecated(CONF_UNITS),
        {
            vol.Remove(CONF_CLIMATES): object,
            vol.Remove(CONF_WATER_HEATERS): object,
            vol.Remove(CONF_FANS): object,
            vol.Remove(CONF_UNITS): list,
            vol.Optional(CONF_SYSTEM): cv.positive_int,
            vol.Optional(CONF_SENSORS, default=[]): vol.All(
                cv.ensure_list, [cv.string]
            ),
            vol.Optional(CONF_SWITCHES, default=[]): vol.All(
                cv.ensure_list, [cv.string]
            ),
            vol.Optional(CONF_BINARY_SENSORS, default=[]): vol.All(
                cv.ensure_list, [cv.string]
            ),
            vol.Optional(CONF_THERMOSTATS, default={}): {
                cv.positive_int: THERMOSTAT_SCHEMA
            },
        },
    )
)

NIBE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_REDIRECT_URI): cv.string,
        vol.Optional(CONF_CLIENT_ID): cv.string,
        vol.Optional(CONF_CLIENT_SECRET): cv.string,
        vol.Optional(CONF_WRITEACCESS): cv.boolean,
        vol.Optional(CONF_SYSTEMS, default={}): vol.All(
            ensure_system_dict, {vol.Coerce(int): SYSTEM_SCHEMA}
        ),
    }
)

CONFIG_SCHEMA = vol.Schema({DOMAIN: NIBE_SCHEMA}, extra=vol.ALLOW_EXTRA)

FORWARD_PLATFORMS = (
    "climate",
    "switch",
    "sensor",
    "binary_sensor",
    "water_heater",
    "fan",
)


@dataclass
class NibeData:
    """Holder for nibe data."""

    session: UplinkSession
    uplink: Uplink
    systems: dict[int, NibeSystem]
    coordinator: DataUpdateCoordinator | None = None


async def async_setup(hass, config):
    """Configure the nibe uplink component."""
    hass.data[DATA_NIBE_ENTRIES] = {}
    if DOMAIN in config:
        hass.data[DATA_NIBE_CONFIG] = config[DOMAIN]
    else:
        hass.data[DATA_NIBE_CONFIG] = NIBE_SCHEMA({})
    await async_register_services(hass)
    return True


def _get_system_config(hass, system_id: int):
    config = hass.data[DATA_NIBE_CONFIG]
    system = config[CONF_SYSTEMS].get(system_id)
    if system:
        return system
    return SYSTEM_SCHEMA({})


async def async_setup_entry(hass, entry: config_entries.ConfigEntry):
    """Set up an access point from a config entry."""
    _LOGGER.debug("Setup nibe entry")

    scope = None
    if entry.data.get(CONF_WRITEACCESS):
        scope = ["READSYSTEM", "WRITESYSTEM"]
    else:
        scope = ["READSYSTEM"]

    def access_data_write(data):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_ACCESS_DATA: data}
        )

    session = UplinkSession(
        client_id=entry.data.get(CONF_CLIENT_ID),
        client_secret=entry.data.get(CONF_CLIENT_SECRET),
        redirect_uri=entry.data.get(CONF_REDIRECT_URI),
        access_data=entry.data.get(CONF_ACCESS_DATA),
        access_data_write=access_data_write,
        scope=scope,
    )
    await session.open()

    uplink = Uplink(session)

    data = NibeData(session, uplink, {})
    hass.data[DATA_NIBE_ENTRIES][entry.entry_id] = data

    async def _async_add_system(system_raw: System, config: dict):

        system = NibeSystem(
            hass,
            uplink,
            system_raw,
            entry.entry_id,
            config,
        )
        await system.load()

        data.systems[system.system_id] = system

    async def _async_refresh():
        systems_raw = await uplink.get_systems()

        if systems_conf := entry.options.get(CONF_SYSTEMS):
            systems_enabled = {system_id for system_id in systems_conf}
        else:
            systems_enabled = {system["systemId"] for system in systems_raw}

        for system_raw in systems_raw:
            system_id = system_raw["systemId"]

            if system_id not in systems_enabled:
                continue

            if system := data.systems.get(system_id):
                await system.async_refresh(system_raw)
            else:
                await _async_add_system(system_raw, _get_system_config(hass, system_id))

    await _async_refresh()

    entry.async_on_unload(async_track_delta_time(hass, SCAN_INTERVAL, _async_refresh))

    for platform in FORWARD_PLATFORMS:
        hass.async_add_job(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    return True


async def async_unload_entry(hass, entry):
    """Unload a configuration entity."""
    data: NibeData = hass.data[DATA_NIBE_ENTRIES][entry.entry_id]
    await asyncio.wait(
        [
            hass.config_entries.async_forward_entry_unload(entry, platform)
            for platform in FORWARD_PLATFORMS
        ]
    )

    await asyncio.wait([system.unload() for system in data.systems.values()])

    await data.session.close()
    hass.data[DATA_NIBE_ENTRIES].pop(entry.entry_id)

    return True


class NibeSystem:
    """Object representing a system."""

    coordinator: DataUpdateCoordinator

    def __init__(
        self,
        hass,
        uplink: Uplink,
        system: nibeuplink.typing.System,
        entry_id: str,
        config: dict,
    ):
        """Init."""
        self.hass = hass
        self.system_id = system["systemId"]
        self.entry_id = entry_id
        self.system = system
        self.uplink = uplink
        self.notice: list[dict] = []
        self.statuses: set[str] = set()
        self._device_info: DeviceInfo = {}
        self._unsub: list[Callable] = []
        self.config = config
        self._parameters: ParameterSet = {}
        self._parameter_subscribers: dict[object, set[ParameterId]] = {}
        self._parameter_preload: set[ParameterId] = set()

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return self._device_info

    async def unload(self):
        """Unload system."""
        for unsub in reversed(self._unsub):
            unsub()
        self._unsub = []

    async def async_refresh(self, system: nibeuplink.typing.System):
        """Update the system."""
        if system != self.system:
            self.system = system
            await self.coordinator.async_refresh()

    async def load(self):
        """Load system."""

        self._device_info = {
            "configuration_url": f"https://nibeuplink.com/System/{self.system_id}",
            "identifiers": {(DOMAIN, self.system_id)},
            "manufacturer": "NIBE Energy Systems",
            "model": self.system.get("productName"),
            "name": f"{self.system.get('name')} - {self.system_id}",
        }

        device_registry = await self.hass.helpers.device_registry.async_get_registry()
        device_registry.async_get_or_create(
            config_entry_id=self.entry_id, **self._device_info
        )

        async def _update():
            await self.update_notifications()
            await self.update_statuses()

            parameters = set()
            for subscriber_parameters in self._parameter_subscribers.values():
                parameters |= subscriber_parameters
            parameters -= self._parameter_preload
            self._parameter_preload = set()

            await self.update_parameters(parameters)

        self.coordinator = DataUpdateCoordinator(
            self.hass,
            _LOGGER,
            name=f"Nibe Uplink: {self.system_id}",
            update_interval=timedelta(minutes=10),
            update_method=_update,
        )
        await self.coordinator.async_config_entry_first_refresh()

    async def update_statuses(self):
        """Update status list."""
        status_icons = await self.uplink.get_status(self.system_id)
        statuses = set()
        for status_icon in status_icons:
            statuses.add(status_icon["title"])
            for parameter in status_icon["parameters"]:
                self.set_parameter(parameter["parameterId"], parameter)
        self.statuses = statuses
        _LOGGER.debug("Statuses: %s", statuses)

    async def update_notifications(self):
        """Update notification list."""
        notice = await self.uplink.get_notifications(self.system_id)
        added = [k for k in notice if k not in self.notice]
        removed = [k for k in self.notice if k not in notice]
        self.notice = notice

        for x in added:
            persistent_notification.async_create(
                self.hass,
                x["info"]["description"],
                x["info"]["title"],
                "nibe:{}".format(x["notificationId"]),
            )
        for x in removed:
            persistent_notification.async_dismiss(
                self.hass, "nibe:{}".format(x["notificationId"])
            )

    def get_parameter(
        self, parameter_id: ParameterId | None, cached=True
    ) -> ParameterType | None:
        """Get a cached parameter."""
        return self._parameters.get(parameter_id)

    async def update_parameters(self, parameters: set[ParameterId | None]):
        """Update parameter cache."""

        async def _get(parameter_id: ParameterId):
            self._parameters[parameter_id] = await self.uplink.get_parameter(
                self.system_id, parameter_id
            )

        tasks = [_get(parameter_id) for parameter_id in parameters if parameter_id]
        if tasks:
            await asyncio.gather(*tasks)

    def set_parameter(self, parameter_id: ParameterId, data: ParameterType | None):
        """Store a parameter in cache."""
        self._parameters[parameter_id] = data
        self._parameter_preload |= {parameter_id}

    def add_parameter_subscriber(
        self, parameters: set[ParameterId | None]
    ) -> CALLBACK_TYPE:
        """Add a subscriber for parameters."""
        sentinel = object()

        @callback
        def _remove():
            del self._parameter_subscribers[sentinel]

        parameters_clean = cast(set[ParameterId], (parameters - {None}))

        self._parameter_subscribers[sentinel] = parameters_clean
        for parameter in parameters_clean - set(self._parameters.keys()):
            self._parameters[parameter] = None

        return _remove
