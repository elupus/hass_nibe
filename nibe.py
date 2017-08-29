"""
Support for nibe uplink.
"""


from datetime import timedelta
from itertools import islice
import json
import logging
import os
import pickle
import sys
import time

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

_LOGGER = logging.getLogger(__name__)

DOMAIN              = 'nibe'

REQUIREMENTS        = ['requests', 'requests_oauthlib']

CONF_CLIENT_ID      = 'client_id'
CONF_CLIENT_SECRET  = 'client_secret'
CONF_REDIRECT_URI   = 'redirect_uri'
CONF_CATEGORIES     = 'categories'
CONF_SYSTEMS        = 'systems'
CONF_SYSTEM         = 'system'

BASE                = 'https://api.nibeuplink.com'
SCOPE               = [ 'READSYSTEM' ]

TOKEN_URL           = '%s/oauth/token' % BASE
AUTH_URL            = '%s/oauth/authorize' % BASE

AUTH_STR            = ("Navigate to provided authorization link, this"
                       " will redirect you to your configured redirect"
                       " url ('{}'). This must match what was setup in"
                       " Nibe Uplink. Enter the complete url you where"
                       " redirected too here.")

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=30)
MAX_REQUEST_PARAMETERS   = 15


SYSTEM_SCHEMA = vol.Schema({
        vol.Required(CONF_SYSTEM): cv.string,
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


#Allow insecure transport for OAuth callback url.
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def chunks(data, SIZE):
    it = iter(data)
    for i in range(0, len(data), SIZE):
        yield {k:data[k] for k in islice(it, SIZE)}

def setup(hass, config):
    """Setup nibe uplink component"""

    hass.data[DOMAIN] = NibeUplink(hass, config)
    return True

class NibeUplink(object):
    """Nibe System class."""

    def __init__(self, hass, config):
        """Initialize the system."""
        self.hass       = hass
        self.store      = hass.config.path('nibe.pickle')
        self.systems    = {}
        self.config     = config[DOMAIN]
        self.parameters = {}

        token = self.token_read()

        client_id     = config[DOMAIN].get(CONF_CLIENT_ID)
        client_secret = config[DOMAIN].get(CONF_CLIENT_SECRET)

        extra = {
            'client_id'    : client_id,
            'client_secret': client_secret,
        }

        from requests_oauthlib import OAuth2Session

        self.session = OAuth2Session(
                client_id            = client_id,
                redirect_uri         = self.config.get(CONF_REDIRECT_URI),
                auto_refresh_url     = TOKEN_URL,
                auto_refresh_kwargs  = extra,
                scope                = SCOPE,
                token                = token,
                token_updater        = self.token_write
        )

        if not token:
            auth_uri, state = self.session.authorization_url(AUTH_URL)

            config_request = None

            def config_callback(data):
                try:
                    token = self.session.fetch_token(
                                TOKEN_URL,
                                client_secret          = client_secret,
                                authorization_response = data['url']
                            )

                    hass.components.configurator.request_done(config_request)
                except:
                    hass.components.configurator.notify_errors(config_request, "An error occured: %s" % sys.exc_info()[0])
                    return

                self.token_write(token)
                hass.add_job(self.update_systems)



            config_request = hass.components.configurator.request_config(
                                "Nibe Uplink Code",
                                callback    = config_callback,
                                description = AUTH_STR.format(self.config.get(CONF_REDIRECT_URI)),
                                link_name   = "Authorize",
                                link_url    = auth_uri,
                                fields      = [{'id': 'url', 'name': 'Full url', 'type': ''}],
                                submit_caption = 'Set Url'
                             )

        else:
            hass.add_job(self.update_systems)

    def update_systems(self):


        _LOGGER.info("Requesting systems")
        systems = self.get('systems')

        configs = None
        if self.config.get(CONF_SYSTEMS):
            configs  = {
                str(system[CONF_SYSTEM]): system
                for system in self.config.get(CONF_SYSTEMS)
            }
        else:
            configs = {
                str(system['systemId']) : None
                for system in systems['objects']
            }

        self.systems = {
            str(system['systemId']) : NibeSystem(self.hass,
                                                 self,
                                                 system,
                                                 configs.get(str(system['systemId']))
                                      )
            for system in systems['objects'] if str(system['systemId']) in configs
        }


    def get(self, uri, params = {}):
        if not self.session.authorized:
            return None

        headers = {}
        url = '%s/api/v1/%s' % (BASE, uri)
        data = self.session.get(url, params=params, headers=headers).json()
        _LOGGER.debug(data)
        return data

    def get_parameter(self, system, parameter):
        if system not in self.systems:
            return None
        return self.systems[system].get_parameter(parameter)

    def token_read(self):
        try:
            with open(self.store, 'rb') as myfile:
                return pickle.load(myfile)
        except FileNotFoundError:
            return None
        except:
            _LOGGER.warning('Failed to load previous token: %s' % sys.exc_info()[0])
            return None

    def token_write(self, token):
        with open(self.store, 'wb') as myfile:
            pickle.dump(token, myfile)

class NibeSystem(object):
    def __init__(self, hass, uplink, system, config):
        self.hass       = hass
        self.parameters = {}
        self.categories = {}
        self.config     = config
        self.system     = system
        self.uplink     = uplink
        self.prefix     = "{}_".format(system['systemId'])
        self.groups     = []

        group = loader.get_component('group')

        self.update_categories()

        self.group = group.Group.create_group(
                        self.hass,
                        self.system['productName'],
                        user_defined = False,
                        view = True,
                        icon = 'mdi:nest-thermostat',
                        entity_ids = [g.entity_id for g in self.groups]
                     )

    def create_group(self, parameters, category):
        group = loader.get_component('group')

        entity_ids = [ 'sensor.{}{}'.format(self.prefix,
                                            parameter['parameterId'])

                        for parameter in parameters
                     ]

        g = group.Group.create_group(
                self.hass,
                "{} - {}".format(self.system['productName'],
                                 category['name']),
                entity_ids = entity_ids)
        self.groups.append(g)

    def get(self, uri, params = {}):
        return self.uplink.get('systems/{}/{}'.format(self.system['systemId'],
                                                      uri),
                               params = params)

    def update_categories(self):
        sensors = set()

        _LOGGER.info("Requesting categories on system {}".format(self.system['systemId']))

        categories = self.get('serviceinfo/categories')

        for category in categories:
            # Filter categories based on config if a category segment exist
            if self.config and \
               self.config.get(CONF_CATEGORIES) != None and \
               category['categoryId'] not in self.config.get(CONF_CATEGORIES):
                continue

            self.categories[category['categoryId']] = category

            _LOGGER.info("Requesting parameters for category: {} on system {}".format(
                                category['categoryId'],
                                self.system['systemId'])
                        )

            parameters = self.get('serviceinfo/categories/{}'.format(category['categoryId']))

            for parameter in parameters:
                self.parameters[parameter['parameterId']] = parameter
                sensors.add(parameter['parameterId'])

            self.create_group(parameters, category)


        discovery_info = [ { 'systemId'   : str(self.system['systemId']),
                             'parameterId': sensor
                           } for sensor in sensors
                         ]

        discovery.load_platform(
            self.hass,
            'sensor',
            DOMAIN,
            discovery_info)


    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update_parameters(self):
        _LOGGER.info("Requesting parameters for system {}".format(self.system['systemId']))
        for p in chunks(self.parameters, MAX_REQUEST_PARAMETERS):
            parameters = self.uplink.get(
                            'systems/{}/parameters'.format(self.system['systemId']),
                            { 'parameterIds' : p.keys() }
                       )

            for parameter in parameters:
                self.parameters[parameter['parameterId']] = parameter


    def get_parameter(self, parameter):
        self.update_parameters()

        if not parameter in self.parameters:
            self.parameters[parameter] = None

        return self.parameters[parameter]


