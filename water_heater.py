import logging
import asyncio
import aiohttp
from collections import OrderedDict
from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.water_heater import (
    WaterHeaterDevice,
    STATE_HEAT_PUMP,
    STATE_ECO,
    STATE_HIGH_DEMAND,
    ENTITY_ID_FORMAT,
    SUPPORT_OPERATION_MODE
)
from homeassistant.const import (
    STATE_OFF,
)
from typing import Set
from ..nibe.const import (
    DOMAIN as DOMAIN_NIBE,
    DATA_NIBE,
    CONF_WATER_HEATERS,
)
from ..nibe.entity import NibeEntity

DEPENDENCIES = ['nibe']
PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)

STATE_BOOST_ONE_TIME = 'boost_one_time'
STATE_BOOST_THREE_HOURS = 'boost_three_hours'
STATE_BOOST_SIX_HOUR = 'boost_six_hours'
STATE_BOOST_TWELVE_HOURS = 'boost_twelve_hours'

NIBE_STATE_TO_HA = {
    'economy': {
        'state': STATE_ECO,
        'start': 'start_temperature_water_economy',
        'stop': 'stop_temperature_water_economy',
    },
    'normal' : {
        'state': STATE_HEAT_PUMP,
        'start': 'start_temperature_water_normal',
        'stop': 'stop_temperature_water_normal',
    },
    'luxuary': {
        'state': STATE_HIGH_DEMAND,
        'start': 'start_temperature_water_luxary',
        'stop': 'stop_temperature_water_luxary',
    }
}

NIBE_BOOST_TO_STATE = {
    1: STATE_BOOST_THREE_HOURS,
    2: STATE_BOOST_SIX_HOUR,
    3: STATE_BOOST_TWELVE_HOURS,
    4: STATE_BOOST_ONE_TIME
}

