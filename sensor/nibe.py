import logging
import time
import json
import requests

from homeassistant.helpers.entity import (Entity, generate_entity_id)
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
        '°C' : { 'scale' : 10,  'unit': TEMP_CELSIUS, 'icon': None },
        'A'  : { 'scale' : 10,  'unit': 'A'         , 'icon': None },
        'DM' : { 'scale' : 10,  'unit': 'DM'        , 'icon': None },
        'kW' : { 'scale' : 100, 'unit': 'kW'        , 'icon': None },
        'Hz' : { 'scale' : 1  , 'unit': 'Hz'        , 'icon': 'mdi:update' },
        'h'  : { 'scale' : 10 , 'unit': 'h'         , 'icon': 'mdi:clock' },
}

SCALE_DEFAULT = { 'scale': None, 'unit': None, 'icon': None }


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
        self._data       = None
        self._icon       = None
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
    def icon(self):
        return self._icon

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            'designation'  : self._data['designation'],
            'parameter id' : self._data['parameterId'],
            'display value': self._data['displayValue'],
            'raw value'    : self._data['rawValue'],
            'display unit' : self._data['unit'],
        }

    @property
    def available(self):
        """Return True if entity is available."""
        if self._state == None:
            return False
        else:
            return True

    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """

        data = self.hass.data[DOMAIN].get_parameter(self._system, self._parameter)
        if data:

            self._name  = data['title']

            scale = SCALE.get(data['unit'], SCALE_DEFAULT)
            self._icon  = scale['icon']
            self._unit  = scale['unit']
            if data['displayValue'] == '--':
                self._state = None
            elif scale['scale']:
                self._state = data['rawValue'] / scale['scale']
            else:
                self._state = data['displayValue']

            self._data = data

        else:
            self._state = None


