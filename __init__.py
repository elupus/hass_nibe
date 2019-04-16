"""Support for nibe uplink."""


import asyncio
import json
import logging
from datetime import timedelta

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.const import CONF_NAME
from homeassistant.helpers.event import async_track_time_interval

from .config import NibeConfigFlow  # noqa
from .const import (CONF_ACCESS_DATA, CONF_BINARY_SENSORS, CONF_CATEGORIES,
                    CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_CLIMATE_SYSTEMS,
                    CONF_CLIMATES, CONF_CURRENT_TEMPERATURE, CONF_REDIRECT_URI,
                    CONF_SENSORS, CONF_STATUSES, CONF_SWITCHES, CONF_SYSTEM,
                    CONF_SYSTEMS, CONF_THERMOSTATS, CONF_UNIT, CONF_UNITS,
                    CONF_VALVE_POSITION, CONF_WATER_HEATERS, CONF_WRITEACCESS,
                    DATA_NIBE, DOMAIN, SCAN_INTERVAL,
                    SIGNAL_PARAMETERS_UPDATED, SIGNAL_STATUSES_UPDATED)
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['group']
REQUIREMENTS = ['nibeuplink==0.6.3']


def none_as_true(data):
    """Return a none value as a truth."""
    if data is None:
        return True
    else:
        return cv.boolean(data)


UNIT_SCHEMA = vol.Schema({
    vol.Required(CONF_UNIT): cv.positive_int,
    vol.Optional(CONF_CATEGORIES, default=False): none_as_true,
    vol.Optional(CONF_STATUSES, default=False): none_as_true,
})

THERMOSTAT_SCHEMA = vol.Schema({
    vol.Optional(CONF_CLIMATE_SYSTEMS, default=[1]):
        vol.All(cv.ensure_list, [int]),
    vol.Required(CONF_NAME): str,
    vol.Optional(CONF_CURRENT_TEMPERATURE): cv.entity_id,
    vol.Optional(CONF_VALVE_POSITION): cv.entity_id,
})

SYSTEM_SCHEMA = vol.Schema({
    vol.Required(CONF_SYSTEM): cv.positive_int,
    vol.Optional(CONF_UNITS, default=[]):
        vol.All(cv.ensure_list, [UNIT_SCHEMA]),
    vol.Optional(CONF_SENSORS, default=[]):
        vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_CLIMATES, default=False): none_as_true,
    vol.Optional(CONF_WATER_HEATERS, default=False): none_as_true,
    vol.Optional(CONF_SWITCHES, default=[]):
        vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_BINARY_SENSORS, default=[]):
        vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_THERMOSTATS, default={}):
        {cv.positive_int: THERMOSTAT_SCHEMA},
})

NIBE_SCHEMA = vol.Schema({
    vol.Optional(CONF_REDIRECT_URI): cv.string,
    vol.Optional(CONF_CLIENT_ID): cv.string,
    vol.Optional(CONF_CLIENT_SECRET): cv.string,
    vol.Optional(CONF_WRITEACCESS): cv.boolean,
    vol.Optional(CONF_SYSTEMS, default=[]):
        vol.All(cv.ensure_list, [SYSTEM_SCHEMA]),
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: NIBE_SCHEMA
}, extra=vol.ALLOW_EXTRA)

FORWARD_PLATFORMS = ('climate', 'switch', 'sensor',
                     'binary_sensor', 'water_heater')


async def async_setup_systems(hass, uplink, entry):
    """Configure each system."""
    config = hass.data[DATA_NIBE]['config']

    if not len(config.get(CONF_SYSTEMS)):
        systems = await uplink.get_systems()
        msg = json.dumps(systems, indent=1)
        persistent_notification.async_create(
            hass,
            ('No systems selected, please configure one system id of:'
             '<br/><br/><pre>{}</pre>').format(msg),
            'Invalid nibe config',
            'invalid_config')
        return

    systems = {
        config[CONF_SYSTEM]:
            NibeSystem(hass,
                       uplink,
                       config[CONF_SYSTEM],
                       config,
                       entry.entry_id)
        for config in config.get(CONF_SYSTEMS)
    }

    hass.data[DATA_NIBE]['systems'] = systems
    hass.data[DATA_NIBE]['uplink'] = uplink

    tasks = [system.load() for system in systems.values()]

    await asyncio.gather(*tasks)

    for platform in FORWARD_PLATFORMS:
        hass.async_add_job(hass.config_entries.async_forward_entry_setup(
            entry, platform))


