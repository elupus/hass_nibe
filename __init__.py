"""Support for nibe uplink."""

import attr
import asyncio
import logging
from typing import List, Dict, Union, T, Mapping

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.const import CONF_NAME
from nibeuplink import Uplink, UplinkSession

from .config_flow import NibeConfigFlow  # noqa
from .const import (
    CONF_ACCESS_DATA,
    CONF_BINARY_SENSORS,
    CONF_CATEGORIES,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CLIMATE_SYSTEMS,
    CONF_CLIMATES,
    CONF_CURRENT_TEMPERATURE,
    CONF_REDIRECT_URI,
    CONF_SENSORS,
    CONF_STATUSES,
    CONF_SWITCHES,
    CONF_SYSTEM,
    CONF_SYSTEMS,
    CONF_THERMOSTATS,
    CONF_UNIT,
    CONF_UNITS,
    CONF_VALVE_POSITION,
    CONF_WATER_HEATERS,
    CONF_WRITEACCESS,
    DATA_NIBE,
    DOMAIN,
    SCAN_INTERVAL,
    CONF_FANS,
    SIGNAL_PARAMETERS_UPDATED,
    SIGNAL_STATUSES_UPDATED,
)
from .services import async_register_services, async_track_delta_time

_LOGGER = logging.getLogger(__name__)


def none_as_true(data):
    """Return a none value as a truth."""
    if data is None:
        return True
    else:
        return cv.boolean(data)


def ensure_system_dict(value: Union[Dict[int, T], List[T], None]) -> Dict[int, T]:
    """Wrap value in list if it is not one."""
    if value is None:
        return {}
    if isinstance(value, list):
        value_schema = vol.Schema([
            vol.Schema({
                vol.Required(CONF_SYSTEM): cv.positive_int
            }, extra=vol.ALLOW_EXTRA)
        ])
        value = value_schema(value)
        return {
            x[CONF_SYSTEM]: x
            for x in value
        }
    if isinstance(value, dict):
        return value
    value = SYSTEM_SCHEMA(value)
    return {value[CONF_SYSTEM]: value}


UNIT_SCHEMA = vol.Schema(vol.All(
    cv.deprecated(CONF_STATUSES),
    {
        vol.Required(CONF_UNIT): cv.positive_int,
        vol.Optional(CONF_CATEGORIES, default=False): none_as_true,
        vol.Optional(CONF_STATUSES, default=False): none_as_true,
    }
))

THERMOSTAT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CLIMATE_SYSTEMS, default=[1]): vol.All(cv.ensure_list, [int]),
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_CURRENT_TEMPERATURE): cv.entity_id,
        vol.Optional(CONF_VALVE_POSITION): cv.entity_id,
    }
)

SYSTEM_SCHEMA = vol.Schema(vol.All(
    cv.deprecated(CONF_CLIMATES),
    cv.deprecated(CONF_WATER_HEATERS),
    cv.deprecated(CONF_FANS),
    {
        vol.Optional(CONF_SYSTEM): cv.positive_int,
        vol.Optional(CONF_UNITS, default=[]): vol.All(cv.ensure_list, [UNIT_SCHEMA]),
        vol.Optional(CONF_SENSORS, default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_CLIMATES): none_as_true,
        vol.Optional(CONF_WATER_HEATERS): none_as_true,
        vol.Optional(CONF_FANS): none_as_true,
        vol.Optional(CONF_SWITCHES, default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_BINARY_SENSORS, default=[]): vol.All(
            cv.ensure_list, [cv.string]
        ),
        vol.Optional(CONF_THERMOSTATS, default={}): {
            cv.positive_int: THERMOSTAT_SCHEMA
        },
    }
))

