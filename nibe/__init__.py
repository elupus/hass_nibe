"""
Support for nibe uplink.
"""


from datetime import timedelta
import logging
import asyncio
import json
import voluptuous as vol
from typing import (List, Iterable)
from collections import defaultdict
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries
from homeassistant.core import split_entity_id
from homeassistant.components.group import (
    ATTR_ADD_ENTITIES, ATTR_OBJECT_ID,
    DOMAIN as DOMAIN_GROUP, SERVICE_SET)
from homeassistant.loader import bind_hass
from homeassistant.helpers import discovery
from homeassistant.util.json import load_json, save_json
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components import persistent_notification

from .auth import NibeAuthView
from .const import *
from .config import configured_hosts

_LOGGER = logging.getLogger(__name__)

config_entries.FLOWS.append(DOMAIN)

INTERVAL            = timedelta(minutes=1)

DEPENDENCIES = ['group']
REQUIREMENTS        = ['nibeuplink==0.4.3']


SIGNAL_UPDATE       = 'nibe_update'

BINARY_SENSOR_VALUES = ('off', 'on', 'yes', 'no')

UNIT_SCHEMA = vol.Schema({
    vol.Required(CONF_UNIT): cv.positive_int,
    vol.Optional(CONF_CATEGORIES): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_STATUSES): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_SENSORS, default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_CLIMATES): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_SWITCHES, default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_BINARY_SENSORS, default=[]): vol.All(cv.ensure_list, [cv.string]),
})

SYSTEM_SCHEMA = vol.Schema({
    vol.Required(CONF_SYSTEM): cv.positive_int,
    vol.Optional(CONF_UNITS, default=[]):
        vol.All(cv.ensure_list, [UNIT_SCHEMA]),
})

NIBE_SCHEMA = vol.Schema({
    vol.Optional(CONF_SYSTEMS, default=[]):
        vol.All(cv.ensure_list, [SYSTEM_SCHEMA]),
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: NIBE_SCHEMA
}, extra=vol.ALLOW_EXTRA)


async def async_setup_systems(hass, uplink, entry):
    config = hass.data[DATA_NIBE]['config']

    if not len(config.get(CONF_SYSTEMS)):
        systems = await uplink.get_systems()
        msg = json.dumps(systems, indent=1)
        persistent_notification.async_create(hass, 'No systems selected, please configure one system id of:<br/><br/><pre>{}</pre>'.format(msg) , 'Invalid nibe config', 'invalid_config')
        return

    systems = {
        config[CONF_SYSTEM]:
            NibeSystem(hass,
                       uplink,
                       config[CONF_SYSTEM],
                       config)
        for config in config.get(CONF_SYSTEMS)
    }

    hass.data[DATA_NIBE]['systems'] = systems
    hass.data[DATA_NIBE]['uplink'] = uplink

    tasks = [system.load() for system in systems.values()]

    await asyncio.gather(*tasks)

    for platform in ('climate', 'switch', 'sensor', 'binary_sensor'):
        hass.async_add_job(hass.config_entries.async_forward_entry_setup(
            entry, platform))


async def async_setup(hass, config):
    """Setup nibe uplink component"""
    hass.data[DATA_NIBE] = {}
    hass.data[DATA_NIBE]['config'] = config[DOMAIN]
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

    uplink = Uplink(
        client_id = entry.data.get(CONF_CLIENT_ID),
        client_secret = entry.data.get(CONF_CLIENT_SECRET),
        redirect_uri = entry.data.get(CONF_REDIRECT_URI),
        refresh_token = entry.data.get(CONF_REFRESH_TOKEN),
        scope = scope
    )

    await uplink.refresh_access_token()

    await async_setup_systems(hass, uplink, entry)

    return True


async def async_unload_entry(hass, entry):
    pass


def filter_list(data: List[dict], field: str, selected: List[str]):
    """Return a filtered array based on existance in a filter list"""
    if len(selected):
        return [x for x in data if x[field] in selected]
    else:
        return data


def gen_dict():
    return {'groups': [], 'data': None}


