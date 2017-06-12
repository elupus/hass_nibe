import logging
import time
import json
import requests

from homeassistant.helpers.entity import (Entity, generate_entity_id)
from oauth2client.client import OAuth2WebServerFlow
from homeassistant.helpers.entity import Entity
from homeassistant.const import TEMP_CELSIUS
from homeassistant.components.sensor import ENTITY_ID_FORMAT

DEPENDENCIES = ['nibe']
DOMAIN       = 'nibe'
_LOGGER      = logging.getLogger(__name__)


CONF_SYSTEM    = 'system'
CONF_PARAMETER = 'parameter'
CONF_CATEGORY  = 'category'

SCALE = {
        '°C' : { 'scale' : 10, 'unit': TEMP_CELSIUS },
        'A'  : { 'scale' : 10, 'unit': 'A'          },
        'DM' : { 'scale' : 10, 'unit': 'DM'         },
}

def setup_platform(hass, config, add_devices, discovery_info=None):
    if (discovery_info):
        sensors = [ NibeSensor(hass, sensor['systemId'], sensor['parameterId']) for sensor in discovery_info ]
    else:
        sensors = [ NibeSensor(hass, config.get(CONF_SYSTEM), config.get(CONF_PARAMETER)) ]

    add_devices(sensors, True)

class NibeSensor(Entity):
    def __init__(self, hass, system, parameter):
        """Initialize the Nibe sensor."""
        self._state      = 0
        self._system     = system
        self._parameter  = parameter
        self._name       = "{}_{}".format(system, parameter)
        self._unit       = None
        self._attributes = None
        self.entity_id  = generate_entity_id(
                                ENTITY_ID_FORMAT,
                                self._name,
                                hass=hass)

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

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

            return {
                ATTR_BATTERY_LEVEL: self._battery,
            }

    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """

        data = self.hass.data[DOMAIN].get_parameter(self._system, self._parameter)
        if data:

            self._name  = data['title']

            if (data['unit'] in SCALE):
                self._unit  = SCALE[data['unit']]['unit']
                if data['displayValue'] == '--':
                    self._state = None
                else:
                    self._state = data['rawValue'] / SCALE[data['unit']]['scale']
            else:
                self._unit  = None
                self._state = data['displayValue']

            self.attributes = {
                'designation': data['desgination']
            }