NIBE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_REDIRECT_URI): cv.string,
        vol.Optional(CONF_CLIENT_ID): cv.string,
        vol.Optional(CONF_CLIENT_SECRET): cv.string,
        vol.Optional(CONF_WRITEACCESS): cv.boolean,
        vol.Optional(CONF_SYSTEMS, default={}): vol.All(
            ensure_system_dict, {vol.Coerce(str): SYSTEM_SCHEMA}
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


@attr.s
class NibeData:
    """Holder for nibe data."""

    config = attr.ib()
    session = attr.ib(default=None, type=UplinkSession)
    uplink = attr.ib(default=None, type=Uplink)
    systems = attr.ib(default=[], type=List["NibeSystem"])


def _get_merged_config(config: Mapping, entry: config_entries.ConfigEntry):
    config = dict(config)
    if CONF_SYSTEMS in entry.data:
        for system in entry.data[CONF_SYSTEMS].keys():
            if system not in config[CONF_SYSTEMS]:
                config[CONF_SYSTEMS][system] = SYSTEM_SCHEMA({})
    return config


async def async_setup_systems(hass, data: NibeData, entry):
    """Configure each system."""
    config = _get_merged_config(data.config, entry)

    systems = {
        system_id: NibeSystem(
            hass, data.uplink, int(system_id), system_cfg, entry.entry_id
        )
        for system_id, system_cfg in config[CONF_SYSTEMS].items()
    }

    data.systems = systems

    tasks = [system.load() for system in systems.values()]

    await asyncio.gather(*tasks)

    for platform in FORWARD_PLATFORMS:
        hass.async_add_job(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )


async def async_setup(hass, config):
    """Configure the nibe uplink component."""
    if DOMAIN in config:
        data = NibeData(config[DOMAIN])
    else:
        data = NibeData(NIBE_SCHEMA({}))

    hass.data[DATA_NIBE] = data
    await async_register_services(hass)
    return True


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

    uplink = Uplink(session)

    data = hass.data[DATA_NIBE]
    data.session = session
    data.uplink = uplink

    await session.refresh_access_token()

    await async_setup_systems(hass, data, entry)

    return True


async def async_unload_entry(hass, entry):
    """Unload a configuration entity."""
    data = hass.data[DATA_NIBE]
    await asyncio.wait(
        [
            hass.config_entries.async_forward_entry_unload(entry, platform)
            for platform in FORWARD_PLATFORMS
        ]
    )

    await asyncio.wait([system.unload() for system in data.systems.values()])

    await data.session.close()
    data.systems = []
    data.uplink = None
    data.monitor = None
    return True


class NibeSystem(object):
    """Object representing a system."""

    def __init__(self, hass, uplink, system_id, config, entry_id):
        """Init."""
        self.hass = hass
        self.config = config
        self.system_id = system_id
        self.entry_id = entry_id
        self.system = None
        self.uplink = uplink
        self.notice = []
        self.statuses = set()
        self._device_info = {}
        self._unsub = []

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return self._device_info

    async def unload(self):
        """Unload system."""
        for unsub in reversed(self._unsub):
            unsub()
        self._unsub = []

    async def load(self):
        """Load system."""
        self.system = await self.uplink.get_system(self.system_id)
        _LOGGER.debug("Loading system: {}".format(self.system))

        self._device_info = {
            "identifiers": {(DOMAIN, self.system_id)},
            "manufacturer": "NIBE Energy Systems",
            "model": self.system.get("productName"),
            "name": f"{self.system.get('name')} - {self.system_id}",
        }

        device_registry = await self.hass.helpers.device_registry.async_get_registry()
        device_registry.async_get_or_create(
            config_entry_id=self.entry_id, **self._device_info
        )

        await self.update_notifications()
        await self.update_statuses()

        self._unsub.append(
            async_track_delta_time(self.hass, SCAN_INTERVAL, self.update_notifications)
        )
        self._unsub.append(
            async_track_delta_time(self.hass, SCAN_INTERVAL, self.update_statuses)
        )

    async def update_statuses(self):
        """Update status list."""
        status_icons = await self.uplink.get_status(self.system_id)
        parameters = {}
        statuses = set()
        for status_icon in status_icons:
            statuses.add(status_icon["title"])
            for parameter in status_icon["parameters"]:
                parameters[parameter["parameterId"]] = parameter
        self.statuses = statuses
        _LOGGER.debug("Statuses: %s", statuses)

        self.hass.helpers.dispatcher.async_dispatcher_send(
            SIGNAL_PARAMETERS_UPDATED, self.system_id, parameters
        )

        self.hass.helpers.dispatcher.async_dispatcher_send(
            SIGNAL_STATUSES_UPDATED, self.system_id, statuses
        )

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