class NibeSystem(object):
    def __init__(self, hass, uplink, system_id, config):
        self.hass = hass
        self.parameters = {}
        self.config = config
        self.system_id = system_id
        self.system = None
        self.uplink = uplink
        self.notice = []
        self.discovered = defaultdict(set)
        self.switches = defaultdict(gen_dict)
        self.sensors = defaultdict(gen_dict)
        self.binary_sensors = defaultdict(gen_dict)
        self.climates = defaultdict(gen_dict)
        self._device_info = {}

    def filter_discovered(self, discovery_info, platform):
        """Keep unique discovery list, to avoid duplicate loads"""
        table = self.discovered[platform]
        for entry in discovery_info:
            object_id = entry.get(CONF_OBJECTID)
            if object_id in table:
                continue
            table.add(object_id)
            yield entry

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return self._device_info

    async def load_parameter_group(self,
                                   name: str,
                                   object_id: str,
                                   parameters: List[dict]):

        group = self.hass.components.group
        entity = await group.Group.async_create_group(
            self.hass,
            name=name,
            control=False,
            object_id='{}_{}_{}'.format(DOMAIN, self.system_id, object_id))

        _, group_id = split_entity_id(entity.entity_id)

        for x in parameters:
            if str(x['value']).lower() in BINARY_SENSOR_VALUES:
                list_object = self.binary_sensors
            else:
                list_object = self.sensors

            entry = list_object[x['parameterId']]
            entry['data'] = x
            entry['groups'].append(group_id)
            _LOGGER.debug("Entry {}".format(entry))

        return entity.entity_id

    async def load_categories(self,
                              unit: int,
                              selected):
        data = await self.uplink.get_categories(self.system_id, True, unit)
        data = filter_list(data, 'categoryId', selected)
        tasks = [
            self.load_parameter_group(
                x['name'],
                '{}_{}'.format(unit, x['categoryId']),
                x['parameters'])
            for x in data
        ]
        return await asyncio.gather(*tasks)

    async def load_status(self,
                          unit: int):
        data = await self.uplink.get_unit_status(self.system_id, unit)
        tasks = [
            self.load_parameter_group(
                x['title'],
                '{}_{}'.format(unit, x['title']),
                x['parameters'])
            for x in data
        ]
        return await asyncio.gather(*tasks)

    async def load_climates(self, selected, group_id):
        from nibeuplink import (PARAM_CLIMATE_SYSTEMS)

        async def get_active(id):
            if selected and id not in selected:
                return None

            climate = PARAM_CLIMATE_SYSTEMS[id]
            if climate.active_accessory is None:
                return id

            active_accessory = await self.uplink.get_parameter(
                self.system_id,
                climate.active_accessory)

            _LOGGER.debug("Accessory status for {} is {}".format(
                climate.name,
                active_accessory))

            if active_accessory and active_accessory['rawValue']:
                return id

            return None

        climates = await asyncio.gather(*[
            get_active(climate)
            for climate in PARAM_CLIMATE_SYSTEMS.keys()
        ])

        for climate in climates:
            if climate:
                self.climates[climate]['groups'].append(group_id)

    async def load_unit(self, unit):

        group = self.hass.components.group
        entity = await group.Group.async_create_group(
            self.hass,
            '{} - Unit {}'.format(self.system['productName'],
                                  unit.get(CONF_UNIT)),
            user_defined=False,
            control=False,
            view=True,
            icon='mdi:thermostat',
            object_id='{}_{}_{}'.format(DOMAIN,
                                        self.system_id,
                                        unit.get(CONF_UNIT)))

        _, object_id = split_entity_id(entity.entity_id)

        for parameter in unit[CONF_SWITCHES]:
            self.switches[parameter]['groups'] = [object_id]

        for parameter in unit[CONF_SENSORS]:
            self.sensors[parameter]['groups'] = [object_id]

        for parameter in unit[CONF_BINARY_SENSORS]:
            self.binary_sensors[parameter]['groups'] = [object_id]

        if CONF_CLIMATES in unit:
            await self.load_climates(
                unit[CONF_CLIMATES],
                object_id)

        entity_ids = []
        if CONF_CATEGORIES in unit:
            entity_ids.extend(
                await self.load_categories(
                    unit.get(CONF_UNIT),
                    unit.get(CONF_CATEGORIES)))

        if CONF_STATUSES in unit:
            entity_ids.extend(
                await self.load_status(
                    unit.get(CONF_UNIT)))

        self.hass.async_add_job(
            self.hass.services.async_call(
                DOMAIN_GROUP, SERVICE_SET, {
                    ATTR_OBJECT_ID: object_id,
                    ATTR_ADD_ENTITIES: entity_ids})
        )

    async def load(self):
        if not self.system:
            self.system = await self.uplink.get_system(self.system_id)
            _LOGGER.debug("Loading system: {}".format(self.system))

            self._device_info = {
                'identifiers': {("system_id", self.system_id)},
                'manufacturer': "NIBE Energy Systems",
                'model': self.system.get('productName'),
                'name': self.system.get('name'),
            }

        for unit in self.config.get(CONF_UNITS):
            await self.load_unit(unit)

        await self.update()
        async_track_time_interval(self.hass, self.update, INTERVAL)

    async def update(self, now=None):
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
                'nibe:{}'.format(x['notificationId'])
            )
