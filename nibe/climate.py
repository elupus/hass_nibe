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

    entities = []

    for system in systems.values():
        for climate, config in system.climates.items():
            entities.append(
                NibeClimateSupply(
                    uplink,
                    system.system_id,
                    PARAM_CLIMATE_SYSTEMS[climate],
                    config.get('groups')
                )
            )
            entities.append(
                NibeClimateRoom(
                    uplink,
                    system.system_id,
                    PARAM_CLIMATE_SYSTEMS[climate],
                    config.get('groups')
                )
            )

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

        from nibeuplink import (PARAM_PUMP_SPEED_HEATING_MEDIUM,
                                PARAM_STATUS_COOLING,
                                PARAM_COMPRESSOR_FREQUENCY)

        self._climate = climate
        self._current = None
        self._active = None
        self._status = 'DONE'
        self._current_operation = None
        self._current_mode = STATE_HEAT
        self._data = OrderedDict()
        self._select = OrderedDict()
        self._select['pump_speed_heating_medium'] = \
            PARAM_PUMP_SPEED_HEATING_MEDIUM
        self._select['compressor_frequency'] = \
            PARAM_COMPRESSOR_FREQUENCY
        self._select['status_cooling'] = \
            PARAM_STATUS_COOLING

    @property
    def name(self):
        return self._climate.name

    @property
    def device_info(self):
        return self.hass.data[DATA_NIBE]['systems'][self._system_id].device_info

    @property
    def temperature_unit(self):
        if self._current:
            return self._current['unit']
        else:
            return None

    @property
    def device_state_attributes(self):
        data = {}
        data['status'] = self._status
        for key, value in self._data.items():
            if value:
                data[key] = value['value']
            else:
                data[key] = None
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

    async def async_set_temperature_internal(self, parameter, data):

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

        _LOGGER.debug("Update climate {}".format(self.name))

        async def get_parameter(parameter_id):
            if parameter_id:
                return await self._uplink.get_parameter(self._system_id,
                                                        parameter_id)
            else:
                return None

        data = OrderedDict()

        async def fill(key, parameter_id):
            if parameter_id is None:
                data[key] = None
            else:
                data[key] = await get_parameter(parameter_id)

        await asyncio.gather(
            *[
                fill(key, parameter_id)
                for key, parameter_id in self._select.items()
            ],
        )

        self._data = data

        self._active  = self._data['compressor_frequency']
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


class NibeClimateRoom(NibeClimate):
    def __init__(self,
                 uplink,
                 system_id: int,
                 climate: ClimateDevice,
                 groups):
        super().__init__(
            uplink,
            system_id,
            climate,
            groups
        )
        self._target_id = None
        self._target = None

        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}_{}_room'.format(
                DOMAIN_NIBE,
                system_id,
                str(climate.name)
            )
        )

        self._select['room_temp'] = \
            self._climate.room_temp
        self._select['room_setpoint_heat'] = \
            self._climate.room_setpoint_heat
        self._select['room_setpoint_cool'] = \
            self._climate.room_setpoint_cool

    @property
    def name(self):
        return "{} Room".format(self._climate.name)

    @property
    def unique_id(self):
        return "{}_{}".format(super().unique_id, "room")

    @property
    def max_temp(self):
        return 35.0

    @property
    def min_temp(self):
        return 5.0

    @property
    def current_temperature(self):
        return self.get_value(self._current)

    @property
    def target_temperature(self):
        return self.get_value(self._target)

    @property
    def target_temperature_step(self):
        return 0.5

    async def async_set_temperature(self, **kwargs):
        data = kwargs.get(ATTR_TEMPERATURE)
        if data is None:
            return

        await self.async_set_temperature_internal(self._target_id, data)

    async def async_update(self):
        await super().async_update()

        self._current = self._data['room_temp']
        if self._current_mode == STATE_HEAT:
            self._target  = self._data['room_setpoint_heat']
            self._target_id = self._climate.room_setpoint_heat
        else:
            self._target  = self._data['room_setpoint_cool']
            self._target_id = self._climate.room_setpoint_cool


class NibeClimateSupply(NibeClimate):
    def __init__(self,
                 uplink,
                 system_id: int,
                 climate: ClimateDevice,
                 groups):
        super().__init__(
            uplink,
            system_id,
            climate,
            groups
        )
        self._adjust_id = None
        self._adjust = None
        self._target = None

        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}_{}_supply'.format(
                DOMAIN_NIBE,
                system_id,
                str(climate.name)
            )
        )

        self._select['supply_temp'] = \
            self._climate.supply_temp
        self._select['calc_supply_temp_heat'] = \
            self._climate.calc_supply_temp_heat
        self._select['calc_supply_temp_cool'] = \
            self._climate.calc_supply_temp_cool
        self._select['offset_heat'] = \
            self._climate.offset_heat
        self._select['offset_cool'] = \
            self._climate.offset_cool

    @property
    def name(self):
        return "{} Supply".format(self._climate.name)

    @property
    def unique_id(self):
        return "{}_{}".format(super().unique_id, "supply")

    def get_target_base(self):
        return self.get_value(self._target, 0) \
            - self.get_value(self._adjust, 0)

    @property
    def max_temp(self):
        return self.get_target_base() + 10.0

    @property
    def min_temp(self):
        return self.get_target_base() - 10.0

    @property
    def current_temperature(self):
        return self.get_value(self._current)

    @property
    def target_temperature(self):
        return self.get_value(self._target)

    @property
    def target_temperature_step(self):
        return 1.0

    async def async_set_temperature(self, **kwargs):
        data = kwargs.get(ATTR_TEMPERATURE)
        if data is None:
            return
        # calculate what offset was used to calculate the target
        base = self.get_target_base()
        data = data - base

        await self.async_set_temperature_internal(self._adjust_id, data)

    async def async_update(self):
        await super().async_update()

        self._current = self._data['supply_temp']
        if self._current_mode == STATE_HEAT:
            self._target  = self._data['calc_supply_temp_heat']
            self._adjust  = self._data['offset_heat']
            self._adjust_id = self._climate.offset_heat
        else:
            self._target  = self._data['calc_supply_temp_cool']
            self._adjust  = self._data['offset_cool']
            self._adjust_id = self._climate.offset_cool
