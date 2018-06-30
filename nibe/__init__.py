"""
Support for nibe uplink.
"""


from datetime import timedelta
import logging
import sys
import time
import asyncio
import json
import voluptuous as vol
import traceback
from typing import List
import homeassistant.helpers.config_validation as cv

from homeassistant.const import (CONF_ACCESS_TOKEN,
                                 CONF_EMAIL,
                                 CONF_PASSWORD,
                                 EVENT_HOMEASSISTANT_START,
                                 EVENT_HOMEASSISTANT_STOP)
from homeassistant.helpers import discovery
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
from homeassistant.util.json import load_json, save_json
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components import persistent_notification
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.entity import (Entity, async_generate_entity_id)
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.core import callback
from homeassistant.const import (
    TEMP_CELSIUS,
    HTTP_OK,
    HTTP_BAD_REQUEST,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN              = 'nibe'
DATA_NIBE           = 'nibe'
INTERVAL            = timedelta(minutes=1)

REQUIREMENTS        = ['nibeuplink==0.4.1']

CONF_CLIENT_ID      = 'client_id'
CONF_CLIENT_SECRET  = 'client_secret'
CONF_REDIRECT_URI   = 'redirect_uri'
CONF_WRITEACCESS    = 'writeaccess'
CONF_CATEGORIES     = 'categories'
CONF_PARAMETERS     = 'parameters'
CONF_STATUSES       = 'statuses'
CONF_SYSTEMS        = 'systems'
CONF_SYSTEM         = 'system'
CONF_UNITS          = 'units'
CONF_UNIT           = 'unit'

SIGNAL_UPDATE       = 'nibe_update'

UNIT_SCHEMA = vol.Schema({
        vol.Required(CONF_UNIT): cv.positive_int,
        vol.Optional(CONF_CATEGORIES): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_STATUSES): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_PARAMETERS): vol.All(cv.ensure_list, [cv.positive_int])
})

SYSTEM_SCHEMA = vol.Schema({
        vol.Required(CONF_SYSTEM): cv.positive_int,
        vol.Optional(CONF_UNITS): vol.All(cv.ensure_list, [UNIT_SCHEMA]),
    })

NIBE_SCHEMA = vol.Schema({
            vol.Required(CONF_REDIRECT_URI): cv.string,
            vol.Required(CONF_CLIENT_ID): cv.string,
            vol.Required(CONF_CLIENT_SECRET): cv.string,
            vol.Required(CONF_CLIENT_SECRET): cv.string,
            vol.Optional(CONF_WRITEACCESS, default = False): cv.boolean,
            vol.Optional(CONF_SYSTEMS, default = []): vol.All(cv.ensure_list, [SYSTEM_SCHEMA]),
    })

CONFIG_SCHEMA = vol.Schema({
        DOMAIN: NIBE_SCHEMA
    }, extra=vol.ALLOW_EXTRA)

async def async_setup_systems(hass, config, uplink):

    if not len(config.get(CONF_SYSTEMS)):
        systems = await uplink.get_systems()
        msg = json.dumps(systems, indent=1)
        persistent_notification.async_create(hass, 'No systems selected, please configure one system id of:<br/><br/><pre>{}</pre>'.format(msg) , 'Invalid nibe config', 'invalid_config')
        return

    systems = [ NibeSystem(hass,
                           uplink,
                           config[CONF_SYSTEM],
                           config)
                     for config in config.get(CONF_SYSTEMS)
              ]

    hass.data[DATA_NIBE] = {}
    hass.data[DATA_NIBE]['systems'] = systems
    hass.data[DATA_NIBE]['uplink']  = uplink

    tasks = [ system.load() for system in systems ]

    await asyncio.gather(*tasks)


async def async_setup(hass, config):
    """Setup nibe uplink component"""

    store = hass.config.path('nibe.json')

    def save_json_local(data):
        save_json(store, data)

    from nibeuplink import Uplink

    scope = None
    if config[DOMAIN].get(CONF_WRITEACCESS):
        scope = ['READSYSTEM', 'WRITESYSTEM']
    else:
        scope = ['READSYSTEM']

    uplink = Uplink(
            client_id            = config[DOMAIN].get(CONF_CLIENT_ID),
            client_secret        = config[DOMAIN].get(CONF_CLIENT_SECRET),
            redirect_uri         = config[DOMAIN].get(CONF_REDIRECT_URI),
            access_data          = load_json(store),
            access_data_write    = save_json_local,
            scope                = scope
    )

    if not uplink.access_data:
        view = NibeAuthView(hass, uplink, config)
        hass.http.register_view(view)
        view.async_request_config()
    else:
        hass.async_add_job(async_setup_systems(hass, config[DOMAIN], uplink))

    return True


def filter_list(data: List[dict], field: str, selected: List[str]):
    """Return a filtered array based on existance in a filter list"""
    if len(selected):
        return [x for x in data if x[field] in selected]
    else:
        return data


