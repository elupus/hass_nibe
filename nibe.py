"""
Support for nibe uplink.
"""


from datetime import timedelta
import logging
import sys
import time
import asyncio

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.const import (CONF_ACCESS_TOKEN,
                                 CONF_EMAIL,
                                 CONF_PASSWORD,
                                 EVENT_HOMEASSISTANT_START,
                                 EVENT_HOMEASSISTANT_STOP)
from homeassistant.helpers import discovery
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
import homeassistant.loader as loader
from homeassistant.util.json import load_json, save_json
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

DOMAIN              = 'nibe'

REQUIREMENTS        = ['requests', 'requests_oauthlib', 'nibeuplink']

CONF_CLIENT_ID      = 'client_id'
CONF_CLIENT_SECRET  = 'client_secret'
CONF_REDIRECT_URI   = 'redirect_uri'
CONF_CATEGORIES     = 'categories'
CONF_SYSTEMS        = 'systems'
CONF_SYSTEM         = 'system'

SIGNAL_UPDATE       = 'nibe_update'

AUTH_STR            = ("Navigate to provided authorization link, this"
                       " will redirect you to your configured redirect"
                       " url ('{}'). This must match what was setup in"
                       " Nibe Uplink. Enter the complete url you where"
                       " redirected too here.")

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=8)
MAX_REQUEST_PARAMETERS   = 15


SYSTEM_SCHEMA = vol.Schema({
        vol.Required(CONF_SYSTEM): cv.positive_int,
        vol.Optional(CONF_CATEGORIES): vol.All(cv.ensure_list, [cv.string])
    })

NIBE_SCHEMA = vol.Schema({
            vol.Required(CONF_REDIRECT_URI): cv.string,
            vol.Required(CONF_CLIENT_ID): cv.string,
            vol.Required(CONF_CLIENT_SECRET): cv.string,
            vol.Optional(CONF_SYSTEMS): vol.All(cv.ensure_list, [SYSTEM_SCHEMA]),
    })

CONFIG_SCHEMA = vol.Schema({
        DOMAIN: NIBE_SCHEMA
    }, extra=vol.ALLOW_EXTRA)


@asyncio.coroutine
def async_setup(hass, config):
    """Setup nibe uplink component"""

    store = hass.config.path('nibe.json')

    def save_json_local(data):
        save_json(store, data)

    from nibeuplink import Uplink

    uplink = Uplink(
            client_id            = config[DOMAIN].get(CONF_CLIENT_ID),
            client_secret        = config[DOMAIN].get(CONF_CLIENT_SECRET),
            redirect_uri         = config[DOMAIN].get(CONF_REDIRECT_URI),
            access_data          = load_json(store),
            access_data_write    = save_json_local
    )

    if not uplink.access_data:
        auth_uri = uplink.get_authorize_url()

        config_request = None

        async def config_callback(data):
            try:
                await uplink.get_access_token(uplink.get_code_from_url(data))
                hass.components.configurator.request_done(config_request)
            except:
                hass.components.configurator.notify_errors(config_request, "An error occured: %s" % sys.exc_info()[0])
                return

            hass.data[DOMAIN] = NibeUplink(hass, config, uplink)

        config_request = hass.components.configurator.async_request_config(
                            "Nibe Uplink Code",
                            callback    = config_callback,
                            description = AUTH_STR.format(self.config.get(CONF_REDIRECT_URI)),
                            link_name   = "Authorize",
                            link_url    = auth_uri,
                            fields      = [{'id': 'url', 'name': 'Full url', 'type': ''}],
                            submit_caption = 'Set Url'
                         )
    else:
        hass.data[DOMAIN] = NibeUplink(hass, config, uplink)

    return True

class NibeUplink(object):
    """Nibe System class."""

    def __init__(self, hass, config, uplink):
        """Initialize the system."""
        self.hass       = hass
        self.uplink     = uplink
        self.systems    = []
        self.config     = config[DOMAIN]
        self.parameters = {}

        hass.add_job(self.load)


    async def load(self):
        systems = await self.uplink.get_systems()

        if self.config.get(CONF_SYSTEMS):
            self.systems = [ NibeSystem(self.hass,
                                        self.uplink,
                                        config[CONF_SYSTEM],
                                        config)
                             for config in self.config.get(CONF_SYSTEMS)
                           ]
        else:
            self.systems = [ NibeSystem(self.hass,
                                        self.uplink,
                                        system,
                                        None)
                             for system in systems
                           ]
        tasks = [ system.load() for system in self.systems ]

        await asyncio.gather(*tasks)


class NibeSystem(object):
    def __init__(self, hass, uplink, system, config):
        self.hass       = hass
        self.parameters = {}
        self.config     = config
        self.system     = system
        self.uplink     = uplink
        self.prefix     = "{}_".format(system['systemId'])
        self.groups     = []

        group = loader.get_component('group')

    async def create_group(self, parameters, category):
        group = loader.get_component('group')

        entity_ids = [ 'sensor.{}{}'.format(self.prefix,
                                            parameter)

                        for parameter in parameters
                     ]

        return await group.Group.async_create_group(
                self.hass,
                "{} - {}".format(self.system['productName'],
                                 category['name']),
                entity_ids = entity_ids)

    async def load(self):
        sensors = set()

        data = await self.uplink.get_categories(self.system['systemId'])
        group_tasks = []
        for category in data:
            # Filter categories based on config if a category segment exist
            if self.config and \
               self.config.get(CONF_CATEGORIES) != None and \
               category['category_id'] not in self.config.get(CONF_CATEGORIES):
                continue

            parameter_ids = [c['parameterId'] for c in category['parameters']]
            sensors.update(parameter_ids)

            group_tasks.append(self.create_group(parameter_ids, category))

        self.groups = await asyncio.gather(*group_tasks, loop = self.hass.loop)

        group = loader.get_component('group')
        await group.Group.async_create_group(
            self.hass,
            self.system['productName'],
            user_defined = False,
            view = True,
            icon = 'mdi:nest-thermostat',
            entity_ids = [g.entity_id for g in self.groups])

        discovery_info = [ { 'system_id': self.system['systemId'], 'parameter_id': sensor } for sensor in sensors ]

        self.hass.async_add_job(discovery.async_load_platform(
            self.hass,
            'sensor',
            DOMAIN,
            discovery_info))

        #async_track_time_interval(self.hass, self.update, MIN_TIME_BETWEEN_UPDATES)

    async def update(self, call):
        _LOGGER.debug("Refreshing system {}".format(self.system.system_id))
        await self.uplink.update_categories(self.system.system_id)
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

