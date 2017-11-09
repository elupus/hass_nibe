import logging
import asyncio

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.helpers.entity import (Entity, async_generate_entity_id)
from homeassistant.components.climate import (ClimateDevice, PLATFORM_SCHEMA, ATTR_HUMIDITY)
from homeassistant.const import (TEMP_CELSIUS, ATTR_TEMPERATURE, CONF_NAME)
from homeassistant.loader import get_component

# Cheaty way to import since paths for custom components don't seem to work with normal imports
SCALE_DEFAULT = get_component('nibe').__dict__['SCALE_DEFAULT']
SCALES        = get_component('nibe').__dict__['SCALES']
parse_parameter_data = get_component('nibe').__dict__['parse_parameter_data']

DEPENDENCIES = ['nibe']
_LOGGER      = logging.getLogger(__name__)

DATA_NIBE      = 'nibe'

CONF_SYSTEM    = 'system'
CONF_CURRENT   = 'current'
CONF_TARGET    = 'target'
CONF_ADJUST    = 'adjust'

PLATFORM_SCHEMA.extend({
        vol.Required(CONF_SYSTEM) : cv.positive_int,
        vol.Required(CONF_NAME)   : cv.string,
        vol.Optional(CONF_CURRENT): cv.positive_int,
        vol.Optional(CONF_TARGET) : cv.positive_int,
        vol.Optional(CONF_ADJUST) : cv.positive_int,
})

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):

    sensors = None
    if (discovery_info):
        pass
    else:
        sensors = [ NibeClimate(config.get(CONF_NAME), config.get(CONF_SYSTEM), config.get(CONF_CURRENT), config.get(CONF_TARGET), config.get(CONF_ADJUST)) ]

    async_add_devices(sensors, True)


class NibeClimate(ClimateDevice):
    def __init__(self, name, system_id, current_id, target_id, adjust_id):
        self._name         = name
        self._system_id    = system_id
        self._current_id   = current_id
        self._target_id    = target_id
        self._adjust_id    = adjust_id
        self._unit         = TEMP_CELSIUS
        self._current      = None
        self._target       = None
        self._adjust       = None

    @property
    def name(self):
        return self._name

    @property
    def current_temperature(self):
        return self._current

    @property
    def target_temperature(self):
        return self._target

    @property
    def temperature_unit(self):
        return self._unit

    @property
    def target_temperature_step(self):
        return 0.5

    @property
    def target_humidity(self):
        return self._adjust

    @property
    def current_humidity(self):
        return self._adjust

    @property
    def min_humidity(self):
        return -10

    @property
    def max_humidity(self):
        return 10

    @asyncio.coroutine
    def async_set_temperature(self, **kwargs):
        data = kwargs.get(ATTR_TEMPERATURE)
        if data is None:
            return

        uplink = self.hass.data[DATA_NIBE]['uplink']
        yield from uplink.set_parameter(self._system_id, self._target_id, data)

    @asyncio.coroutine
    def async_set_humidity(self, **kwargs):
        data = kwargs.get(ATTR_HUMIDITY)
        if data is None:
            return

        uplink = self.hass.data[DATA_NIBE]['uplink']
        yield from uplink.set_parameter(self._system_id, self._adjust_id, data)


    @asyncio.coroutine
    def async_update(self):

        uplink = self.hass.data[DATA_NIBE]['uplink']

        @asyncio.coroutine
        def get_parameter(parameter_id):
            if parameter_id:
                value = yield from uplink.get_parameter(self._system_id, parameter_id)
                if value:
                    scale = SCALES.get(value['unit'], SCALE_DEFAULT)
                    return parse_parameter_data(value, scale)
                return None
            else:
                return None

        self._current, self._target, self._adjust = yield from asyncio.gather(
            get_parameter(self._current_id),
            get_parameter(self._target_id),
            get_parameter(self._adjust_id),
        )
