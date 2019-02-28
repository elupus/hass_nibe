import logging
import asyncio
from collections import OrderedDict
from typing import Set

from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.climate import (
    ClimateDevice,
    ENTITY_ID_FORMAT,
)

try:
    from homeassistant.components.climate.const import (
        STATE_HEAT,
        STATE_COOL,
        SUPPORT_TARGET_TEMPERATURE
    )
except ImportError:
    from homeassistant.components.climate import (
        STATE_HEAT,
        STATE_COOL,
        SUPPORT_TARGET_TEMPERATURE
    )

from homeassistant.const import (ATTR_TEMPERATURE)
from ..nibe.const import (
    DOMAIN as DOMAIN_NIBE,
    DATA_NIBE,
    CONF_CLIMATES,
)
from ..nibe.entity import NibeEntity

DEPENDENCIES = ['nibe']
PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the climate device based on a config entry."""

    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink = hass.data[DATA_NIBE]['uplink']
    systems = hass.data[DATA_NIBE]['systems']

    from nibeuplink import (PARAM_CLIMATE_SYSTEMS)

    entities = []

    async def is_active(system, climate):
        if not system.config[CONF_CLIMATES]:
            return False

        if climate.active_accessory is None:
            return True

        active_accessory = await uplink.get_parameter(
            system.system_id,
            climate.active_accessory)

        _LOGGER.debug("Accessory status for {} is {}".format(
            climate.name,
            active_accessory))

        if active_accessory and active_accessory['rawValue']:
            return True

        return False

    async def add_active(system, climate):
        if await is_active(system, climate):
            entities.append(
                NibeClimateSupply(
                    uplink,
                    system.system_id,
                    system.statuses,
                    climate
                )
            )
            entities.append(
                NibeClimateRoom(
                    uplink,
                    system.system_id,
                    system.statuses,
                    climate
                )
            )

    await asyncio.gather(*[
        add_active(system, climate)
        for climate in PARAM_CLIMATE_SYSTEMS.values()
        for system in systems.values()
    ])

    async_add_entities(entities, True)


class NibeClimate(NibeEntity, ClimateDevice):
    def __init__(self,
                 uplink,
                 system_id: int,
                 statuses: Set[str],
                 climate: ClimateDevice):
        super(NibeClimate, self).__init__(
            uplink,
            system_id,
            [])

        from nibeuplink import (PARAM_PUMP_SPEED_HEATING_MEDIUM)

        self.get_parameters([
            PARAM_PUMP_SPEED_HEATING_MEDIUM,
        ])

        self._climate = climate
        self._status = 'DONE'
        self._current_operation = STATE_HEAT
        self.parse_statuses(statuses)

    @property
    def device_info(self):
        return {
            'identifiers': {(DOMAIN_NIBE,
                             self._system_id,
                             self._climate.supply_temp)},
            'via_hub': (DOMAIN_NIBE, self._system_id),
            'name': self._climate.name,
            'model': 'Climate System',
            'manufacturer': "NIBE Energy Systems",
        }

    @property
    def name(self):
        return self._climate.name

    @property
    def device_state_attributes(self):

        from nibeuplink import (PARAM_PUMP_SPEED_HEATING_MEDIUM)

        data = OrderedDict()
        data['status'] = self._status
        data['pump_speed_heating_medium'] = \
            self.get_float(PARAM_PUMP_SPEED_HEATING_MEDIUM)

        return data

    @property
    def supported_features(self):
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def is_on(self):
        return self._is_on

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
        await super().async_update()
        self.parse_data()

    async def async_statuses_updated(self, statuses: Set[str]):
        self.parse_statuses(statuses)
        self.async_schedule_update_ha_state()

    def parse_statuses(self, statuses: Set[str]):
        if 'Heating' in statuses:
            self._current_operation = STATE_HEAT
            self._is_on = True
        elif 'Cooling' in statuses:
            self._current_operation = STATE_COOL
            self._is_on = True
        else:
            self._is_on = False

    def parse_data(self):
        pass


class NibeClimateRoom(NibeClimate):
    def __init__(self,
                 uplink,
                 system_id: int,
                 statuses: Set[str],
                 climate: ClimateDevice):
        super().__init__(
            uplink,
            system_id,
            statuses,
            climate
        )
        self._target_id = None

        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}_{}_room'.format(
                DOMAIN_NIBE,
                system_id,
                str(climate.name)
            )
        )

        self.get_parameters([
            self._climate.room_temp,
            self._climate.room_setpoint_heat,
            self._climate.room_setpoint_cool,
        ])

    @property
    def available(self):
        return self.get_value(self._climate.room_temp) is not None

    @property
    def temperature_unit(self):
        data = self._parameters[self._climate.room_temp]
        if data:
            return data['unit']
        else:
            return None

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
        return self.get_float(self._climate.room_temp)

    @property
    def target_temperature(self):
        return self.get_float(self._target_id)

    @property
    def target_temperature_step(self):
        return 0.5

    async def async_set_temperature(self, **kwargs):
        data = kwargs.get(ATTR_TEMPERATURE)
        if data is None:
            return

        await self.async_set_temperature_internal(self._target_id, data)

    @property
    def device_state_attributes(self):
        data = super().device_state_attributes
        data['room_temp'] = \
            self.get_float(self._climate.room_temp)
        data['room_setpoint_heat'] = \
            self.get_float(self._climate.room_setpoint_heat)
        data['room_setpoint_cool'] = \
            self.get_float(self._climate.room_setpoint_cool)

    def parse_data(self):
        super().parse_data()

        if self._current_operation == STATE_HEAT:
            self._target_id = self._climate.room_setpoint_heat
        else:
            self._target_id = self._climate.room_setpoint_cool


class NibeClimateSupply(NibeClimate):
    def __init__(self,
                 uplink,
                 system_id: int,
                 statuses: Set[str],
                 climate: ClimateDevice):
        super().__init__(
            uplink,
            system_id,
            statuses,
            climate
        )
        self._adjust_id = None
        self._target_id = None

        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}_{}_supply'.format(
                DOMAIN_NIBE,
                system_id,
                str(climate.name)
            )
        )

        self.get_parameters([
            self._climate.supply_temp,
            self._climate.calc_supply_temp_heat,
            self._climate.calc_supply_temp_cool,
            self._climate.offset_heat,
            self._climate.offset_cool,
            self._climate.external_adjustment_active
        ])

    @property
    def available(self):
        return self.get_value(self._climate.supply_temp) is not None

    @property
    def temperature_unit(self):
        data = self._parameters[self._climate.supply_temp]
        if data:
            return data['unit']
        else:
            return None

    @property
    def name(self):
        return "{} Supply".format(self._climate.name)

    @property
    def unique_id(self):
        return "{}_{}".format(super().unique_id, "supply")

    def get_target_base(self):
        return (self.get_float(self._target_id, 0) -
                self.get_float(self._adjust_id, 0))

    @property
    def max_temp(self):
        return self.get_target_base() + 10.0

    @property
    def min_temp(self):
        return self.get_target_base() - 10.0

    @property
    def current_temperature(self):
        return self.get_float(self._climate.supply_temp)

    @property
    def target_temperature(self):
        return self.get_float(self._target_id)

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

    @property
    def device_state_attributes(self):
        data = super().device_state_attributes
        data['supply_temp'] = \
            self.get_float(self._climate.supply_temp)
        data['calc_supply_temp_heat'] = \
            self.get_float(self._climate.calc_supply_temp_heat)
        data['calc_supply_temp_cool'] = \
            self.get_float(self._climate.calc_supply_temp_cool)
        data['offset_heat'] = \
            self.get_float(self._climate.offset_heat)
        data['offset_cool'] = \
            self.get_float(self._climate.offset_cool)
        data['external_adjustment_active'] = \
            self.get_bool(self._climate.external_adjustment_active)

        return data

    def parse_data(self):
        super().parse_data()

        if self._current_operation == STATE_HEAT:
            self._target_id = self._climate.calc_supply_temp_heat
            self._adjust_id = self._climate.offset_heat
        else:
            self._target_id = self._climate.calc_supply_temp_cool
            self._adjust_id = self._climate.offset_cool