class NibeSystem(object):
    def __init__(self, hass, uplink, system_id, config):
        self.hass       = hass
        self.parameters = {}
        self.config     = config
        self.system_id  = system_id
        self.system     = None
        self.uplink     = uplink
        self.notice     = []

    async def load_parameters(self, ids, entities, sensors: set):
        entity_ids = [ 'sensor.{}_{}_{}'.format(DOMAIN, self.system_id, str(sensor))
                        for sensor in ids
                     ]

        sensors.update(ids)
        entities.extend(entity_ids)

    async def load_parameter_group(self, name: str, object_id: str, parameters: List[dict], entities: list, sensors: set):
        group = self.hass.components.group
        ids = [c['parameterId'] for c in parameters]

        entity_ids = [ 'sensor.{}_{}_{}'.format(DOMAIN, self.system_id, str(sensor))
                        for sensor in ids
                     ]

        entity = await group.Group.async_create_group(
                        self.hass,
                        name       = name,
                        control    = False,
                        entity_ids = entity_ids,
                        object_id  = '{}_{}_{}'.format(DOMAIN, self.system_id, object_id))

        sensors.update(ids)
        entities.append(entity.entity_id)


    async def load_categories(self, unit: int, selected, entities: list, sensors: set):
        data   = await self.uplink.get_categories(self.system_id, True, unit)
        data   = filter_list(data, 'categoryId', selected)

        for x in data:
            await self.load_parameter_group(x['name'],
                                            '{}_{}'.format(unit, x['categoryId']),
                                            x['parameters'],
                                            entities,
                                            sensors)


    async def load_status(self, unit: int, entities: list, sensors: set):
        data   = await self.uplink.get_status(self.system_id, unit)

        for x in data:
            await self.load_parameter_group(x['title'],
                                            '{}_{}'.format(unit, x['title']),
                                            x['parameters'],
                                            entities,
                                            sensors)

    async def load(self):
        if not self.system:
            self.system = await self.uplink.get_system(self.system_id)

        sensors  = set()
        for unit in self.config.get(CONF_UNITS):
            entities = []
            if CONF_CATEGORIES in unit:
                await self.load_categories(
                    unit.get(CONF_UNIT),
                    unit.get(CONF_CATEGORIES),
                    entities,
                    sensors)

            if CONF_STATUSES in unit:
                await self.load_status(
                    unit.get(CONF_UNIT),
                    entities,
                    sensors)

            if CONF_PARAMETERS in unit:
                await self.load_parameters(
                    unit.get(CONF_PARAMETERS),
                    entities,
                    sensors)

            group = self.hass.components.group
            await group.Group.async_create_group(
                self.hass,
                '{} - Unit {}'.format(self.system['productName'], unit.get(CONF_UNIT)),
                user_defined = False,
                control      = False,
                view         = True,
                icon         = 'mdi:thermostat',
                object_id    = '{}_{}_{}'.format(DOMAIN, self.system_id, unit.get(CONF_UNIT)),
                entity_ids   = entities)

        if sensors:
            discovery_info = [
                { 'system_id'   : self.system['systemId'],
                  'parameter_id': sensor
                }
                for sensor in sensors
            ]

            await discovery.async_load_platform(
                self.hass,
                'sensor',
                DOMAIN,
                discovery_info)

        await self.update()
        async_track_time_interval(self.hass, self.update, INTERVAL)

    async def update(self, now = None):
        notice = await self.uplink.get_notifications(self.system_id)
        added   = [ k for k in notice      if k not in self.notice ]
        removed = [ k for k in self.notice if k not in notice ]
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

class NibeAuthView(HomeAssistantView):
    """Handle nibe  authentication callbacks."""

    url  = '/api/nibe/auth'
    name = 'api:nibe:auth'

    requires_auth = False

    def __init__(self, hass, uplink, config) -> None:
        """Initialize instance of the view."""
        super().__init__()
        self.hass           = hass
        self.uplink         = uplink
        self.config         = config
        self.request_id     = None

    def async_request_config(self):
        auth_uri    = self.uplink.get_authorize_url()

        description = """
Please authorize Home Assistant to access nibe uplink by following the authorization link.

Automatic configuration will only work if your configured redirect url is set to
a url that will match the access url of Home Assistant. If for example you access
Home Assisant on http://localhost:8123 you should set your callback url, both on Nibe
Uplink and in Home Assistant configuration, to http://localhost:8123/api/nibe/auth.

If automatic configuration of home assistant fails, you can enter the url to the webpage you
get redirected to in the below prompt.
"""

        self.request_id = self.hass.components.configurator.async_request_config(
            "Nibe Uplink authorization required",
            callback    = self.callback,
            description = description,
            link_name   = "Authorize",
            link_url    = auth_uri,
            fields      = [{'id': 'url', 'name': 'Full url', 'type': ''}],
            submit_caption = 'Manually set url'
        )

    async def configure(self, url):

        if not self.request_id:
            raise Exception('No Nibe configuration in progress!')

        try:
            code = self.uplink.get_code_from_url(url)

            await self.uplink.get_access_token(code)

            self.hass.components.configurator.async_request_done(self.request_id)
            self.hass.async_add_job(async_setup_systems(self.hass, self.config[DOMAIN], self.uplink))

        except:
            self.hass.components.configurator.async_notify_errors(self.request_id,
                "An error occured during nibe authorization. See logfile for more information.")
            raise

    async def callback(self, data):
        await self.configure(data['url'])

    
    async def get(self, request):
        """Handle oauth token request."""

        from aiohttp import web

        try:
            await self.configure(str(request.url))
        except:
            msg = "An error occured during nibe authorization."
            _LOGGER.exception(msg)
            return self.json_message(msg, status_code =HTTP_BAD_REQUEST)
        else:
            msg = "Nibe has been authorized! you can close this window, and restart Home Assistant."
            _LOGGER.info(msg)
            return self.json_message(msg, status_code =HTTP_OK)

