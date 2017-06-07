"""
Support for nibe uplink.
"""

import logging
import time
import json
import requests

from homeassistant.helpers.entity import Entity
from homeassistant.components.configurator import (request_config, notify_errors, request_done)

from homeassistant.const import (
    CONF_ACCESS_TOKEN, CONF_EMAIL, CONF_PASSWORD,
    EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP)
from oauth2client.client import (OAuth2WebServerFlow, FlowExchangeError)
from oauth2client.file import Storage



_LOGGER = logging.getLogger(__name__)

CHANNELS = []

DOMAIN = 'nibe'

REQUIREMENTS = ['oauth2client']

CONF_CLIENT_ID     = 'client_id'
CONF_CLIENT_SECRET = 'client_secret'
CONF_REDIRECT_URI  = 'redirect_uri'

BASE       = 'https://api.nibeuplink.com'


def setup(hass, config):
    """Setup nibe uplink component"""

    hass.data[DOMAIN] = NibeUplink(hass, config)
    return True

class NibeUplink(object):
    """Nibe System class."""

    def __init__(self, hass, config):
        """Initialize the system."""
        self.hass       = hass
        self.config     = None

        storage    = Storage(hass.config.path('nibe.token'))

        self.credential = storage.get()
        self.systems    = None

        if self.credential == None:
            flow = OAuth2WebServerFlow(client_id     = config[DOMAIN].get(CONF_CLIENT_ID),
                                       client_secret = config[DOMAIN].get(CONF_CLIENT_SECRET),
                                       scope         = 'READSYSTEM',
                                       redirect_uri  = config[DOMAIN].get(CONF_REDIRECT_URI),                                             state         = 'STATE',
                                       auth_uri      = '%s/oauth/authorize' % BASE,
                                       token_uri     = '%s/oauth/token'     % BASE)

            auth_uri = flow.step1_get_authorize_url()

            config = None

            def config_callback(data):
                _LOGGER.info(data)
                try:
                    self.credential = flow.step2_exchange(data['code'])
                    storage.put(self.credential)
                    request_done(config)
                    hass.add_job(self.update)
                except FlowExchangeError as error:
                    notify_errors(config, "An error occured: %s" % error)

            config = request_config(hass, "Nibe Uplink Code",
                            callback    = config_callback,
                            description = "Navigate to provided authorization link, this will redirect you to your configured redirect url. This must match what was setup in Nibe Uplink. Enter the [code] provided to that url here.",
                            link_name   = "Authorize",
                            link_url    = auth_uri,
                            fields      = [{'id': 'code', 'name': 'Code', 'type': ''}]
                        )
        else:
            hass.add_job(self.update)

    def update(self):
        if self.systems == None:
            _LOGGER.info("Requesting systems")
            self.systems = self.get('systems')
            _LOGGER.info(self.systems)

    def get(self, uri, params = {}):
        if self.credential == None:
            return None

        headers = {}
        self.credential.apply(headers)
        url = '%s/api/v1/%s' % (BASE, uri)
        _LOGGER.info(url)
        return requests.get(url, params=params, headers=headers).json()

