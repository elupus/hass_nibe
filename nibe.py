"""
Support for nibe uplink.
"""


from datetime import timedelta
from itertools import islice
import json
import logging
import os
import pickle
import requests
import sys
import time

from homeassistant.components.configurator import (request_config, notify_errors, request_done)
from homeassistant.const import (CONF_ACCESS_TOKEN,
                                 CONF_EMAIL,
                                 CONF_PASSWORD,
                                 EVENT_HOMEASSISTANT_START,
                                 EVENT_HOMEASSISTANT_STOP)
from homeassistant.helpers import discovery
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
import homeassistant.loader as loader

from requests_oauthlib import OAuth2Session


_LOGGER = logging.getLogger(__name__)

DOMAIN              = 'nibe'

REQUIREMENTS        = ['requests', 'requests_oauthlib']

CONF_CLIENT_ID      = 'client_id'
CONF_CLIENT_SECRET  = 'client_secret'
CONF_REDIRECT_URI   = 'redirect_uri'
CONF_CATEGORIES     = 'categories'

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
        self.systems    = None
        self.redirect   = config[DOMAIN].get(CONF_REDIRECT_URI)
        self.categories = config[DOMAIN].get(CONF_CATEGORIES, ['STATUS'])
        self.parameters = {}

        token = self.token_read()

        client_id     = config[DOMAIN].get(CONF_CLIENT_ID)
        client_secret = config[DOMAIN].get(CONF_CLIENT_SECRET)

        extra = {
            'client_id'    : client_id,
            'client_secret': client_secret,
        }

        self.session = OAuth2Session(
                client_id            = client_id,
                redirect_uri         = self.redirect,
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

                    request_done(config_request)
                except:
                    notify_errors(config_request, "An error occured: %s" % sys.exc_info()[0])
                    return

                self.token_write(token)
                hass.add_job(self.update_systems)



            config_request = request_config(
                                hass,
                                "Nibe Uplink Code",
                                callback    = config_callback,
                                description = AUTH_STR.format(self.redirect),
                                link_name   = "Authorize",
                                link_url    = auth_uri,
                                fields      = [{'id': 'url', 'name': 'Full url', 'type': ''}]
                             )

        else:
            hass.add_job(self.update_systems)

    def update_systems(self):

        group = loader.get_component('group')

        _LOGGER.info("Requesting systems")
        self.systems = self.get('systems')

        sensors = []

        for system in self.systems['objects']:
            self.parameters[system['systemId']] = {}
            for category in self.categories:
                _LOGGER.info("Requesting category: {}".format(category))
                parameters = self.get_category(system['systemId'], category)

                for parameter in parameters:
                    self.parameters[system['systemId']][parameter['parameterId']] = parameter

                data = ([ { 'systemId'   : system['systemId'],
                            'parameterId': parameter['parameterId']
                          } for parameter in parameters
                        ])

                entity_ids = [ 'sensor.{}_{}'.format(system['systemId'],
                                                     parameter['parameterId'])
                                for parameter in parameters
                             ]

                group.Group.create_group(
                        self.hass,
                        "{} - {}".format(system['productName'], category),
                        entity_ids)

                sensors.extend(data)

        discovery.load_platform(
            self.hass,
            'sensor',
            DOMAIN,
            sensors)


    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update_parameters(self):
        _LOGGER.info("Requesting parameters")
        for system, parameters in self.parameters.items():
            for p in chunks(parameters, 15):
                datas = self.get('systems/%s/parameters' % system, { 'parameterIds' : p.keys() } )

                for data in datas:
                    parameters[data['parameterId']] = data

    def get(self, uri, params = {}):
        if not self.session.authorized:
            return None

        headers = {}
        url = '%s/api/v1/%s' % (BASE, uri)
        data = self.session.get(url, params=params, headers=headers).json()
        _LOGGER.debug(data)
        return data

    def get_category(self, system, category):
        return self.get('systems/%s/serviceinfo/categories/%s' % (system, category))

    def get_parameter(self, system, parameter):
        if not system in self.parameters:
            self.parameters[system] = {}

        if not parameter in self.parameters[system]:
            self.parameters[system][parameter] = None

        self.update_parameters()

        return self.parameters[system][parameter] 

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

