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
    add_devices([
        NibeSensor(hass.data[DOMAIN], 36563, 'outdoor_temperature'),
        NibeSensor(hass.data[DOMAIN], 36563, 'hot_water_temperature')
        ])

class NibeSensor(Entity):
    def __init__(self, uplink, system, parameter):
        """Initialize the Nibe sensor."""
        self._state     = 0
        self._system    = system
        self._parameter = parameter
        self._uplink    = uplink
        self._name      = parameter
        self._unit      = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """

        data = self._uplink.get('systems/%d/parameters' % self._system, { 'parameterIds': self._parameter } )
        _LOGGER.info(data)


        self._name  = data[0]['title']

        if (data[0]['unit'] == '°C'):
            self._unit  = TEMP_CELSIUS
            self._state = data[0]['rawValue'] / 10
        else:
            self._unit  = None
            self._state = data[0]['displayValue']