async def async_setup(hass, config):
    """Configure the nibe uplink component."""
    hass.data[DATA_NIBE] = {}
    hass.data[DATA_NIBE]['config'] = config[DOMAIN]

    """Monkey patch hass to get detected"""
    config_entries.FLOWS.append(DOMAIN)

    """
    Monkey patch history component to get full state history.
    https://github.com/home-assistant/home-assistant/pull/21390
    """
    import homeassistant.components.history as history
    if 'water_heater' not in history.SIGNIFICANT_DOMAINS:
        history.SIGNIFICANT_DOMAINS = (*history.SIGNIFICANT_DOMAINS,
                                       'water_heater')

    await async_register_services(hass)
    return True


async def async_setup_entry(hass, entry: config_entries.ConfigEntry):
    """Set up an access point from a config entry."""
    _LOGGER.debug("Setup nibe entry")

    from nibeuplink import Uplink

    scope = None
    if entry.data.get(CONF_WRITEACCESS):
        scope = ['READSYSTEM', 'WRITESYSTEM']
    else:
        scope = ['READSYSTEM']

    def access_data_write(data):
        hass.config_entries.async_update_entry(
            entry, data={
                **entry.data, CONF_ACCESS_DATA: data
            })

    uplink = Uplink(
        client_id=entry.data.get(CONF_CLIENT_ID),
        client_secret=entry.data.get(CONF_CLIENT_SECRET),
        redirect_uri=entry.data.get(CONF_REDIRECT_URI),
        access_data=entry.data.get(CONF_ACCESS_DATA),
        access_data_write=access_data_write,
        scope=scope
    )

    await uplink.refresh_access_token()

    await async_setup_systems(hass, uplink, entry)

    return True


async def async_unload_entry(hass, entry):
    """Unload a configuration entity."""
    await asyncio.wait([
        hass.config_entries.async_forward_entry_unload(
            entry, platform)
        for platform in FORWARD_PLATFORMS
    ])

    await asyncio.wait([
        system.unload()
        for system in hass.data[DATA_NIBE]['systems'].values()
    ])

    await hass.data[DATA_NIBE]['uplink'].close()
    del hass.data[DATA_NIBE]['systems']
    del hass.data[DATA_NIBE]['uplink']
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

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return self._device_info

    async def unload(self):
        """Unload system."""
        pass

    async def load(self):
        """Load system."""
        self.system = await self.uplink.get_system(self.system_id)
        _LOGGER.debug("Loading system: {}".format(self.system))

        self._device_info = {
            'identifiers': {(DOMAIN, self.system_id)},
            'manufacturer': "NIBE Energy Systems",
            'model': self.system.get('productName'),
            'name': self.system.get('name'),
        }

        device_registry = await \
            self.hass.helpers.device_registry.async_get_registry()
        device_registry.async_get_or_create(
            config_entry_id=self.entry_id,
            **self._device_info
        )

        await self.update()
        async_track_time_interval(
            self.hass,
            self.update,
            timedelta(seconds=SCAN_INTERVAL))

    async def update_statuses(self):
        """Update status list."""
        status_icons = await self.uplink.get_status(self.system_id)
        parameters = {}
        statuses = set()
        for status_icon in status_icons:
            statuses.add(status_icon['title'])
            for parameter in status_icon['parameters']:
                parameters[parameter['parameterId']] = parameter
        self.statuses = statuses
        _LOGGER.debug("Statuses: %s", statuses)

        self.hass.helpers.dispatcher.async_dispatcher_send(
            SIGNAL_PARAMETERS_UPDATED, parameters)

        self.hass.helpers.dispatcher.async_dispatcher_send(
            SIGNAL_STATUSES_UPDATED, statuses)

    async def update_notifications(self):
        """Update notification list."""
        notice = await self.uplink.get_notifications(self.system_id)
        added = [k for k in notice if k not in self.notice]
        removed = [k for k in self.notice if k not in notice]
        self.notice = notice

        for x in added:
            persistent_notification.async_create(
                self.hass,
                x['info']['description'],
                x['info']['title'],
                'nibe:{}'.format(x['notificationId'])
            )
        for x in removed:
            persistent_notification.async_dismiss(
                self.hass,
                'nibe:{}'.format(x['notificationId'])
            )

    async def update(self, now=None):
        """Update system state."""
        await self.update_notifications()
        await self.update_statuses()
