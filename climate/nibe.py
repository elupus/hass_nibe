import logging
import asyncio

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import (async_generate_entity_id)
from homeassistant.components.climate import (
    ClimateDevice,
    ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_TEMPERATURE_HIGH,
    SUPPORT_TARGET_TEMPERATURE_LOW,
    SUPPORT_ON_OFF
)
from homeassistant.const import (ATTR_TEMPERATURE, CONF_NAME)
from collections import namedtuple

DEPENDENCIES = ['nibe']
_LOGGER      = logging.getLogger(__name__)

DATA_NIBE      = 'nibe'

CONF_SYSTEM    = 'system'
CONF_CLIMATE   = 'climate'
CONF_CURRENT   = 'current'
CONF_TARGET    = 'target'
CONF_ADJUST    = 'adjust'
CONF_ACTIVE    = 'active'

CLIMATE_SCHEMA = {
    vol.Required(CONF_SYSTEM) : cv.positive_int,
    vol.Required(CONF_NAME)   : cv.string,
    vol.Optional(CONF_CLIMATE): cv.string,
    vol.Optional(CONF_CURRENT): cv.positive_int,
    vol.Optional(CONF_TARGET) : cv.positive_int,
    vol.Optional(CONF_ADJUST) : cv.positive_int,
}

PLATFORM_SCHEMA.extend(CLIMATE_SCHEMA)

NAME_HEATING_ROOM = "S{} Heat (room)"
NAME_HEATING_FLOW = "S{} Heat (flow)"
NAME_COOLING_ROOM = "S{} Cool (room)"
NAME_COOLING_FLOW = "S{} Cool (flow)"

ClimateSystem = namedtuple(
    'ClimateSystem',
    ['name', 'current', 'target', 'adjust', 'active']
)

PARAM_PUMP_SPEED = 43437

CLIMATE_SYSTEMS = {
    '1h' : ClimateSystem(NAME_HEATING_ROOM.format(1), 40033, 47398, None , PARAM_PUMP_SPEED),
    '2h' : ClimateSystem(NAME_HEATING_ROOM.format(2), 40032, 47397, None , PARAM_PUMP_SPEED),
    '3h' : ClimateSystem(NAME_HEATING_ROOM.format(3), 40031, 47396, None , PARAM_PUMP_SPEED),
    '4h' : ClimateSystem(NAME_HEATING_ROOM.format(4), 40030, 47395, None , PARAM_PUMP_SPEED),
    '1ha': ClimateSystem(NAME_HEATING_FLOW.format(1), 40008, 43009, 47011, PARAM_PUMP_SPEED),
    '2ha': ClimateSystem(NAME_HEATING_FLOW.format(2), 40007, 43008, 47010, PARAM_PUMP_SPEED),
    '3ha': ClimateSystem(NAME_HEATING_FLOW.format(3), 40006, 43007, 47009, PARAM_PUMP_SPEED),
    '4ha': ClimateSystem(NAME_HEATING_FLOW.format(4), 40005, 43006, 47008, PARAM_PUMP_SPEED),
    '1c' : ClimateSystem(NAME_COOLING_ROOM.format(1), 40033, 48785, None , None),
    '2c' : ClimateSystem(NAME_COOLING_ROOM.format(2), 40032, 48784, None , None),
    '3c' : ClimateSystem(NAME_COOLING_ROOM.format(3), 40031, 48783, None , None),
    '4c' : ClimateSystem(NAME_COOLING_ROOM.format(4), 40030, 48782, None , None),
    '1ca': ClimateSystem(NAME_COOLING_FLOW.format(1), 40008, 43009, 48739, None),
    '2ca': ClimateSystem(NAME_COOLING_FLOW.format(2), 40007, 43008, 48738, None),
    '3ca': ClimateSystem(NAME_COOLING_FLOW.format(3), 40006, 43007, 48737, None),
    '4ca': ClimateSystem(NAME_COOLING_FLOW.format(4), 40005, 43006, 48736, None),
}

