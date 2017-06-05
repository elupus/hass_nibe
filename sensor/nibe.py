import logging
import time
import json
import requests

from homeassistant.helpers.entity import Entity
from oauth2client.client import OAuth2WebServerFlow
from homeassistant.helpers.entity import Entity
from homeassistant.const import TEMP_CELSIUS

DEPENDENCIES = ['nibe']
DOMAIN       = 'nibe'
_LOGGER      = logging.getLogger(__name__)

def setup_platform(hass, config, add_devices, discovery_info=None):
    add_devices([NibeSensor(hass.data[DOMAIN])])

class NibeSensor(Entity):
    def __init__(self, uplink):
        """Initialize the Nibe sensor."""
        self._state     = 0
        self._system    = 36563
        self._parameter = 1
        self._uplink    = uplink

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'Example Temperature'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """

        data = self._uplink.get('systems/%d/parameters' % self._system, { 'parameterIds': self._parameter } )
        _LOGGER.info(data)

        self._state = 23

