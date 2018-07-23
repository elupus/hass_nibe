import logging
import asyncio

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.climate import (
    ClimateDevice,
    ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_ON_OFF
)
from homeassistant.const import (ATTR_TEMPERATURE, CONF_NAME)
from ..nibe import (
    CONF_OBJECTID,
    CONF_SYSTEM,
    CONF_CLIMATE,
    CONF_CURRENT,
    CONF_TARGET,
    CONF_ADJUST,
    CONF_ACTIVE,
    DATA_NIBE,
)
from ..nibe.entity import NibeEntity

DEPENDENCIES = ['nibe']
_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SYSTEM): cv.positive_int,
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_CLIMATE): cv.string,
    vol.Optional(CONF_CURRENT): cv.positive_int,
    vol.Optional(CONF_TARGET): cv.positive_int,
    vol.Optional(CONF_ADJUST): cv.positive_int,
    vol.Optional(CONF_OBJECTID): cv.string,
})


async def async_setup_platform(hass,
                               config,
                               async_add_devices,
                               discovery_info=None):

    sensors = []
    configs = []
    if (discovery_info):
        configs = [PLATFORM_SCHEMA(x) for x in discovery_info]
    else:
        configs = [config]

    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    from nibeuplink import (PARAM_PUMP_SPEED, PARAM_CLIMATE_SYSTEMS)

    for c in configs:
        index   = c.get(CONF_CLIMATE, '0')[0]
        variant = c.get(CONF_CLIMATE, '0')[1:]
        climate = PARAM_CLIMATE_SYSTEMS.get(index)
        if climate:
            name = climate.name
            if variant == 'h':
                name    = '{} Heat (room)'.format(index)
                current = climate.room_temp
                target  = climate.room_setpoint_heat
                adjust  = None
                active  = PARAM_PUMP_SPEED
            elif variant == 'c':
                name    = '{} Cool (room)'.format(index)
                current = climate.room_temp
                target  = climate.room_setpoint_cool
                adjust  = None
                active  = None
            elif variant == 'ha':
                name    = '{} Heat (flow)'.format(index)
                current = climate.supply_temp
                target  = climate.calc_supply_temp_heat
                adjust  = climate.offset_heat
                active  = PARAM_PUMP_SPEED
            elif variant == 'ca':
                name    = '{} Cool (flow)'.format(index)
                current = climate.supply_temp
                target  = climate.calc_supply_temp_cool
                adjust  = climate.offset_cool
                active  = None
        else:
            name    = 'System'
            current = c.get(CONF_CURRENT)
            target  = c.get(CONF_TARGET)
            adjust  = c.get(CONF_ADJUST)
            active  = c.get(CONF_ACTIVE)

        sensors.append(
            NibeClimate(
                hass.data[DATA_NIBE]['uplink'],
                c.get(CONF_NAME, name),
                c.get(CONF_SYSTEM),
                current,
                target,
                adjust,
                active,
                c.get(CONF_OBJECTID),
            )
        )

    async_add_devices(sensors, True)


class NibeClimate(NibeEntity, ClimateDevice):
    def __init__(self,
                 uplink,
                 name: str,
                 system_id: int,
                 current_id: str,
                 target_id: str,
                 adjust_id: str,
                 active_id: str,
                 object_id: str):
        super(NibeClimate, self).__init__(uplink, system_id)
        self._name = name
        self._current_id = current_id
        self._target_id = target_id
        self._adjust_id = adjust_id
        self._active_id = active_id
        self._unit = None
        self._current = None
        self._target = None
        self._adjust = None
        self._active = None
        self._status = 'DONE'
        if object_id:  # Forced id on discovery
            self.entity_id = ENTITY_ID_FORMAT.format(object_id)

    def get_value(self, data, default=None):
        if data is None or data['value'] is None:
            return default
        else:
            return float(data['value'])

    def get_scale(self, data):
        if data is None or data['value'] is None:
            return 1.0
        else:
            return float(data['rawValue']) / float(data['value'])

    def get_target_base(self):
        return self.get_value(self._target, 0) \
            - self.get_value(self._adjust, 0)

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
        features = SUPPORT_TARGET_TEMPERATURE
        if self._active_id:
            features = features | SUPPORT_ON_OFF
        return features

    @property
    def is_on(self):
        if self._active_id:
            return self._active is not None and bool(self._active['value'])
        else:
            return None

    @property
    def unique_id(self):
        return "{}_{}".format(self._system_id,
                              self._current_id,
                              self._target_id,
                              self._adjust_id)

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
            base = self.get_target_base()
            scale = self.get_scale(self._adjust)
            parameter = self._adjust_id
        else:
            base = 0.0
            scale = self.get_scale(self._target)
            parameter = self._target_id

        data = scale * (data - base)

        _LOGGER.debug("Set temperature on parameter {} to {}".format(
            parameter,
            data))

        try:
            self._status = await self._uplink.put_parameter(self._system_id,
                                                            parameter,
                                                            data)
        except BaseException:
            self._status = 'ERROR'
            raise
        finally:
            _LOGGER.debug("Put parameter response {}".format(self._status))

    async def async_update(self):

        async def get_parameter(parameter_id):
            if parameter_id:
                return await self._uplink.get_parameter(self._system_id,
                                                        parameter_id)
            else:
                return None

        (self._current,
         self._target,
         self._adjust,
         self._active) = await asyncio.gather(
            get_parameter(self._current_id),
            get_parameter(self._target_id),
            get_parameter(self._adjust_id),
            get_parameter(self._active_id),
        )