HA_STATE_TO_NIBE = {v['state']: k for k, v in NIBE_STATE_TO_HA.items()}
HA_BOOST_TO_NIBE = {v: k for k, v in NIBE_BOOST_TO_STATE.items()}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the climate device based on a config entry."""

    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink = hass.data[DATA_NIBE]['uplink']
    systems = hass.data[DATA_NIBE]['systems']

    entities = []

    from nibeuplink import (PARAM_HOTWATER_SYSTEMS)

    async def is_active(system, hwsys):
        if not system.config[CONF_WATER_HEATERS]:
            return False

        available = await uplink.get_parameter(
            system.system_id,
            hwsys.hot_water_production)
        if available and available['rawValue']:
            return True
        return False

    async def add_active(system, hwsys):
        if await is_active(system, hwsys):
            entities.append(
                NibeWaterHeater(
                    uplink,
                    system.system_id,
                    system.statuses,
                    hwsys,
                )
            )

    await asyncio.gather(*[
        add_active(system, hwsys)
        for hwsys in PARAM_HOTWATER_SYSTEMS.values()
        for system in systems.values()
    ])

    async_add_entities(entities, True)


class NibeWaterHeater(NibeEntity, WaterHeaterDevice):
    def __init__(self,
                 uplink,
                 system_id: int,
                 statuses: Set[str],
                 hwsys):
        super().__init__(
            uplink,
            system_id,
            [])

        self._name = hwsys.name
        self._current_operation = STATE_OFF
        self._current_state = STATE_OFF
        self._hwsys = hwsys

        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}'.format(
                DOMAIN_NIBE,
                self.unique_id
            )
        )

        self.get_parameters([
            self._hwsys.hot_water_charging,
            self._hwsys.hot_water_comfort_mode,
            self._hwsys.hot_water_top,
            self._hwsys.start_temperature_water_economy,
            self._hwsys.start_temperature_water_normal,
            self._hwsys.start_temperature_water_luxary,
            self._hwsys.stop_temperature_water_economy,
            self._hwsys.stop_temperature_water_normal,
            self._hwsys.stop_temperature_water_luxary,
            self._hwsys.hot_water_boost,
        ])
        self.parse_statuses(statuses)

    @property
    def name(self):
        return self._name

    @property
    def temperature_unit(self):
        data = self._parameters[self._hwsys.hot_water_charging]
        if data:
            return data['unit']
        else:
            return None

    @property
    def device_state_attributes(self):
        data = OrderedDict()
        data['current_temperature'] = self.current_temperature
        data['target_temp_low'] = self.target_temperature_low
        data['target_temp_high'] = self.target_temperature_high
        return data

    @property
    def available(self):
        value = self.get_value(self._hwsys.hot_water_charging)
        return value is not None

    @property
    def is_on(self):
        return self._is_on

    @property
    def supported_features(self):
        return SUPPORT_OPERATION_MODE

    @property
    def state(self):
        """Return the current state."""
        if self._is_on:
            return self._current_state
        else:
            return STATE_OFF

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_operation

    @property
    def current_temperature(self):
        """Returrn current temperature."""
        return self.get_float(self._hwsys.hot_water_charging)

    def get_float_named(self, name):
        parameter_id = getattr(self._hwsys, name, None)
        return self.get_float(parameter_id)

    def get_float_operation(self, name):
        if self._current_operation in HA_BOOST_TO_NIBE:
            state = HA_STATE_TO_NIBE.get(STATE_HIGH_DEMAND)
        else:
            state = HA_STATE_TO_NIBE.get(self._current_operation)
        if state:
            return self.get_float_named(NIBE_STATE_TO_HA[state][name])
        else:
            return None

    @property
    def target_temperature_high(self):
        return self.get_float_operation('stop')

    @property
    def target_temperature_low(self):
        return self.get_float_operation('start')

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        operations = []
        for x in NIBE_STATE_TO_HA.values():
            operations.append(x['state'])
        for x in NIBE_BOOST_TO_STATE.values():
            operations.append(x)
        return operations

    async def async_set_operation_mode(self, operation_mode):
        """Set new target operation mode."""
        try:
            if operation_mode in HA_STATE_TO_NIBE:
                    await self._uplink.put_parameter(
                        self._system_id,
                        self._hwsys.hot_water_comfort_mode,
                        HA_STATE_TO_NIBE[operation_mode])
            elif operation_mode in HA_BOOST_TO_NIBE:
                    await self._uplink.put_parameter(
                        self._system_id,
                        self._hwsys.hot_water_boost,
                        HA_BOOST_TO_NIBE[operation_mode])
            else:
                _LOGGER.error("Operation mode %s not supported",
                              operation_mode)
        except aiohttp.client_exceptions.ClientResponseError as e:
            _LOGGER.error("Error trying to set mode %s", str(e))

    @property
    def unique_id(self):
        return "{}_{}".format(self._system_id,
                              self._hwsys.hot_water_charging)

    async def async_update(self):

        _LOGGER.debug("Update water heater {}".format(self.name))
        await super().async_update()
        self.parse_data()

    async def async_statuses_updated(self, statuses: Set[str]):
        self.parse_statuses(statuses)
        self.async_schedule_update_ha_state()

    def parse_statuses(self, statuses: Set[str]):
        if 'Hot Water' in statuses:
            self._is_on = True
        else:
            self._is_on = False

    def parse_data(self):
        mode = self.get_value(self._hwsys.hot_water_comfort_mode)
        if mode in NIBE_STATE_TO_HA:
            operation = NIBE_STATE_TO_HA[mode]['state']
        else:
            operation = STATE_OFF
        self._current_state = operation

        boost = self._parameters[self._hwsys.hot_water_boost]
        if boost:
            value = boost['rawValue']
            if value != 0:
                operation = NIBE_BOOST_TO_STATE.get(
                    value, 'boost_{}'.format(value))

        self._current_operation = operation
