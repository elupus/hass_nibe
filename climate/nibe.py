import logging
import asyncio
from collections import OrderedDict

from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.climate import (
    ClimateDevice,
    SUPPORT_TARGET_TEMPERATURE,
    STATE_HEAT,
    STATE_COOL,
    STATE_IDLE,
    ENTITY_ID_FORMAT
)
from homeassistant.const import (ATTR_TEMPERATURE)
from ..nibe.const import (
    DOMAIN as DOMAIN_NIBE,
    DATA_NIBE
)
from ..nibe.entity import NibeEntity

DEPENDENCIES = ['nibe']
_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass,
                               config,
                               async_add_devices,
                               discovery_info=None):
    """Old setyp, not used"""
    pass


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the climate device based on a config entry."""

    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink = hass.data[DATA_NIBE]['uplink']
    systems = hass.data[DATA_NIBE]['systems']

    from nibeuplink import (PARAM_CLIMATE_SYSTEMS)

    entities = [
        NibeClimate(
            uplink,
            system.system_id,
            PARAM_CLIMATE_SYSTEMS[climate],
            config.get('groups')
        )
        for system in systems
        for climate, config in system.climates.items()
    ]

    async_add_entities(entities, True)


class NibeClimate(NibeEntity, ClimateDevice):
    def __init__(self,
                 uplink,
                 system_id: int,
                 climate: ClimateDevice,
                 groups):
        super(NibeClimate, self).__init__(
            uplink,
            system_id,
            groups)

        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}_{}'.format(
                DOMAIN_NIBE,
                system_id,
                str(climate.name)
            )
        )


        self._climate = climate
        self._adjust_id = None
        self._target_id = None
        self._current = None
        self._target = None
        self._adjust = None
        self._active = None
        self._status = 'DONE'
        self._current_operation = None
        self._current_mode = STATE_HEAT
        self._attributes = OrderedDict()

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
        return self._climate.name

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
        data.update(self._attributes)
        return data

    @property
    def available(self):
        return self.get_value(self._current) is not None

    @property
    def supported_features(self):
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def is_on(self):
        return True

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_operation

    @property
    def unique_id(self):
        return "{}_{}".format(self._system_id,
                              self._climate.name)

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
            parameter = self._adjust_id
        else:
            base = 0.0
            parameter = self._target_id

        data = data - base

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

        from nibeuplink import (PARAM_PUMP_SPEED_HEATING_MEDIUM,
                                PARAM_STATUS_COOLING,
                                PARAM_COMPRESSOR_FREQUENCY)

        climate = self._climate._asdict()
        data = OrderedDict()

        async def fill(key, parameter_id):
            if type(parameter_id) == int:
                data[key] = await get_parameter(parameter_id)
            elif parameter_id is None:
                data[key] = None

        await asyncio.gather(
            *[
                fill(key, parameter_id)
                for key, parameter_id in climate.items()
            ],
            fill('pump_speed_heating_medium', PARAM_PUMP_SPEED_HEATING_MEDIUM),
            fill('compressor_frequency', PARAM_COMPRESSOR_FREQUENCY),
            fill('status_cooling', PARAM_STATUS_COOLING)
        )

        if data['status_cooling']['value']:
            self._current_operation = STATE_COOL
            self._current_mode = STATE_COOL
        else:
            self._current_mode = STATE_HEAT
            if data['pump_speed_heating_medium']['value'] and \
               data['compressor_frequency']['value']:
                self._current_operation = STATE_HEAT
            else:
                self._current_operation = STATE_IDLE

        for key, value in data.items():
            if value:
                self._attributes[key] = value['value']
            else:
                self._attributes[key] = None

        if data['use_room_sensor']['rawValue']:
            self._adjust  = None
            self._adjust_id = None
            if self._current_mode == STATE_HEAT:
                self._current = data['room_temp']
                self._target  = data['room_setpoint_heat']
                self._target_id = self._climate.room_setpoint_heat
            else:
                self._current = data['room_temp']
                self._target  = data['room_setpoint_cool']
                self._target_id = self._climate.room_setpoint_cool
        else:
            self._current = data['supply_temp']
            self._active  = data['compressor_frequency']
            if self._current_mode == STATE_HEAT:
                self._target  = data['calc_supply_temp_heat']
                self._target_id = self._climate.calc_supply_temp_heat

                self._adjust  = data['offset_heat']
                self._adjust_id = self._climate.offset_heat
            else:
                self._target  = data['calc_supply_temp_cool']
                self._target_id = self._climate.calc_supply_temp_cool

                self._adjust  = data['offset_cool']
                self._adjust_id = self._climate.offset_cool
