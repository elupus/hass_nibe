"""
Support for nibe uplink.
"""

import logging
import time
import json
import requests

from homeassistant.helpers.entity import Entity
from homeassistant.const import (
    CONF_ACCESS_TOKEN, CONF_EMAIL, CONF_PASSWORD,
    EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP)
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage

from homeassistant.helpers.entity import Entity


_LOGGER = logging.getLogger(__name__)

CHANNELS = []

DOMAIN = 'nibe'

REQUIREMENTS = ['oauth2client']

CONF_CLIENT_ID     = 'client_id'
CONF_CLIENT_SECRET = 'client_secret'

CREDENTIAL = None
BASE       = 'https://api.nibeuplink.com'

def setup(hass, config):
    """Setup nibe uplink component"""

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]['entities'] = []
    hass.data[DOMAIN]['unique_ids'] = []

    storage    = Storage('nibe_store')
    global CREDENTIAL

    CREDENTIAL = storage.get()

    if CREDENTIAL == None:
        flow = OAuth2WebServerFlow(client_id     = config[DOMAIN].get(CONF_CLIENT_ID),
                                   client_secret = config[DOMAIN].get(CONF_CLIENT_SECRET),
                                   scope         = 'READSYSTEM',
                                   redirect_uri  = 'https://www.marshflattsfarm.org.uk/nibeuplink/oauth2callback/index.php',
                                   state         = 'STATE',
                                   auth_uri      = '%s/oauth/authorize' % BASE,
                                   token_uri     = '%s/oauth/token'     % BASE)


        code =  config[DOMAIN].get("code")

        if code == None:
            auth_uri = flow.step1_get_authorize_url()
            _LOGGER.info("Navigate to url to get access code: %s" % auth_uri)
            return False

        CREDENTIAL = flow.step2_exchange(code)
        storage.put(CREDENTIAL)


    hass.data[DOMAIN] = NibeUplink()


    return True

class NibeUplink(object):
    """Nibe System class."""

    def __init__(self):
        """Initialize the system."""

        _LOGGER.info("Requesting systems")

        systems = self.get('systems')

        _LOGGER.info(systems)

    def get(self, uri, params = {}):
        headers = {}
        CREDENTIAL.apply(headers)
        url = '%s/api/v1/%s' % (BASE, uri)
        _LOGGER.info(url)
        return requests.get(url, params=params, headers=headers).json()

