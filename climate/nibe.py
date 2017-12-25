import logging
import asyncio

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.helpers.entity import (Entity, async_generate_entity_id)
from homeassistant.components.climate import (
    ClimateDevice, PLATFORM_SCHEMA, ATTR_HUMIDITY,
    SUPPORT_TARGET_TEMPERATURE, SUPPORT_TARGET_HUMIDITY,
    SUPPORT_AWAY_MODE, SUPPORT_HOLD_MODE, SUPPORT_FAN_MODE,
    SUPPORT_OPERATION_MODE, SUPPORT_AUX_HEAT, SUPPORT_SWING_MODE,
    SUPPORT_TARGET_TEMPERATURE_HIGH, SUPPORT_TARGET_TEMPERATURE_LOW)
from homeassistant.const import (TEMP_CELSIUS, ATTR_TEMPERATURE, CONF_NAME)
from homeassistant.loader import get_component
from collections import namedtuple

DEPENDENCIES = ['nibe']
_LOGGER      = logging.getLogger(__name__)

DATA_NIBE      = 'nibe'

CONF_SYSTEM    = 'system'
CONF_CLIMATE   = 'climate'
CONF_CURRENT   = 'current'
CONF_TARGET    = 'target'
CONF_ADJUST    = 'adjust'

PLATFORM_SCHEMA.extend({
        vol.Required(CONF_SYSTEM) : cv.positive_int,
        vol.Required(CONF_NAME)   : cv.string,
        vol.Optional(CONF_CLIMATE): cv.string,
        vol.Optional(CONF_CURRENT): cv.positive_int,
        vol.Optional(CONF_TARGET) : cv.positive_int,
        vol.Optional(CONF_ADJUST) : cv.positive_int,
})


ClimateSystem = namedtuple(
    'ClimateSystem',
    ['name', 'current', 'target', 'adjust']
)

CLIMATE_SYSTEMS = {
    '1h': ClimateSystem('S1 (heating)', 40033, 47398, 47011),
    '2h': ClimateSystem('S2 (heating)', 40032, 47397, 47010),
    '3h': ClimateSystem('S3 (heating)', 40031, 47396, 47009),
    '4h': ClimateSystem('S4 (heating)', 40030, 47395, 47008),
    '5h': ClimateSystem('S5 (heating)', 40167, 48683, 48494),
    '6h': ClimateSystem('S6 (heating)', 40166, 48682, 48493),
    '7h': ClimateSystem('S7 (heating)', 40165, 48681, 48492),
    '8h': ClimateSystem('S8 (heating)', 40164, 48680, 48491),

    '1c': ClimateSystem('S1 (cooling)', 40033, 48785, 48739),
    '2c': ClimateSystem('S2 (cooling)', 40032, 48784, 48738),
    '3c': ClimateSystem('S3 (cooling)', 40031, 48783, 48737),
    '4c': ClimateSystem('S4 (cooling)', 40030, 48782, 48736),
    '5c': ClimateSystem('S5 (cooling)', 40167, 48781, 48735),
    '6c': ClimateSystem('S6 (cooling)', 40166, 48780, 48734),
    '7c': ClimateSystem('S7 (cooling)', 40165, 48779, 48733),
    '8c': ClimateSystem('S8 (cooling)', 40164, 48778, 48732),
}

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):

    sensors = None
    if (discovery_info):
        pass
    else:
        sensors = []
        climate = config.get(CONF_CLIMATE)
        if (climate):
            sensors.append(NibeClimate(hass,
                                       config.get(CONF_NAME, CLIMATE_SYSTEMS[climate].name),
                                       config.get(CONF_SYSTEM),
                                       CLIMATE_SYSTEMS[climate].current,
                                       CLIMATE_SYSTEMS[climate].target,
                                       CLIMATE_SYSTEMS[climate].adjust))
        else:
            sensors.append(NibeClimate(hass,
                                       config.get(CONF_NAME),
                                       config.get(CONF_SYSTEM),
                                       config.get(CONF_CURRENT),
                                       config.get(CONF_TARGET),
                                       config.get(CONF_ADJUST)))

    async_add_devices(sensors, True)


class NibeClimate(ClimateDevice):
    def __init__(self, hass, name, system_id, current_id, target_id, adjust_id):
        self._name         = name
        self._system_id    = system_id
        self._current_id   = current_id
        self._target_id    = target_id
        self._adjust_id    = adjust_id
        self._unit         = None
        self._current      = None
        self._target       = None
        self._adjust       = None
        self._uplink       = hass.data[DATA_NIBE]['uplink']
        self.entity_id     = async_generate_entity_id(
                                'climate.nibe_' + str(self._system_id) + '_{}',
                                str(self._current_id),
                                hass=hass)

    def get_value(self, data):
        if data == None or data['value'] == '--':
            return None
        else:
            return data['value']

    @property
    def name(self):
        return self._name

    @property
    def current_temperature(self):
        return self.get_value(self._current)

    @property
    def target_temperature(self):
        return self.get_value(self._target)

    @property
    def temperature_unit(self):
        if self._current:
            return self._current['unit']
        else:
            return None

    @property
    def target_temperature_step(self):
        return 0.5

    @property
    def target_humidity(self):
        return self.get_value(self._adjust)

    @property
    def current_humidity(self):
        return self.get_value(self._adjust)

    @property
    def min_humidity(self):
        return -10

    @property
    def max_humidity(self):
        return 10

    @property
    def supported_features(self):
        features = (SUPPORT_TARGET_TEMPERATURE |
                    SUPPORT_TARGET_TEMPERATURE_HIGH |
                    SUPPORT_TARGET_TEMPERATURE_LOW)
        if self._adjust_id:
            features += SUPPORT_TARGET_HUMIDITY
        return features

    @asyncio.coroutine
    def async_set_temperature(self, **kwargs):
        data = kwargs.get(ATTR_TEMPERATURE)
        if data is None:
            return

        yield from self._uplink.set_parameter(self._system_id, self._target_id, data)

    @asyncio.coroutine
    def async_set_humidity(self, humidity):
        uplink = self.hass.data[DATA_NIBE]['uplink']
        yield from self._uplink.set_parameter(self._system_id, self._adjust_id, humidity)

    @asyncio.coroutine
    def async_update(self):

        @asyncio.coroutine
        def get_parameter(parameter_id):
            if parameter_id:
                data = yield from self._uplink.get_parameter(self._system_id, parameter_id)
                return data
            else:
                return None

        self._current, self._target, self._adjust = yield from asyncio.gather(
            get_parameter(self._current_id),
            get_parameter(self._target_id),
            get_parameter(self._adjust_id),
        )
