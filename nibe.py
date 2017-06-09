"""
Support for nibe uplink.
"""

import logging
import time
import json
import requests
import sys
import pickle

from homeassistant.helpers.entity import Entity
from homeassistant.components.configurator import (request_config, notify_errors, request_done)

from homeassistant.const import (
    CONF_ACCESS_TOKEN, CONF_EMAIL, CONF_PASSWORD,
    EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP)

from requests_oauthlib import OAuth2Session


_LOGGER = logging.getLogger(__name__)

CHANNELS = []

DOMAIN = 'nibe'

REQUIREMENTS = ['requests', 'requests_oauthlib']

CONF_CLIENT_ID     = 'client_id'
CONF_CLIENT_SECRET = 'client_secret'
CONF_REDIRECT_URI  = 'redirect_uri'

BASE       = 'https://api.nibeuplink.com'
SCOPE      = [ 'READSYSTEM' ]

TOKEN_URL  = '%s/oauth/token' % BASE
AUTH_URL   = '%s/oauth/authorize' % BASE


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
        self.credential = None
        self.systems    = None

        token = self.token_read()

        self.session = OAuth2Session(
                client_id        = config[DOMAIN].get(CONF_CLIENT_ID),
                redirect_uri     = config[DOMAIN].get(CONF_REDIRECT_URI),
                auto_refresh_url = TOKEN_URL,
                scope            = SCOPE,
                token            = token,
                token_updater    = self.token_write
        )

        if not self.session.authorized:
            auth_uri, state = self.session.authorization_url(AUTH_URL)

            config_request = None

            def config_callback(data):
                try:
                    token = self.session.fetch_token(
                                TOKEN_URL,
                                client_secret          = config[DOMAIN].get(CONF_CLIENT_SECRET),
                                authorization_response = data['url']
                    )

                    request_done(config_request)
                except:
                    notify_errors(config_request, "An error occured: %s" % sys.exc_info()[0])
                    return

                self.token_write(token)
                hass.add_job(self.update)



            config_request = request_config(hass, "Nibe Uplink Code",
                            callback    = config_callback,
                            description = "Navigate to provided authorization link, this will redirect you to your configured redirect url. This must match what was setup in Nibe Uplink. Enter the complete url you where redirected too here.",
                            link_name   = "Authorize",
                            link_url    = auth_uri,
                            fields      = [{'id': 'url', 'name': 'Full url', 'type': ''}]
                        )
        else:
            hass.add_job(self.update)

    def update(self):
        if self.systems == None:
            _LOGGER.info("Requesting systems")
            self.systems = self.get('systems')
            _LOGGER.info(self.systems)

    def get(self, uri, params = {}):
        if not self.session.authorized:
            return None

        headers = {}
        url = '%s/api/v1/%s' % (BASE, uri)
        return self.session.get(url, params=params, headers=headers).json()

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

