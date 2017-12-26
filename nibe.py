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

REQUIREMENTS        = ['nibeuplink==0.3.0']

CONF_CLIENT_ID      = 'client_id'
CONF_CLIENT_SECRET  = 'client_secret'
CONF_REDIRECT_URI   = 'redirect_uri'
CONF_WRITEACCESS    = 'writeaccess'
CONF_CATEGORIES     = 'categories'
CONF_PARAMETERS     = 'parameters'
CONF_STATUSES       = 'statuses'
CONF_SYSTEMS        = 'systems'
CONF_SYSTEM         = 'system'

SIGNAL_UPDATE       = 'nibe_update'

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=8)
MAX_REQUEST_PARAMETERS   = 15

SYSTEM_SCHEMA = vol.Schema({
        vol.Required(CONF_SYSTEM): cv.positive_int,
        vol.Optional(CONF_CATEGORIES): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_STATUSES): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_PARAMETERS): vol.All(cv.ensure_list, [cv.positive_int])
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

class NibeSystem(object):
    def __init__(self, hass, uplink, system_id, config):
        self.hass       = hass
        self.parameters = {}
        self.config     = config
        self.system_id  = system_id
        self.system     = None
        self.uplink     = uplink
        self.prefix     = "nibe_{}_".format(self.system_id)
        self.groups     = []
        self.notice     = []

    async def create_group(self, name, sensors):
        group = loader.get_component('group')

        entity_ids = [ 'sensor.' + self.prefix + str(sensor)
                        for sensor in sensors
                     ]

        return await group.Group.async_create_group(
                self.hass,
                name       = name,
                entity_ids = entity_ids,
                object_id  = self.prefix + name)

    async def load_parameters(self):
        sensors = set()
        sensors.update(self.config.get(CONF_PARAMETERS))
        return sensors

    async def load_categories(self):
        sensors = set()
        data    = await self.uplink.get_categories(self.system_id, True)

        for x in data:
            # Filter categories based on config if a category segment exist
            if len(self.config.get(CONF_CATEGORIES)) and \
               x['categoryId'] not in self.config.get(CONF_CATEGORIES):
                continue

            ids = [c['parameterId'] for c in x['parameters']]
            sensors.update(ids)
            self.groups.append(await self.create_group(x['name'], sensors = ids))

        return sensors

    async def load_status(self):
        sensors = set()
        data    = await self.uplink.get_status(self.system_id)

        for x in data:
            ids = [c['parameterId'] for c in x['parameters']]
            sensors.update(ids)
            self.groups.append(await self.create_group(x['image']['name'], sensors = ids))

        return sensors


    async def load(self):
        sensors = set()

        if not self.system:
            self.system = await self.uplink.get_system(self.system_id)

        if CONF_CATEGORIES in self.config:
            sensors.update(await self.load_categories())

        if CONF_PARAMETERS in self.config:
            sensors.update(await self.load_parameters())

        if CONF_STATUSES in self.config:
            sensors.update(await self.load_status())

        group = loader.get_component('group')
        await group.Group.async_create_group(
            self.hass,
            self.system['productName'],
            user_defined = False,
            view         = True,
            icon         = 'mdi:nest-thermostat',
            object_id    = self.prefix,
            entity_ids   = [g.entity_id for g in self.groups])

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