CLIMATE_NONE = ClimateSystem(None, None, None, None, None)


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):

    sensors = []
    configs = []
    if (discovery_info):
        configs = discovery_info
    else:
        configs = [config]

    for c in configs:
        if CONF_CLIMATE in c:
            climate = CLIMATE_SYSTEMS[c[CONF_CLIMATE]]
        else:
            climate = CLIMATE_NONE

        sensors.append(NibeClimate(hass,
                                   c.get(CONF_NAME   , climate.name),
                                   c.get(CONF_SYSTEM),
                                   c.get(CONF_CURRENT, climate.current),
                                   c.get(CONF_TARGET , climate.target),
                                   c.get(CONF_ADJUST , climate.adjust),
                                   c.get(CONF_ADJUST , climate.active)))

    async_add_devices(sensors, True)


class NibeClimate(ClimateDevice):
    def __init__(self, hass, name, system_id, current_id, target_id, adjust_id, active_id):
        self._name         = name
        self._system_id    = system_id
        self._current_id   = current_id
        self._target_id    = target_id
        self._adjust_id    = adjust_id
        self._active_id    = active_id
        self._unit         = None
        self._current      = None
        self._target       = None
        self._adjust       = None
        self._active       = None
        self._status       = 'DONE'
        self._uplink       = hass.data[DATA_NIBE]['uplink']
        self.entity_id     = async_generate_entity_id(
            ENTITY_ID_FORMAT,
            'nibe_{}_{}'.format(system_id, current_id),
            hass=hass
        )

    def get_value(self, data, default = None):
        if data is None or data['value'] is None:
            return default
        else:
            return float(data['value'])

    def get_target_base(self):
        return self.get_value(self._target, 0)  - self.get_value(self._adjust, 0)

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
        if self._adjust_id:
            return 1.0
        else:
            return 0.5

    @property
    def max_temp(self):
        if self._adjust_id:
            return self.get_target_base() + 10.0
        else:
            return 35.0

    @property
    def min_temp(self):
        if self._adjust_id:
            return self.get_target_base() - 10.0
        else:
            return 5.0

    @property
    def state_attributes(self):
        data = super().state_attributes
        data['status'] = self._status
        return data

    @property
    def available(self):
        return self.get_value(self._current) is not None

    @property
    def supported_features(self):
        features = (SUPPORT_TARGET_TEMPERATURE |
                    SUPPORT_TARGET_TEMPERATURE_HIGH |
                    SUPPORT_TARGET_TEMPERATURE_LOW)
        if self._active_id:
            features = features | SUPPORT_ON_OFF
        return features

    @property
    def is_on(self):
        if self._active_id:
            _LOGGER.error("GAD {}".format(self._active is not None and self._active['value']))
            return self._active is not None and bool(self._active['value'])
        else:
            return None

    async def async_turn_on(self):
        return

    async def async_turn_off(self):
        return

    async def async_set_temperature(self, **kwargs):
        data = kwargs.get(ATTR_TEMPERATURE)
        if data is None:
            return

        if self._adjust_id:
            # calculate what offset was used to calculate the target
            data = data - self.get_target_base()
            parameter = self._adjust_id
        else:
            parameter = self._target_id

        _LOGGER.debug("Set temperature on parameter {} to {}".format(parameter, data))

        try:
            self._status = await self._uplink.put_parameter(self._system_id, parameter, data)
        except:

            self._status = 'ERROR'
            pass
        finally:
            _LOGGER.debug("Put parameter response {}".format(self._status))

    async def async_update(self):

        async def get_parameter(parameter_id):
            if parameter_id:
                return await self._uplink.get_parameter(self._system_id, parameter_id)
            else:
                return None

        self._current, self._target, self._adjust, self._active = await asyncio.gather(
            get_parameter(self._current_id),
            get_parameter(self._target_id),
            get_parameter(self._adjust_id),
            get_parameter(self._active_id),
        )
